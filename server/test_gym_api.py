"""Sanity tests for the /api/gym/envs endpoint.

Run: uv run python server/test_gym_api.py   (in-process, no server needed).
"""
from app import app


def _get_envs():
    client = app.test_client()
    resp = client.get("/api/gym/envs")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
    return resp.get_json()


def test_shape_and_source():
    d = _get_envs()
    assert d["source"] == "gymnasium", d.get("source")
    assert isinstance(d["version"], str) and d["version"], "version must be non-empty"
    print(f"ok  source=gymnasium version={d['version']}")


def test_groups():
    d = _get_envs()
    groups = d["groups"]
    assert isinstance(groups, list) and len(groups) >= 3, f"need >=3 groups, got {len(groups)}"
    for g in groups:
        assert g["namespace"], "every group needs a namespace"
        envs = g["envs"]
        assert isinstance(envs, list) and envs, f"group {g['namespace']} has no envs"
        assert all(isinstance(e, str) for e in envs), f"group {g['namespace']} has non-string envs"
    counts = {g["namespace"]: len(g["envs"]) for g in groups}
    print(f"ok  {len(groups)} groups: {counts}")


def test_cartpole_present():
    d = _get_envs()
    all_envs = [e for g in d["groups"] for e in g["envs"]]
    assert "CartPole-v1" in all_envs, "CartPole-v1 missing from registry"
    print("ok  CartPole-v1 present in the registry")


def test_open_spiel_key():
    d = _get_envs()
    spiel = d["open_spiel"]
    assert isinstance(spiel, dict) and isinstance(spiel["available"], bool), spiel
    print(f"ok  open_spiel key present: available={spiel['available']}")


if __name__ == "__main__":
    test_shape_and_source()
    test_groups()
    test_cartpole_present()
    test_open_spiel_key()
    print("\nALL PASSED")
