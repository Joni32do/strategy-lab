"""Config/skin + static-routing API tests, in-process.

Run: <repo>/.venv/bin/python server/test_app.py
"""
from app import app, build_arg_parser, SKIN_IDS


def main():
    c = app.test_client()

    # ---- /api/config ----
    r = c.get("/api/config")
    assert r.status_code == 200, r.status_code
    d = r.get_json()
    assert d["skin"] in SKIN_IDS, d
    assert d["skins"] == SKIN_IDS, d
    print("ok  /api/config: skin=%r skins=%r" % (d["skin"], d["skins"]))

    # ---- "/" serves the gallery (index.html), not catan.html ----
    r = c.get("/")
    assert r.status_code == 200, r.status_code
    body = r.get_data(as_text=True)
    assert "UI.init" in body, "index.html body did not contain UI.init"
    print("ok  GET / serves index.html (gallery)")

    # ---- "/catan.html" still reachable via the catch-all ----
    r = c.get("/catan.html")
    assert r.status_code == 200, r.status_code
    body = r.get_data(as_text=True)
    assert "catan-lab.js" in body, "catan.html body did not contain catan-lab.js"
    print("ok  GET /catan.html still reachable")

    # ---- argparse ----
    args = build_arg_parser().parse_args([])
    assert args.skin == "original", args.skin
    print("ok  build_arg_parser(): default skin=%r" % args.skin)

    args = build_arg_parser().parse_args(["--skin", "minimal"])
    assert args.skin == "minimal", args.skin
    print("ok  build_arg_parser(): --skin minimal accepted")

    try:
        build_arg_parser().parse_args(["--skin", "bogus"])
        raise AssertionError("expected SystemExit for bogus skin choice")
    except SystemExit:
        print("ok  build_arg_parser(): --skin bogus raises SystemExit")

    print("ALL PASSED")


if __name__ == "__main__":
    main()
