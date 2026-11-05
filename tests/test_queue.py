import json
import os

import pytest

from vshort import queue
from vshort.run import Run


@pytest.fixture
def tmp_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(queue, "runs_dir", lambda: tmp_path)
    (tmp_path / "five-solas").mkdir()
    return tmp_path


def make_run(root, slug, auto=None, run=None, **files):
    """A run folder: auto.json / run.json from the arguments, any other file as name=json (name uses _ for the dot)."""
    d = root / slug
    d.mkdir()
    if auto is not None:
        (d / "auto.json").write_text(auto if isinstance(auto, str) else json.dumps({"round": 0, "pid": 1, "message": "", **auto}))
    if run is not None:
        (d / "run.json").write_text(json.dumps(run))
    for name, data in files.items():
        (d / f"{name}.json").write_text(data if isinstance(data, str) else json.dumps(data))
    return d


def test_slugify_and_validation():
    assert queue.slugify("Five Solas: năm chữ “chỉ” của Cải cách") == "five-solas-nam-chu-chi-cua-cai-cach"
    assert queue.slugify("https://www.reformationbiblecollege.org/blog/the-five-solas") == "the-five-solas"
    assert queue.slugify("🙂 !!!") == ""
    assert len(queue.slugify("a-" * 80)) <= 60
    with pytest.raises(ValueError):
        queue.run_path("../etc")


def test_slugify_cuts_at_a_word_and_matches_the_slug_rule():
    s = queue.slugify("Đức Chúa Trời " * 10)
    assert s.startswith("duc-chua-troi-") and len(s) <= 60 and not s.endswith("-") and queue.SLUG_RE.fullmatch(s)
    assert queue.slugify("https://example.com/a/b/") == "b" and queue.slugify("https://example.com") == "example-com"
    assert queue.slugify("https://vi.wikipedia.org/wiki/C%E1%BA%A3i_c%C3%A1ch") == "cai-cach"
    assert queue.slugify("abcdefg " * 10) == "-".join(["abcdefg"] * 7)  # the 60th character is mid-word: that word goes
    assert queue.slugify("x" * 100) == "x" * 60  # no dash to cut at
    assert not queue.SLUG_RE.match("abc\n")  # `$` alone would let a trailing newline through
    with pytest.raises(ValueError):
        queue.run_path("abc\n")


def test_add_topics_all_or_nothing(tmp_runs):          # tmp_runs: runs_dir() -> tmp_path; tmp_path/"five-solas" exists
    q = queue.Queue([], [])
    errs = queue.add_topics(q, [{"slug": "a", "topic": "A"}, {"slug": "a", "topic": "A2"},
                                {"slug": "", "topic": "🙂"}, {"slug": "five-solas", "topic": "x"},
                                {"slug": "b", "topic": "x" * 501}], auto=True)
    assert errs[0] == "" and all(errs[1:]) and q.new == []
    assert queue.add_topics(q, [{"slug": "a", "topic": "A"}], auto=True) == [""] and q.new[0]["auto"] is True


def test_add_topics_rejects_what_is_already_queued_or_malformed(tmp_runs):
    q = queue.Queue([], [])
    assert queue.add_topics(q, [{"slug": "a", "topic": " A "}], auto=False) == [""]
    assert q.new[0]["topic"] == "A" and q.new[0]["added"] > 0
    errs = queue.add_topics(q, [{"slug": "a", "topic": "A"}, {"slug": "Bad_Slug", "topic": "x"},
                                {"slug": "c", "topic": "   "}, {"slug": 5, "topic": "x"}, {"slug": "d"}], auto=False)
    assert all(errs) and len(q.new) == 1
    assert queue.add_topics(q, [], auto=False) == []


def test_add_resume_is_idempotent():
    q = queue.Queue([], [])
    queue.add_resume(q, "s"); queue.add_resume(q, "s")
    assert q.resume == ["s"]


def test_queue_file_round_trip(tmp_runs):
    assert queue.load_queue() == queue.Queue([], [])
    q = queue.Queue([{"slug": "n", "topic": "N", "auto": True, "added": 2.0}], ["r"])
    queue.save_queue(q)
    assert queue.load_queue() == q
    assert [p.name for p in tmp_runs.iterdir() if p.is_file()] == ["queue.json"]  # no tmp file left behind


def test_safe_file_stays_inside_the_run(tmp_runs, tmp_path):
    (tmp_path / "s").mkdir(); (tmp_path / "s" / "final.mp4").write_bytes(b"x")
    (tmp_path / "secret").write_text("x"); (tmp_path / "s" / "link.mp4").symlink_to(tmp_path / "secret")
    assert queue.safe_file("s", "final.mp4") == (tmp_path / "s" / "final.mp4").resolve()
    assert queue.safe_file("s", "../secret") is None and queue.safe_file("s", "link.mp4") is None
    assert queue.safe_file("s", "nothing.mp4") is None


def test_safe_file_refuses_a_run_folder_that_is_a_symlink_out(tmp_runs, tmp_path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "passwd").write_text("x")
    (tmp_path / "evil").symlink_to(outside, target_is_directory=True)
    assert (tmp_path / "evil" / "passwd").is_file()  # reachable through the link, yet not inside runs_dir
    assert queue.safe_file("evil", "passwd") is None


def test_safe_file_refuses_odd_names(tmp_runs, tmp_path):
    (tmp_path / "s").mkdir(); (tmp_path / "s" / "sub").mkdir()
    assert queue.safe_file("s", "/etc/hosts") is None and queue.safe_file("s", "sub") is None
    assert queue.safe_file("s", "") is None and queue.safe_file("s", "a\0b") is None
    with pytest.raises(ValueError):
        queue.safe_file("../s", "final.mp4")


def test_rows_survive_odd_folders_and_sort(tmp_runs, tmp_path):
    # odd: no run.json; broken: auto.json is not JSON; w: wait_script; d: done; r: running with a dead pid
    (tmp_path / "odd").mkdir()
    make_run(tmp_path, "broken", auto="{not json", run={"topic": "B"})
    make_run(tmp_path, "w", auto={"state": "wait_script"}, run={"topic": "W", "auto": True})
    make_run(tmp_path, "d", auto={"state": "done"}, run={"topic": "D"})
    make_run(tmp_path, "r", auto={"state": "running", "pid": 999999}, run={"topic": "R"})
    (tmp_path / "queue.json").write_text("{}"); (tmp_path / "Not_A_Slug").mkdir()
    rs = queue.rows(queue.Queue([{"slug": "n", "topic": "N", "auto": False, "added": 1.0}], []))
    assert [r["slug"] for r in rs][:2] == ["w", "r"] and {r["state"] for r in rs} >= {"dead", "done", "queued", "idle"}
    assert next(r for r in rs if r["slug"] == "r")["state"] == "dead"
    assert {r["slug"] for r in rs} == {"w", "r", "d", "n", "odd", "broken", "five-solas"}


def test_rows_order_and_fields(tmp_runs, tmp_path):
    make_run(tmp_path, "old", auto={"state": "done"}, run={"topic": "Old"})
    make_run(tmp_path, "new", auto={"state": "done", "message": "Soát: Đạt\nChép về Mac: scp x y\nxong"}, run={"topic": "New"},
             review={"verdict": "Đạt", "findings": []}, timeline={"total": 41.5, "placements": []},
             cost=[{"cost_usd": 0.5}, {"cost_usd": 0.25}])
    make_run(tmp_path, "e", auto={"state": "error", "message": "hỏng"}, run={"topic": "E"})
    make_run(tmp_path, "wb", auto={"state": "wait_brief"}, run={"topic": "WB"})
    make_run(tmp_path, "q1", auto={"state": "error", "message": "hỏng"}, run={"topic": "Q1"})
    make_run(tmp_path, "q2", auto={"state": "done"}, run={"topic": "Q2"})
    os.utime(tmp_path / "old" / "auto.json", (100, 100)); os.utime(tmp_path / "new" / "auto.json", (200, 200))
    items = [{"slug": "n1", "topic": "N1", "auto": True, "added": 5.0}, {"slug": "n2", "topic": "N2", "auto": False, "added": 6.0}]
    rs = queue.rows(queue.Queue(items, ["q2", "q1"]))
    assert [r["slug"] for r in rs][:9] == ["wb", "e", "q2", "q1", "n1", "n2", "new", "old", "five-solas"]
    row = {r["slug"]: r for r in rs}
    assert row["new"]["message"] == "Soát: Đạt\nxong" and row["new"]["verdict"] == "Đạt" and row["new"]["seconds"] == 41.5
    assert row["new"]["cost"] == 0.75 and row["new"]["since"] == 200 and row["new"]["topic"] == "New"
    assert row["old"]["verdict"] is None and row["old"]["seconds"] is None and row["old"]["cost"] == 0
    assert row["n1"]["since"] == 5.0 and row["n1"]["auto"] is True and row["n1"]["removable"] is True
    assert row["n1"]["step"] == "Tìm hiểu" and row["n1"]["state"] == "queued"
    assert all(not r["removable"] for r in rs if r["slug"] not in ("n1", "n2"))
    assert row["five-solas"]["state"] == "idle" and row["five-solas"]["topic"] == "" and row["five-solas"]["since"] is None


def test_queued_resume_hides_the_old_wait_state(tmp_runs, tmp_path):
    # a run whose auto.json still says wait_brief but is in q.resume shows as queued, not as needing Tai
    make_run(tmp_path, "q", auto={"state": "wait_brief"}, run={"topic": "Q"})
    make_run(tmp_path, "z", auto={"state": "wait_script"}, run={"topic": "Z"})
    rs = queue.rows(queue.Queue([], ["q"]))
    assert [(r["slug"], r["state"]) for r in rs][:2] == [("z", "wait_script"), ("q", "queued")]


def test_unknown_or_broken_files_never_hide_a_video(tmp_runs, tmp_path):
    make_run(tmp_path, "weird", auto={"state": "paused"}, run={"topic": "W"})
    make_run(tmp_path, "list", auto="[1, 2]", run="[]", state="oops", review="x", timeline="[]", cost="{")
    make_run(tmp_path, "nopid", auto={"state": "running"}, run={"topic": "P"})
    (tmp_path / "nopid" / "auto.json").write_text('{"state": "running"}')
    make_run(tmp_path, "arr", auto="null", run={"topic": "A"}, state="[1]", review="[1]", cost="5")
    rs = {r["slug"]: r for r in queue.rows(queue.Queue([], []))}
    assert rs["weird"]["state"] == "error" and rs["nopid"]["state"] == "dead"
    assert rs["list"]["state"] == "idle" and rs["list"]["step"] == "Tìm hiểu" and rs["list"]["cost"] == 0
    assert rs["arr"]["state"] == "idle" and rs["arr"]["step"] == "Tìm hiểu" and rs["arr"]["topic"] == "A"  # JSON, not objects


def test_a_folder_keeps_the_behaviour_of_run(tmp_path):
    # rows() opens folders as _Folder so a broken state.json cannot stop the listing; done/mark/unmark must still work
    make_run(tmp_path, "s", state={"research": "done", "text": "done"})
    f = queue._Folder(tmp_path / "s")
    assert f.done("research") and not f.done("fetch")
    f.mark("fetch")
    f.unmark("text")
    assert json.loads((tmp_path / "s" / "state.json").read_text()) == {"research": "done", "fetch": "done"}
    make_run(tmp_path, "broken", state="{oops")
    broken = queue._Folder(tmp_path / "broken")  # making it does not parse state.json…
    with pytest.raises(ValueError):  # …done() does, as Run does, so status() has to catch it
        broken.done("research")


def test_step_is_the_first_one_not_done(tmp_runs, tmp_path):
    done = {s: "done" for s, _ in queue.STEPS[:queue.STEPS.index(("translate", "Dịch"))]}
    make_run(tmp_path, "m", auto={"state": "running"}, run={"auto": False}, state=done)
    make_run(tmp_path, "a", auto={"state": "running"}, run={"auto": True}, state={k: v for k, v in done.items() if k != "approve_brief"})
    make_run(tmp_path, "end", auto={"state": "done"}, run={}, state={s: "done" for s, _ in queue.STEPS})
    row = {r["slug"]: r for r in queue.rows(queue.Queue([], []))}
    assert row["m"]["step"] == "Dịch" and row["a"]["step"] == "Dịch" and row["end"]["step"] is None
    del done["approve_brief"]
    make_run(tmp_path, "m2", auto={"state": "running"}, run={"auto": False}, state=done)
    make_run(tmp_path, "a2", auto={"state": "running"}, run={"auto": True}, state=done)
    row = {r["slug"]: r for r in queue.rows(queue.Queue([], []))}
    assert row["m2"]["step"] == "Chờ duyệt brief" and row["a2"]["step"] == "Dịch"


def test_relogin_survives_being_queued(tmp_runs, tmp_path):
    from vshort.cli import RELOGIN
    make_run(tmp_path, "x", auto={"state": "error", "message": RELOGIN}, run={"topic": "X"})
    make_run(tmp_path, "y", auto={"state": "error", "message": RELOGIN}, run={"topic": "Y"})
    make_run(tmp_path, "z", auto={"state": "error", "message": RELOGIN + "."}, run={"topic": "Z"})
    rs = queue.rows(queue.Queue([], ["y"]))
    row = {r["slug"]: r for r in rs}
    assert row["x"]["relogin"] and row["x"]["state"] == "error"
    assert row["y"]["relogin"] and row["y"]["state"] == "queued" and not row["z"]["relogin"]
    assert queue.relogin_waiting(rs) == ["x"]
    assert queue.relogin_waiting(queue.rows(queue.Queue([], ["y", "x"]))) == []


def test_next_to_start_respects_limit_order_and_pause():
    q = queue.Queue([{"slug": "n1"}, {"slug": "n2"}], ["r1"])
    running = [{"state": "running", "relogin": False, "slug": "x"}]
    assert queue.next_to_start(q, running, 3) == [("resume", "r1"), ("new", "n1")]
    assert queue.next_to_start(q, running * 3, 3) == []
    paused = running + [{"state": "error", "relogin": True, "slug": "e"}]
    assert queue.next_to_start(q, paused, 3) == [] and queue.relogin_waiting(paused) == ["e"]
    assert queue.next_to_start(q, running * 5, 3) == []  # over the limit: never a negative slice
    assert queue.next_to_start(q, [], 9) == [("resume", "r1"), ("new", "n1"), ("new", "n2")]


def test_running_row_has_progress(tmp_runs, tmp_path):
    import time
    make_run(tmp_path, "r2", auto={"state": "running", "pid": os.getpid()}, run={"auto": True}, state={"research": "done"},
             times={"brief_check": {"start": time.time() - 5}})
    row = {r["slug"]: r for r in queue.rows(queue.Queue([], []))}
    p = row["r2"]["progress"]
    assert p["n"] == 2 and p["label"] == "Duyệt brief" and p["status"] == "running" and 0 <= p["percent"] <= 99
    assert p["eta"]["stop"] == "Duyệt bản dịch"
    assert row["five-solas"]["progress"] is None  # not started: nothing to show


def test_done_steps_survive_a_broken_state(tmp_runs, tmp_path):
    make_run(tmp_path, "ok", state={"research": "done", "fetch": "x"})
    make_run(tmp_path, "bad", state="{oops")
    make_run(tmp_path, "list", state="[1]")
    assert queue.done_steps(queue._Folder(tmp_path / "ok")) == {"research"}
    assert queue.done_steps(queue._Folder(tmp_path / "bad")) == set() == queue.done_steps(queue._Folder(tmp_path / "list"))
