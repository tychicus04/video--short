import json
import os

import pytest
from starlette.testclient import TestClient

from vshort import queue, web
from vshort.run import Run


@pytest.fixture
def run_s(tmp_path, monkeypatch):
    """runs_dir() -> tmp_path, holding one finished run `s` (brief.en.md newer than brief.vi.md)."""
    monkeypatch.setattr(queue, "runs_dir", lambda: tmp_path)
    d = tmp_path / "s"
    d.mkdir()
    (d / "final.mp4").write_bytes(b"v" * 1000)
    (d / "brief.vi.md").write_text("# Brief VI", encoding="utf-8")
    (d / "brief.en.md").write_text("# Brief EN", encoding="utf-8")
    os.utime(d / "brief.vi.md", (1000, 1000))
    os.utime(d / "brief.en.md", (2000, 2000))
    (d / "sentences.en.json").write_text(json.dumps([{"id": 1, "start": 0, "end": 2, "en": "Hello there."},
                                                     {"id": 2, "start": 2, "end": 4, "en": "Bye."}]))
    (d / "script.vi.json").write_text(json.dumps([{"id": 1, "phrases": "Xin | chào"}, {"id": 2, "phrases": "Tạm | biệt", "note": "n"}]),
                                      encoding="utf-8")
    (d / "auto.json").write_text(json.dumps({"state": "done", "message": "", "round": 0, "pid": 1}))
    return Run(d)


@pytest.fixture
def client(run_s, monkeypatch):
    monkeypatch.setattr(web, "token", lambda: "bi-mat")
    return TestClient(web.app)


def test_state_lists_runs_and_reports_no_write(client):
    j = client.get("/api/state").json()
    assert [r["slug"] for r in j["rows"]] == ["s"] and j["can_write"] is False and j["token_set"] is True
    assert j["relogin"] == [] and j["max_running"] == web.config()["web_max_running"]


def test_video_supports_range_and_download(client):
    r = client.get("/files/s/final.mp4", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100 and r.headers["accept-ranges"] == "bytes"
    assert 's.mp4' in client.get("/files/s/final.mp4?download=1").headers["content-disposition"]


def test_files_refuse_other_names_and_escapes(client):
    for url in ("/files/s/brief.vi.md", "/files/s/..%2F..%2Fetc%2Fpasswd", "/files/..%2Fs/final.mp4", "/files/NOPE/final.mp4"):
        assert client.get(url).status_code == 404


def test_video_is_409_while_the_run_is_locked(client, run_s):
    run_s.file("auto.lock").write_text(str(os.getpid()))
    assert client.get("/files/s/final.mp4").status_code == 409


def test_login_sets_cookie_only_with_the_right_token(client, monkeypatch):
    assert client.post("/api/login", json={"token": "sai"}).status_code == 403
    assert client.post("/api/login", json={"token": "bi-mat"}).status_code == 204
    assert client.get("/api/state").json()["can_write"] is True
    monkeypatch.setattr(web, "token", lambda: "doi-ma")           # token changed on the server
    assert client.get("/api/state").json()["can_write"] is False


def test_login_cookie_is_httponly_strict_for_a_year_and_not_secure(client):
    c = client.post("/api/login", json={"token": "bi-mat"}).headers["set-cookie"].lower()
    assert "httponly" in c and "samesite=strict" in c and "max-age=31536000" in c and "secure" not in c


def test_login_works_with_a_code_outside_latin1(client, monkeypatch):
    monkeypatch.setattr(web, "token", lambda: "mã-đẹp 100%")
    assert client.post("/api/login", json={"token": "mã-đẹp 100%"}).status_code == 204
    assert client.get("/api/state").json()["can_write"] is True


def test_login_never_matches_when_the_server_has_no_token(client, monkeypatch):
    monkeypatch.setattr(web, "token", lambda: "")
    assert client.post("/api/login", json={"token": ""}).status_code == 403
    assert client.post("/api/login", json="không phải object").status_code == 403
    assert client.get("/api/state").json()["token_set"] is False


def test_token_is_read_from_the_file_and_stripped(tmp_path, monkeypatch):
    f = tmp_path / "t"
    monkeypatch.setattr(web, "config", lambda: {"web_token_file": str(f)})
    assert web.token() == ""                                       # no file yet
    f.write_text("  abc\n")
    assert web.token() == "abc"


def test_detail_joins_translation_and_flags_stale_english_brief(client, run_s):
    j = client.get("/api/runs/s").json()
    assert j["brief_en_stale"] is False
    os.utime(run_s.file("brief.vi.md"), (3000, 3000))              # brief.vi.md newer than brief.en.md
    j = client.get("/api/runs/s").json()
    assert j["brief_en_stale"] is True and j["translation"][0] == {"id": 1, "en": "Hello there.", "phrases": "Xin | chào", "note": ""}


def test_detail_of_a_finished_run(client, run_s):
    run_s.file("auto.log").write_text("\n".join(f"dòng {i}" for i in range(80)), encoding="utf-8")
    run_s.file("cost.json").write_text(json.dumps([{"step": "x", "cost_usd": 0.5}]))
    j = client.get("/api/runs/s").json()
    assert j["row"]["slug"] == "s" and j["row"]["state"] == "done" and j["locked"] is False and j["video"] is True
    assert j["brief_vi"] == "# Brief VI" and j["brief_en"] == "# Brief EN" and j["review_md"] is None and j["proposed"] is None
    assert j["cost"] == [{"step": "x", "cost_usd": 0.5}]
    assert j["log_tail"].splitlines() == [f"dòng {i}" for i in range(30, 80)]
    run_s.file("auto.lock").write_text(str(os.getpid()))
    j = client.get("/api/runs/s").json()
    assert j["locked"] is True and j["video"] is False


def test_detail_proposal_and_unknown_runs(client, run_s):
    run_s.file("script.proposed.json").write_text(json.dumps([{"id": 2, "phrases": "Tạm | biệt nhé", "note": "sửa"}]), encoding="utf-8")
    assert client.get("/api/runs/s").json()["proposed"] == [{"id": 2, "phrases": "Tạm | biệt nhé", "note": "sửa"}]
    for slug in ("nope", "..", "S"):
        r = client.get(f"/api/runs/{slug}")
        assert r.status_code == 404 and r.json()["error"]


def test_detail_survives_broken_files_and_never_follows_links_out(client, run_s, tmp_path):
    run_s.file("script.vi.json").write_text("{không phải json")
    run_s.file("cost.json").write_text('{"a": 1}')                  # JSON, but not a list of lines
    secret = tmp_path.parent / "secret.log"
    secret.write_text("bí mật")
    run_s.file("auto.log").symlink_to(secret)
    j = client.get("/api/runs/s").json()
    assert j["translation"] is None and j["cost"] == [] and j["log_tail"] == ""


def test_unknown_paths_answer_in_vietnamese(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]
