import json
import os
import subprocess
import time

import pytest
from starlette.testclient import TestClient

from vshort import auto, cli, queue, web
from vshort.cli import RELOGIN
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
def client_anon(run_s, monkeypatch):
    monkeypatch.setattr(web, "token", lambda: "bi-mat")
    return TestClient(web.app)


@pytest.fixture
def client(client_anon):
    """Logged in: its own cookie jar. Never `with TestClient(...)` here: that starts the real queue loop."""
    c = TestClient(web.app)
    assert c.post("/api/login", json={"token": "bi-mat"}).status_code == 204
    return c


SENTENCES = [{"id": 1, "start": 0, "end": 2, "en": "Hello there."}, {"id": 2, "start": 2, "end": 4, "en": "Bye."}]
SCRIPT = [{"id": 1, "phrases": "Xin | chào"}, {"id": 2, "phrases": "Tạm | biệt", "note": "n"}]


def make_run(tmp_path, slug, state, files=None, message=""):
    d = tmp_path / slug
    d.mkdir()
    (d / "auto.json").write_text(json.dumps({"state": state, "message": message, "round": 0, "pid": 1}))
    for name, data in (files or {}).items():
        (d / name).write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return Run(d)


@pytest.fixture
def run_wait_script(run_s, tmp_path):
    return make_run(tmp_path, "w", "wait_script", {"sentences.en.json": SENTENCES, "script.vi.json": SCRIPT})


@pytest.fixture
def run_wait_brief(run_s, tmp_path):
    return make_run(tmp_path, "b", "wait_brief", {"brief.vi.md": "VI cũ", "brief.en.md": "EN cũ"})


@pytest.fixture
def run_relogin(run_s, tmp_path):
    return make_run(tmp_path, "e", "error", message=RELOGIN)


def fake_vshort(monkeypatch, fails=None):
    """`web.vshort` records its args and answers 0, or 1 with the given stderr for the commands named in `fails`."""
    seen = []

    def fake(args):
        seen.append(args)
        err = (fails or {}).get(args[0])
        return subprocess.CompletedProcess(args, 0 if err is None else 1, "", err or "")

    monkeypatch.setattr(web, "vshort", fake)
    return seen


@pytest.fixture
def calls(monkeypatch):
    return fake_vshort(monkeypatch)


@pytest.fixture
def calls_with_check_failing(monkeypatch):
    return fake_vshort(monkeypatch, {"check": "câu 2: cụm quá rộng\n\n  Câu 3: thiếu \n"})


def test_state_lists_runs_and_reports_no_write(client_anon):
    j = client_anon.get("/api/state").json()
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


def test_login_sets_cookie_only_with_the_right_token(client_anon, monkeypatch):
    assert client_anon.post("/api/login", json={"token": "sai"}).status_code == 403
    assert client_anon.post("/api/login", json={"token": "bi-mat"}).status_code == 204
    assert client_anon.get("/api/state").json()["can_write"] is True
    monkeypatch.setattr(web, "token", lambda: "doi-ma")           # token changed on the server
    assert client_anon.get("/api/state").json()["can_write"] is False


def test_login_cookie_is_httponly_strict_for_a_year_and_not_secure(client_anon):
    c = client_anon.post("/api/login", json={"token": "bi-mat"}).headers["set-cookie"].lower()
    assert "httponly" in c and "samesite=strict" in c and "max-age=31536000" in c and "secure" not in c


def test_login_works_with_a_code_outside_latin1(client_anon, monkeypatch):
    monkeypatch.setattr(web, "token", lambda: "mã-đẹp 100%")
    assert client_anon.post("/api/login", json={"token": "mã-đẹp 100%"}).status_code == 204
    assert client_anon.get("/api/state").json()["can_write"] is True


def test_login_never_matches_when_the_server_has_no_token(client_anon, monkeypatch):
    monkeypatch.setattr(web, "token", lambda: "")
    assert client_anon.post("/api/login", json={"token": ""}).status_code == 403
    assert client_anon.post("/api/login", json="không phải object").status_code == 403
    assert client_anon.get("/api/state").json()["token_set"] is False


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


# --- the write side and the queue loop -------------------------------------------------------------------------------

def test_writes_need_the_code(client_anon):
    assert client_anon.post("/api/queue", json={"items": [{"slug": "a", "topic": "A"}], "auto": False}).status_code == 403


def test_every_write_route_needs_the_code(client_anon, calls):
    for url in ("/api/queue", "/api/queue/remove", "/api/resume", "/api/runs/s/brief", "/api/runs/s/brief_en", "/api/runs/s/script",
                "/api/runs/s/proposal", "/api/runs/s/approve", "/api/runs/s/retry"):
        r = client_anon.post(url, json={})
        assert (r.status_code, r.json()) == (403, {"error": "Cần mã truy cập"}), url
    assert calls == [] and not queue.runs_dir().joinpath("queue.json").exists()


def test_queue_add_then_tick_starts_up_to_the_limit(client, calls, monkeypatch):
    cfg = web.config()
    monkeypatch.setattr(web, "config", lambda: cfg | {"web_max_running": 2})  # web.py: `from vshort.run import config`
    items = [{"slug": s, "topic": s.upper()} for s in ("a", "b", "c")]
    assert client.post("/api/queue", json={"items": items, "auto": True}).json() == {"errors": ["", "", ""]}
    web.tick()
    assert calls == [["auto", "a", "--topic=A", "--auto"], ["auto", "b", "--topic=B", "--auto"]]
    assert [i["slug"] for i in queue.load_queue().new] == ["c"]


def test_approve_requeues_once_and_tick_resumes_it(client, calls, run_wait_script):
    assert client.post("/api/runs/w/approve", json={"what": "script"}).status_code == 204
    client.post("/api/runs/w/approve", json={"what": "script"})
    assert queue.load_queue().resume == ["w"]
    web.tick()
    assert calls[-1] == ["auto", str(queue.run_path("w"))]


def test_locked_run_refuses_edits(client, run_s):
    run_s.file("auto.lock").write_text(str(os.getpid()))
    assert client.post("/api/runs/s/script", json={"rows": []}).status_code == 409


def test_script_save_runs_check_and_reports_problems(client, calls_with_check_failing, run_wait_script):
    rows = [{"id": 1, "phrases": "Xin | chào", "note": ""}, {"id": 2, "phrases": "Tạm | biệt", "note": "n"}]
    for bad in (rows[:1], rows + rows[:1], [{**rows[0], "id": 3}, rows[1]]):          # a missing id, a repeated one, an unknown one
        assert client.post("/api/runs/w/script", json={"rows": bad}).status_code == 400
    assert calls_with_check_failing == [] and json.loads(run_wait_script.file("script.vi.json").read_text(encoding="utf-8")) == SCRIPT
    j = client.post("/api/runs/w/script", json={"rows": rows}).json()
    assert j == {"ok": False, "problems": ["câu 2: cụm quá rộng", "Câu 3: thiếu"]}
    assert calls_with_check_failing == [["check", str(queue.run_path("w"))]]
    assert json.loads(run_wait_script.file("script.vi.json").read_text(encoding="utf-8")) == SCRIPT   # empty note is not written


def test_script_save_of_good_rows_says_ok(client, calls, run_wait_script):
    rows = [{"id": 1, "phrases": "Chào bạn", "note": ""}, {"id": 2, "phrases": "Tạm biệt"}]
    assert client.post("/api/runs/w/script", json={"rows": rows}).json() == {"ok": True, "problems": []}
    assert json.loads(run_wait_script.file("script.vi.json").read_text(encoding="utf-8")) == [
        {"id": 1, "phrases": "Chào bạn"}, {"id": 2, "phrases": "Tạm biệt"}]


def test_script_refuses_odd_shapes(client, calls, run_wait_script):
    for rows in ("không phải list", [1], [{"id": "1", "phrases": "x"}], [{"id": True, "phrases": "x"}], [{"id": [1], "phrases": "x"}],
                 [{"id": 1, "phrases": 5}, {"id": 2, "phrases": "x"}], [{"id": 1, "phrases": "x", "note": 5}, {"id": 2, "phrases": "x"}]):
        r = client.post("/api/runs/w/script", json={"rows": rows})
        assert r.status_code == 400 and r.json()["error"], rows
    assert calls == []


def test_brief_save_syncs_english_with_a_cheap_agent(client, run_wait_brief, monkeypatch):
    seen = []
    monkeypatch.setattr(auto, "run_claude", lambda run, step, agent, prompt, t: seen.append((step, agent, prompt))
                        or run.file("brief.en.md").write_text("EN mới") or "xong")
    j = client.post("/api/runs/b/brief", json={"vi": "VI mới"}).json()
    assert j == {"brief_en": "EN mới", "brief_en_stale": False}
    assert seen[0][:2] == ("brief_sync", "vs-researcher") and "+VI mới" in seen[0][2]


def test_brief_sync_prompt_names_the_run_and_carries_the_diff(client, run_wait_brief, monkeypatch):
    seen = []
    monkeypatch.setattr(auto, "run_claude", lambda run, step, agent, prompt, t: seen.append((prompt, t)) or "xong")
    client.post("/api/runs/b/brief", json={"vi": "VI mới"})
    prompt, timeout = seen[0]
    assert "-VI cũ" in prompt and f"RUN={queue.run_path('b')}." in prompt and timeout == 600
    assert run_wait_brief.file("brief.vi.md").read_text(encoding="utf-8") == "VI mới"


def test_brief_save_without_a_change_neither_writes_nor_asks_the_agent(client, run_wait_brief, monkeypatch):
    monkeypatch.setattr(auto, "run_claude", lambda *a: pytest.fail("no change, no agent"))
    os.utime(run_wait_brief.file("brief.vi.md"), (1000, 1000))
    os.utime(run_wait_brief.file("brief.en.md"), (2000, 2000))
    assert client.post("/api/runs/b/brief", json={"vi": "VI cũ"}).json() == {"brief_en": "EN cũ", "brief_en_stale": False}
    assert run_wait_brief.file("brief.vi.md").stat().st_mtime == 1000


def test_brief_agent_failure_is_a_502_and_the_vietnamese_is_kept(client, run_wait_brief, monkeypatch):
    def broken(*a):
        raise auto.AgentError("vs-researcher chạy quá 10 phút ở bước brief_sync")
    monkeypatch.setattr(auto, "run_claude", broken)
    os.utime(run_wait_brief.file("brief.en.md"), (2000, 2000))
    r = client.post("/api/runs/b/brief", json={"vi": "VI mới"})
    assert r.status_code == 502 and "vs-researcher chạy quá 10 phút" in r.json()["error"]
    assert run_wait_brief.file("brief.vi.md").read_text(encoding="utf-8") == "VI mới"
    assert client.get("/api/runs/b").json()["brief_en_stale"] is True


def test_brief_en_save_clears_the_stale_flag(client, run_wait_brief):
    os.utime(run_wait_brief.file("brief.en.md"), (2000, 2000))
    os.utime(run_wait_brief.file("brief.vi.md"), (3000, 3000))
    assert client.get("/api/runs/b").json()["brief_en_stale"] is True
    assert client.post("/api/runs/b/brief_en", json={"en": "EN đã sửa"}).status_code == 204
    j = client.get("/api/runs/b").json()
    assert j["brief_en"] == "EN đã sửa" and j["brief_en_stale"] is False
    assert client.post("/api/runs/b/brief_en", json={"en": 5}).status_code == 400


def test_proposal_use_copies_it_and_either_way_removes_it(client, run_wait_script):
    prop = [{"id": 1, "phrases": "Chào các bạn"}, {"id": 2, "phrases": "Tạm biệt", "note": "sửa"}]
    for use in (True, False):
        run_wait_script.file("script.proposed.json").write_text(json.dumps(prop), encoding="utf-8")
        run_wait_script.file("script.vi.json").write_text(json.dumps(SCRIPT), encoding="utf-8")
        assert client.post("/api/runs/w/proposal", json={"use": use}).status_code == 204
        assert not run_wait_script.file("script.proposed.json").exists()
        assert json.loads(run_wait_script.file("script.vi.json").read_text(encoding="utf-8")) == (prop if use else SCRIPT)
    assert client.post("/api/runs/w/proposal", json={"use": True}).status_code == 400      # nothing left to use
    assert client.post("/api/runs/w/proposal", json={"use": False}).status_code == 204     # removing twice is fine
    assert client.post("/api/runs/w/proposal", json={"use": "có"}).status_code == 400


def test_approve_failure_is_a_400_with_the_cli_message_and_queues_nothing(client, monkeypatch, run_wait_script):
    calls = fake_vshort(monkeypatch, {"approve": "còn script.proposed.json — chép bản đề xuất hoặc xóa nó trước\n"})
    r = client.post("/api/runs/w/approve", json={"what": "script"})
    assert r.status_code == 400 and r.json() == {"error": "còn script.proposed.json — chép bản đề xuất hoặc xóa nó trước"}
    assert queue.load_queue().resume == [] and calls == [["approve", str(queue.run_path("w")), "script"]]
    assert client.post("/api/runs/w/approve", json={"what": "xóa"}).status_code == 400
    assert client.post("/api/runs/w/approve", json={}).status_code == 400
    assert len(calls) == 1                                        # the CLI is not asked about a step that does not exist


def test_retry_only_for_a_run_that_stopped(client, calls, run_s, run_relogin):
    assert client.post("/api/runs/s/retry").status_code == 400    # done
    assert queue.load_queue().resume == []
    assert client.post("/api/runs/e/retry").status_code == 204    # error
    assert queue.load_queue().resume == ["e"]
    run_s.file("auto.json").write_text(json.dumps({"state": "running", "message": "", "round": 0, "pid": 0}))
    assert client.post("/api/runs/s/retry").status_code == 204    # "running" but the process is gone: dead
    assert queue.load_queue().resume == ["e", "s"]


def test_run_routes_check_the_slug_before_the_lock_before_the_body(client, run_s):
    for slug in ("nope", "..", "S"):
        assert client.post(f"/api/runs/{slug}/brief_en", json={"en": "x"}).status_code == 404
    client.post("/api/queue", json={"items": [{"slug": "a", "topic": "A"}], "auto": False})
    assert client.post("/api/runs/a/brief_en", json={"en": "x"}).status_code == 404       # waiting in the queue: no folder to write to
    assert not queue.runs_dir().joinpath("a").exists()
    run_s.file("auto.lock").write_text(str(os.getpid()))
    assert client.post("/api/runs/s/brief_en", content=b"{not json").status_code == 409
    run_s.file("auto.lock").unlink()
    assert client.post("/api/runs/s/brief_en", content=b"{not json").status_code == 400
    assert client.post("/api/runs/s/brief_en", json=["en"]).status_code == 400


def test_queue_refuses_odd_shapes_and_keeps_the_errors_in_order(client):
    for body in ({"items": "x", "auto": False}, {"items": [1], "auto": False}, {"items": [], "auto": "có"}):
        r = client.post("/api/queue", json=body)
        assert r.status_code == 400 and r.json()["error"], body
    r = client.post("/api/queue", json={"items": [{"slug": "a", "topic": 5}, {"slug": "s", "topic": "S"}, {"slug": "b", "topic": "B"}],
                                        "auto": False})
    assert r.status_code == 400 and [bool(e) for e in r.json()["errors"]] == [True, True, False]
    assert queue.load_queue().new == []                           # all or nothing


def test_queue_remove_only_takes_topics_that_have_not_started(client):
    client.post("/api/queue", json={"items": [{"slug": "a", "topic": "A"}, {"slug": "b", "topic": "B"}], "auto": False})
    assert client.post("/api/queue/remove", json={"slug": "a"}).status_code == 204
    assert [i["slug"] for i in queue.load_queue().new] == ["b"]
    for slug in ("a", "s", 5):                                    # gone already, a video that exists, not a slug
        assert client.post("/api/queue/remove", json={"slug": slug}).status_code in (400, 404)
    assert [i["slug"] for i in queue.load_queue().new] == ["b"] and queue.runs_dir().joinpath("s").is_dir()


def test_relogin_pauses_the_queue_until_resume(client, calls, run_relogin):
    client.post("/api/queue", json={"items": [{"slug": "a", "topic": "A"}], "auto": False})
    web.tick(); assert calls == []
    assert client.post("/api/resume").status_code == 204
    web.tick(); assert calls[0] == ["auto", str(queue.run_path("e"))]


def test_tick_counts_the_runs_that_are_already_going(client, calls, run_s, monkeypatch):
    cfg = web.config()
    monkeypatch.setattr(web, "config", lambda: cfg | {"web_max_running": 1})
    run_s.file("auto.json").write_text(json.dumps({"state": "running", "message": "", "round": 0, "pid": os.getpid()}))
    client.post("/api/queue", json={"items": [{"slug": "a", "topic": "A"}], "auto": False})
    web.tick()
    assert calls == [] and [i["slug"] for i in queue.load_queue().new] == ["a"]


def test_tick_drops_an_item_the_cli_refuses_and_logs_one_line(client, monkeypatch):
    calls = fake_vshort(monkeypatch, {"auto": "đã có video\nchạy tiếp bằng `vshort auto`\n"})
    client.post("/api/queue", json={"items": [{"slug": "a", "topic": "A"}, {"slug": "b", "topic": "B"}], "auto": False})
    web.tick()
    assert [c[1] for c in calls] == ["a", "b"] and queue.load_queue().new == []     # both asked, both gone
    log = (queue.runs_dir() / "web.log").read_text(encoding="utf-8").splitlines()
    assert len(log) == 2 and "a" in log[0] and "đã có video chạy tiếp bằng `vshort auto`" in log[0]


def test_one_item_that_cannot_be_started_does_not_block_the_queue(client, monkeypatch):
    seen = []

    def fake(args):                                               # what subprocess.run does with a NUL in an argument
        seen.append(args)
        if any("\x00" in a for a in args):
            raise ValueError("embedded null byte")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(web, "vshort", fake)
    assert client.post("/api/queue", json={"items": [{"slug": "a", "topic": "x\x00y"}, {"slug": "b", "topic": "B"}], "auto": False}).status_code == 200
    web.tick()
    assert [c[1] for c in seen] == ["a", "b"] and queue.load_queue().new == []     # a is dropped, b started in the same tick
    log = (queue.runs_dir() / "web.log").read_text(encoding="utf-8").splitlines()
    assert len(log) == 1 and "a" in log[0] and "ValueError" in log[0]


def test_a_topic_that_looks_like_an_option_is_passed_as_one_argument(client, calls, monkeypatch, capsys):
    client.post("/api/queue", json={"items": [{"slug": "g", "topic": "-gravity"}], "auto": False})
    web.tick()
    assert calls == [["auto", "g", "--topic=-gravity"]] and queue.load_queue().new == []
    got = []
    monkeypatch.setattr(cli, "cmd_auto", lambda a: got.append(a.topic) or 0)
    assert cli.main(calls[0]) == 0 and got == ["-gravity"]        # argparse reads it as the topic
    with pytest.raises(SystemExit):                               # the two-argument form is what failed
        cli.main(["auto", "g", "--topic", "-gravity"])
    capsys.readouterr()


def test_approve_only_when_the_video_waits_for_that_step(client, calls, run_s, run_wait_script, run_wait_brief):
    for slug, what in (("s", "script"), ("w", "brief"), ("b", "script")):      # done; waits for the translation; waits for the brief
        r = client.post(f"/api/runs/{slug}/approve", json={"what": what})
        assert r.status_code == 400 and r.json()["error"], (slug, what)
    assert calls == [] and queue.load_queue().resume == []
    assert client.post("/api/runs/w/approve", json={"what": "script"}).status_code == 204
    again = client.post("/api/runs/w/approve", json={"what": "script"})        # a double click: it is queued now
    assert again.status_code == 400 and again.json()["error"]
    assert queue.load_queue().resume == ["w"] and len(calls) == 1


def test_a_run_that_is_going_refuses_writes_before_it_takes_the_lock(client, calls, run_wait_script):
    """`vshort auto` has written auto.json (running, its child's pid) but the child has not made auto.lock yet."""
    run_wait_script.file("auto.json").write_text(json.dumps({"state": "running", "message": "", "round": 0, "pid": os.getpid()}))
    r = client.post("/api/runs/w/approve", json={"what": "script"})
    assert (r.status_code, r.json()) == (409, {"error": "Video đang chạy, đợi nó dừng rồi sửa"})
    assert client.post("/api/runs/w/script", json={"rows": []}).status_code == 409
    assert calls == [] and queue.load_queue().resume == [] and client.get("/api/runs/w").json()["locked"] is True


def test_tick_survives_a_cli_that_hangs(client, monkeypatch):
    def hangs(args):
        raise subprocess.TimeoutExpired(args, 120)
    monkeypatch.setattr(web, "vshort", hangs)
    client.post("/api/queue", json={"items": [{"slug": "a", "topic": "A"}], "auto": False})
    web.tick()
    assert queue.load_queue().new == [] and "a" in (queue.runs_dir() / "web.log").read_text(encoding="utf-8")


def test_vshort_runs_the_cli_with_a_list_of_arguments(monkeypatch):
    seen = {}
    monkeypatch.setattr(web.subprocess, "run", lambda cmd, **kw: seen.update(cmd=cmd, kw=kw))
    web.vshort(["check", "/x"])
    assert seen["cmd"][1:] == ["-m", "vshort.cli", "check", "/x"] and seen["kw"] == {
        "cwd": web.ROOT, "capture_output": True, "text": True, "timeout": 120}


def test_the_loop_keeps_going_after_tick_fails(run_s, monkeypatch):
    done = []

    def tick():
        done.append(1)
        if len(done) == 1:
            raise RuntimeError("queue.json hỏng")

    monkeypatch.setattr(web, "tick", tick)
    monkeypatch.setattr(web, "TICK", 0.01)
    with TestClient(web.app):                                     # the only test that runs the lifespan, with tick replaced
        for _ in range(200):
            if len(done) >= 3:
                break
            time.sleep(0.01)
    assert len(done) >= 3 and "RuntimeError" in (queue.runs_dir() / "web.log").read_text(encoding="utf-8")
