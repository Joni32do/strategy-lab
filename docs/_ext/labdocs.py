"""Generate the game catalog and concept pages from the code at build time.

Writes ``docs/generated/games.md`` and ``docs/generated/concepts.md`` so
the documentation always matches the registered games and concept cards.
"""

from __future__ import annotations

from pathlib import Path


def _games_md() -> str:
    from strategy_lab.core import registry
    from strategy_lab.learn.curriculum import CHAPTERS
    from strategy_lab.lenses import lenses_for

    games = registry.games()
    out = ["# Game catalog", "",
           "Generated from the registry: every class under `strategy_lab/games` with an `id`.", ""]
    for ch in CHAPTERS:
        members = [g for g in games if (g.draft and ch.id == "workbench") or (not g.draft and g.chapter == ch.id)]
        if not members:
            continue
        out += [f"## {ch.title}: {ch.subtitle}", "", f"*{ch.question}*", "", ch.intro, ""]
        for cls in members:
            try:
                g = cls()
            except Exception as e:  # noqa: BLE001
                out += [f"### {cls.name}", "", f"Could not instantiate: {e}", ""]
                continue
            fam = g.family()
            out += [f"### {g.name}", "", f"*{g.tagline}*", ""]
            out += [f"- **Class:** `{cls.__module__}.{cls.__name__}`",
                    f"- **Lineage:** {' > '.join(f'`{n}`' for n in g.lineage())}",
                    f"- **Family:** {fam['name']}",
                    f"- **Players:** {g.num_players}",
                    f"- **Concepts:** {', '.join(g.concepts) or '-'}",
                    f"- **Lenses:** {', '.join(l.title for l in lenses_for(g)) or '-'}", ""]
            if g.rulebook:
                out += [g.rulebook.summary, ""]
                for i, (t, x) in enumerate(g.rulebook.steps, 1):
                    out.append(f"{i}. **{t}.** {x}")
                out.append("")
                if g.rulebook.source:
                    out += [f"Rules source: <{g.rulebook.source}>", ""]
            if g.cards():
                out += ["**Rule cards:** " + ", ".join(f"{c.name} ({c.kind})" for c in g.cards()), ""]
            if g.bots:
                out += ["**Bots:** " + ", ".join(f"{b.name} ({b.stars}*)" for b in g.bots), ""]
    broken = registry.broken()
    if broken:
        out += ["## Modules that failed to import", ""]
        out += [f"- `{m}`" for m in broken]
    return "\n".join(out) + "\n"


def _concepts_md() -> str:
    from strategy_lab.learn.concepts import all_concepts
    from strategy_lab.learn.curriculum import CHAPTERS

    concepts = all_concepts()
    out = ["# Concept cards", "", "The cheatsheet of the app, generated from "
           "`strategy_lab/learn/concepts.py` and `concept_texts.py`.", ""]
    for ch in CHAPTERS:
        cards = [c for c in concepts if c.chapter == ch.id]
        if not cards:
            continue
        out += [f"## {ch.title}", ""]
        for c in cards:
            out += [f"### {c.title}", "", f"**{c.short}**", ""]
            if c.formula:
                out += ["$$", c.formula, "$$", ""]
            if c.body:
                out += [c.body, ""]
            if c.example:
                out += [f"*Example:* {c.example}", ""]
    return "\n".join(out) + "\n"


def generate(app) -> None:
    gen = Path(app.srcdir) / "generated"
    gen.mkdir(exist_ok=True)
    (gen / "games.md").write_text(_games_md())
    (gen / "concepts.md").write_text(_concepts_md())


def setup(app):
    app.connect("builder-inited", generate)
    return {"version": "1.0", "parallel_read_safe": True}
