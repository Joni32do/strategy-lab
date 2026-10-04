"""The Flask app: a small JSON API plus the static frontend in ``web/``.

The API is stateless. Every play request carries the whole session
(game, params, seed, seats, action log); the server replays the log,
applies the new action, lets chance and bots move, and returns the new log
together with the scene to draw. See :mod:`strategy_lab.core.session`.

=============================  =================================================
``GET  /api/catalog``          chapters -> families -> games, with lock state
``GET  /api/games/<id>``       rulebook, params, bots, cards, challenges, lenses
``POST /api/play``             replay + act + advance; returns scene and log
``POST /api/lens/<id>``        run a lens on the current position
``POST /api/simulate``         a card stack against a bot over many games
``GET  /api/concepts``         cheatsheet cards with learned flags
``GET  /api/profile``          profile, progress and statistics
``PATCH /api/profile``         update name, tutorial progress or settings
``POST /api/profile/concept``  mark a concept card as seen
``POST /api/profile/reset``    forget everything
``GET  /api/history``          finished games (newest first)
``GET  /api/dev/version``      changes when Python or web files change
=============================  =================================================
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

from strategy_lab.core import registry
from strategy_lab.core.game import Game
from strategy_lab.core.match import simulate
from strategy_lab.core.policy import RulePolicy
from strategy_lab.core.session import ReplayError, Seat, Session
from strategy_lab.history import Store
from strategy_lab.learn import progress
from strategy_lab.learn.concepts import all_concepts
from strategy_lab.learn.curriculum import CHAPTERS
from strategy_lab.lenses import all_lenses, lenses_for
from strategy_lab.lenses import broken as broken_lenses

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"
STARTED = time.time()
MAX_SIM_GAMES = 500


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def default_seats(game: Game) -> list[Seat]:
    """You in seat 0 against the first bot; everyone a bot if not playable."""
    bot = game.bots[0].id if game.bots else "random"
    if not game.playable_by_human:
        return [Seat("bot", bot) for _ in range(game.num_players)]
    return [Seat("human")] + [Seat("bot", bot) for _ in range(game.num_players - 1)]


def build_session(body: dict) -> Session:
    gid = body.get("game")
    if not gid:
        raise ApiError("missing 'game'")
    try:
        game = registry.create(gid, body.get("params") or {})
    except KeyError as e:
        raise ApiError(str(e), 404) from None
    except (TypeError, ValueError) as e:
        raise ApiError(f"bad params: {e}") from None
    raw_seats = body.get("seats")
    seats = [Seat.from_json(x) for x in raw_seats] if raw_seats else default_seats(game)
    if len(seats) != game.num_players:
        seats = default_seats(game)
    for st in seats:
        if st.kind == "bot" and st.cards is None:
            try:
                game.bot(st.bot)
            except KeyError:
                st.bot = game.bots[0].id if game.bots else "random"
    return Session(game, seats, int(body.get("seed") or 0), body.get("log") or [])


def viewer_of(sess: Session) -> int | None:
    humans = sess.human_seats()
    return humans[0] if humans else None


def session_json(sess: Session, since: int = 0) -> dict:
    g, s = sess.game, sess.state
    viewer = viewer_of(sess)
    human_turn = sess.waiting_for_human()
    legal = []
    if human_turn:
        legal = [{"a": a, "label": g.action_label(s, a)} for a in g.legal_actions(s)]
    scene = g.scene(s, viewer)
    status = scene.get("status") or g.status(s, viewer)
    out = {
        "game": g.id, "params": g.p, "seed": sess.seed,
        "seats": [st.to_json() for st in sess.seats],
        "log": sess.log, "count": len(sess.steps),
        "steps": [st.to_json(i, viewer) for i, st in enumerate(sess.steps) if i >= since],
        "toMove": sess.to_move(), "humanTurn": human_turn, "viewer": viewer,
        "legal": legal, "terminal": sess.terminal, "timeout": sess.timeout,
        "returns": sess.returns(), "scene": scene, "status": status,
        "replayError": sess.replay_error,
    }
    if sess.terminal and viewer is not None:
        out["outcome"] = g.outcome(sess.returns(), viewer)
    return out


def create_app(data_dir: str | Path | None = None, dev: bool = False) -> Flask:
    """Build the app. ``data_dir`` holds profile and history (see :mod:`strategy_lab.history`)."""
    app = Flask("strategy_lab", static_folder=None)
    store = Store(data_dir)
    app.config["store"] = store
    app.config["dev"] = dev

    def settings() -> dict:
        return store.profile()["settings"]

    def current_progress() -> dict:
        return progress.compute(registry.games(), store.events(), settings())

    def record(event: dict) -> dict | None:
        """Append an event; return what it achieved (or None if a duplicate)."""
        before = current_progress()
        if not store.append(event):
            return None
        return progress.diff(before, current_progress())

    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return jsonify({"error": str(e)}), e.status

    # ------------------------------------------------------------- frontend
    def _static(path: str):
        resp = send_from_directory(WEB_DIR, path)
        if dev or path.endswith(".html"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/")
    def index():
        return _static("index.html")

    @app.get("/<path:path>")
    def static_files(path: str):
        if path.startswith("api/"):
            abort(404)
        return _static(path)

    # -------------------------------------------------------------- catalog
    @app.get("/api/catalog")
    def catalog():
        games = registry.games()
        prog = current_progress()
        unlocked = set(prog["unlocked"])
        finished = set(prog["finished"])
        chapters = []
        for ch in CHAPTERS:
            members = [g for g in games
                       if (g.draft and ch.id == "workbench") or (not g.draft and g.chapter == ch.id)]
            families: dict[str, dict] = {}
            for g in members:
                fam = g.family()
                entry = families.setdefault(fam["id"], {**fam, "games": []})
                meta = g.meta()
                meta.update({
                    "unlocked": g.id in unlocked, "finished": g.id in finished,
                    "stars": len(prog["stars"].get(g.id, [])),
                    "maxStars": len(g.challenges),
                })
                entry["games"].append(meta)
            chapters.append({**ch.to_json(), "open": prog["chapters"].get(ch.id, False),
                             "families": list(families.values()),
                             "count": len(members),
                             "finished": sum(1 for g in members if g.id in finished)})
        return jsonify({"chapters": chapters, "progress": prog,
                        "broken": {**registry.broken(), **broken_lenses()} if dev else {}})

    @app.get("/api/games/<gid>")
    def game_detail(gid: str):
        try:
            game = registry.create(gid)
        except KeyError as e:
            raise ApiError(str(e), 404) from None
        d = game.detail()
        d["lenses"] = [lens.meta(game) for lens in lenses_for(game)]
        prog = current_progress()
        d["earned"] = prog["stars"].get(gid, [])
        d["stats"] = progress.stats(store.events(game=gid))["games"].get(gid)
        d["defaultSeats"] = [s.to_json() for s in default_seats(game)]
        return jsonify(d)

    # ----------------------------------------------------------------- play
    @app.post("/api/play")
    def play():
        body = request.get_json(force=True, silent=True) or {}
        sess = build_session(body)
        error = None
        mode = body.get("mode", "play")
        if sess.replay_error is None:
            try:
                if body.get("undo"):
                    sess.undo()
                elif "action" in body and body["action"] is not None:
                    sess.act(body["action"])
            except ReplayError as e:
                error = str(e)
        if mode == "play" and not body.get("undo"):
            sess.advance()
        elif mode == "step":
            sess.step()
        out = session_json(sess, int(body.get("since") or 0))
        out["error"] = error
        out["sid"] = body.get("sid") or uuid.uuid4().hex
        viewer = viewer_of(sess)
        if sess.terminal and viewer is not None and body.get("record", True):
            rets = sess.returns()
            out["achieved"] = record({
                "type": "game", "id": out["sid"], "game": sess.game.id,
                "params": sess.game.p, "seat": viewer, "seed": sess.seed,
                "bots": [st.bot for st in sess.seats if st.kind == "bot"],
                "outcome": sess.game.outcome(rets, viewer), "returns": rets,
                "score": rets[viewer], "steps": len(sess.steps), "timeout": sess.timeout,
                "log": sess.log,
            })
        return jsonify(out)

    # ----------------------------------------------------------------- lens
    @app.post("/api/lens/<lens_id>")
    def lens(lens_id: str):
        body = request.get_json(force=True, silent=True) or {}
        lens_obj = all_lenses().get(lens_id)
        if lens_obj is None:
            raise ApiError(f"unknown lens {lens_id!r}", 404)
        sess = build_session(body)
        if not lens_obj.applies(sess.game):
            raise ApiError(f"lens {lens_id!r} does not apply to {sess.game.id!r}")
        result = lens_obj.run(sess, body.get("options") or {})
        achieved = None
        if body.get("record", True):
            sid = body.get("sid") or "anon"
            achieved = record({"type": "lens", "id": f"{sid}:lens:{lens_id}",
                               "game": sess.game.id, "lens": lens_id})
        return jsonify({"result": result, "achieved": achieved})

    # ------------------------------------------------------------- simulate
    @app.post("/api/simulate")
    def simulate_route():
        body = request.get_json(force=True, silent=True) or {}
        gid = body.get("game")
        try:
            game = registry.create(gid, body.get("params") or {})
        except KeyError as e:
            raise ApiError(str(e), 404) from None
        stack = [c for c in body.get("stack") or [] if c in {x.id for x in game.cards()}]
        try:
            bot = game.bot(body.get("bot") or game.bots[0].id)
        except KeyError as e:
            raise ApiError(str(e)) from None
        n = max(1, min(MAX_SIM_GAMES, int(body.get("n") or 100)))
        seed = int(body.get("seed") or 0)
        mine = RulePolicy([game.card(c) for c in stack], name="Your stack")
        t0 = time.monotonic()
        res = simulate(game, [mine, game.make_policy(bot.id)], n=n, seed=seed,
                       names=["Your stack", bot.name])
        stats = res.to_json()
        stats["bot"] = bot.id
        stats["cards"] = stack
        stats["seconds"] = round(time.monotonic() - t0, 3)
        losses = sum(1 for gr in res.games if gr.winner not in (0, None))
        achieved = record({"type": "sim", "game": game.id, "bot": bot.id, "stack": stack,
                           "n": n, "wins": res.wins(0), "draws": res.draws(),
                           "losses": losses})
        return jsonify({"stats": stats, "insight": game.insight(stats), "achieved": achieved})

    # -------------------------------------------------------------- learning
    @app.get("/api/concepts")
    def concepts():
        prog = current_progress()
        learned = set(prog["concepts"])
        teaching: dict[str, list[str]] = {}
        for g in registry.games():
            for c in g.concepts:
                teaching.setdefault(c, []).append(g.id)
        for lens_obj in all_lenses().values():
            for c in lens_obj.concepts:
                teaching.setdefault(c, [])
        cards = []
        for c in all_concepts():
            d = c.to_json()
            d["learned"] = c.id in learned
            d["games"] = teaching.get(c.id, [])
            cards.append(d)
        return jsonify({"concepts": cards,
                        "chapters": [ch.to_json() for ch in CHAPTERS]})

    # --------------------------------------------------------------- profile
    @app.get("/api/profile")
    def profile():
        events = store.events()
        return jsonify({"profile": store.profile(), "progress": current_progress(),
                        "stats": progress.stats(events)})

    @app.patch("/api/profile")
    def patch_profile():
        body = request.get_json(force=True, silent=True) or {}
        prof = store.patch_profile(body)
        return jsonify({"profile": prof, "progress": current_progress()})

    @app.post("/api/profile/concept")
    def see_concept():
        body = request.get_json(force=True, silent=True) or {}
        cid = body.get("concept")
        if not cid:
            raise ApiError("missing 'concept'")
        achieved = record({"type": "concept", "id": f"concept:{cid}", "concept": cid})
        return jsonify({"achieved": achieved})

    @app.post("/api/profile/reset")
    def reset_profile():
        store.reset()
        return jsonify({"profile": store.profile(), "progress": current_progress()})

    @app.get("/api/history")
    def history():
        game = request.args.get("game") or None
        limit = int(request.args.get("limit") or 50)
        logs = request.args.get("logs") == "1"
        evs = list(reversed(store.events("game", game)))[:limit]
        if not logs:
            evs = [{k: v for k, v in e.items() if k != "log"} for e in evs]
        return jsonify({"games": evs})

    # ------------------------------------------------------------------- dev
    @app.get("/api/dev/version")
    def dev_version():
        newest = 0.0
        if dev:
            for p in WEB_DIR.rglob("*"):
                if p.is_file():
                    newest = max(newest, p.stat().st_mtime)
        return jsonify({"server": STARTED, "static": newest, "dev": dev})

    return app
