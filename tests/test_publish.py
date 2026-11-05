"""vshort.publish: the article as the sample 22457 has it, and the send to the CMS that is safe to press twice."""
import json

import pytest

from vshort import auto, cms, publish, stages
from vshort.run import Run

from test_cms import settings

URL = "https://cdn.example/original/videos/2026-11-05/u1_final.mp4"
META = {"sapo": "NAS Synology chạy DSM cũ đang bị mã độc tống tiền mã hóa ảnh và tài liệu của chủ máy, cần cập nhật ngay.",
        "keywords": ["mã độc tống tiền", "Synology", "NAS", "DSM", "bảo mật", "cập nhật"]}


def test_video_block_matches_the_admin_editor():
    html = publish.video_block(URL)
    for part in ('class="mce-noneditable"', 'data-align-image="center"', "playsinline", 'preload="metadata"',
                 'controls', '<p class="mce-editable" style="text-align: center; font-style: italic;"></p>'):
        assert part in html
    hls = html.index(f'<source src="{URL}/master.m3u8" type="application/vnd.apple.mpegurl">')
    mp4 = html.index(f'<source src="{URL}" type="video/mp4">')
    assert hls < mp4
    assert "poster" not in html
    bad = publish.video_block('https://cdn.example/a".mp4')
    assert 'a".mp4' not in bad and "a&quot;.mp4" in bad


def test_swap_video_replaces_both_sources_and_keeps_the_rest():
    new = "https://cdn.example/original/videos/2026-11-06/u2_final.mp4"
    content = publish.video_block(URL) + "<p>Tai viết</p>"
    out = publish.swap_video(content, URL, new)
    assert URL not in out and f"{new}/master.m3u8" in out and f'src="{new}"' in out and "<p>Tai viết</p>" in out
    assert publish.swap_video("<p>Tai viết</p>", URL, new) == "<p>Tai viết</p>"


def test_create_body_follows_the_sample():
    body = publish.create_body(settings(), "Tiêu đề đăng", META, URL, 101, 102)
    assert body == {
        "title": "Tiêu đề đăng", "slug": "", "desc": META["sapo"], "content": publish.video_block(URL),
        "avatar1_id": 101, "avatar2_id": 102,
        "workflow_id": 7, "article_type_id": 1, "department_id": 1,
        "article_categories": [{"category_id": 11, "display_order": 0, "is_major": True},
                               {"category_id": 12, "display_order": 1, "is_major": False}],
        "article_genres": [{"article_genre_id": 21, "display_order": 0, "is_major": True}],
        "article_kind_ids": [31],
        "article_tags": [{"name": k, "for_seo": True, "for_article": True} for k in META["keywords"]],
        "is_seo": True, "is_push_notify": False, "submit_type": "save"}


def test_update_body_touches_only_pictures_and_video():
    current = {"id": 9, "title": "Tai sửa", "slug": "tai-sua", "content": "<p>x</p>", "department_id": 1,
               "article_type_id": 1, "workflow_id": 7, "avatar1_id": 1, "avatar2_id": 2,
               "updated_at": "2026-11-05T10:00:00.000Z", "desc": "sapo Tai sửa",
               "workflow": {"workflow_type_id": 1, "name": "Bài cá nhân"}}
    body = publish.update_body(current, 201, 202, "<p>y</p>")
    assert body == {"title": "Tai sửa", "slug": "tai-sua", "department_id": 1, "article_type_id": 1, "workflow_id": 7,
                    "content": "<p>y</p>", "avatar1_id": 201, "avatar2_id": 202, "submit_type": "save",
                    "expected_updated_at": "2026-11-05T10:00:00.000Z"}


def _run(tmp_path) -> Run:
    d = tmp_path / "synology"
    (d / "cover").mkdir(parents=True)
    return Run(d)


def test_ensure_meta_checks_what_the_agent_wrote(tmp_path, monkeypatch):
    run = _run(tmp_path)
    calls = []

    def agent_writes(doc):
        def fake(r, step, agent, prompt, timeout):
            calls.append((step, agent))
            (r.path / publish.META).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            return ""
        return fake

    monkeypatch.setattr(auto, "run_claude", agent_writes(META))
    assert publish.ensure_meta(run) == META and calls == [("cms_meta", "vs-researcher")]
    assert publish.ensure_meta(run) == META and len(calls) == 1  # the file is there: no second agent

    (run.path / publish.META).unlink()
    monkeypatch.setattr(auto, "run_claude", agent_writes(META | {"keywords": [f"k{i}" for i in range(7)]}))
    with pytest.raises(cms.CmsError) as e:
        publish.ensure_meta(run)
    assert "từ khóa" in e.value.message
    assert not (run.path / publish.META).exists()  # a bad file goes, so "Gửi lại" asks the agent again

    for bad in [META | {"sapo": "ngắn"}, META | {"keywords": ["NAS", "nas"]}, META | {"keywords": []},
                META | {"keywords": ["x" * 61]}, {"sapo": META["sapo"]}]:
        monkeypatch.setattr(auto, "run_claude", agent_writes(bad))
        with pytest.raises(cms.CmsError):
            publish.ensure_meta(run)

    def agent_fails(*a):
        raise auto.AgentError("vs-researcher lỗi ở bước cms_meta")

    monkeypatch.setattr(auto, "run_claude", agent_fails)
    with pytest.raises(auto.AgentError):
        publish.ensure_meta(run)


def test_cms_meta_step_is_no_stage():
    """run_claude opens a times.json entry for cms_meta that nothing closes: it must not move a finished video's stages."""
    assert stages.stage_of("cms_meta") is None
    times = {"cover": {"start": 1.0, "end": 2.0}}
    done = {"research", "approve_brief", "cover"}
    typ = dict(stages.DEFAULT_SECONDS)
    assert (stages.view("done", False, done, times | {"cms_meta": {"start": 3.0}}, typ, 10.0)
            == stages.view("done", False, done, times, typ, 10.0))


# --- send ----------------------------------------------------------------------------------------------------------

FORBIDDEN = ("approve_zernio_post", "publishNow", "scheduledFor", "step_up_token")


class FakeCms:
    """The CMS in memory: articles, uploads, the social AI and Zernio. `before`/`after` raise around one operation, to
    play the CMS refusing it or the process dying right after it; `during_upload` runs inside each upload."""

    OPS = {cms.ARTICLE: "articles_detail", cms.CREATE: "articles_create", cms.UPDATE: "articles_update",
           cms.TRANSFORM: "articles_transform_preview", cms.PROPOSE: "propose_zernio_post"}

    def __init__(self):
        self.articles: dict[int, dict] = {}
        self.calls: list[tuple[str, object]] = []
        self.before: dict[str, BaseException] = {}
        self.after: dict[str, BaseException] = {}
        self.during_upload = None
        self.workflow_type = 1
        self.n_article, self.n_file, self.clock = 22500, 900, 0

    def ops(self, op: str) -> list:
        return [v for o, v in self.calls if o == op]

    def upload(self, s, path, mime):
        self.calls.append(("upload", path.name))
        if self.during_upload:
            self.during_upload()
        if (e := self.before.get("upload")) is not None:
            raise e
        self.n_file += 1
        return {"id": self.n_file, "url": f"https://cdn.example/original/videos/{self.n_file}_{path.name}"}

    def gql(self, s, query, variables):
        op = self.OPS[query]
        self.calls.append((op, variables))
        for word in FORBIDDEN:
            assert word not in query and word not in json.dumps(variables)
        if (e := self.before.get(op)) is not None:
            raise e
        out = getattr(self, op)(variables)
        if (e := self.after.get(op)) is not None:
            raise e
        return {op: out}

    def _tick(self) -> str:
        self.clock += 1
        return f"2026-11-05T10:00:{self.clock:02d}.000Z"

    def articles_detail(self, v):
        if v["id"] not in self.articles:
            raise cms.CmsError("CMS báo lỗi: Not Found", 404)
        a = self.articles[v["id"]]
        return a | {"workflow": {"workflow_type_id": self.workflow_type,
                                 "name": "Bài cá nhân" if self.workflow_type == 1 else "Chờ duyệt"}}

    def articles_create(self, v):
        self.n_article += 1
        b = v["b"]
        self.articles[self.n_article] = {
            "id": self.n_article, "title": b["title"], "slug": "tieu-de", "content": b["content"], "desc": b["desc"],
            "department_id": b["department_id"], "article_type_id": b["article_type_id"], "workflow_id": b["workflow_id"],
            "avatar1_id": b["avatar1_id"], "avatar2_id": b["avatar2_id"], "updated_at": self._tick()}
        return {"id": self.n_article}

    def articles_update(self, v):
        a = self.articles[v["id"]]
        if v["b"].get("expected_updated_at") != a["updated_at"]:
            raise cms.CmsError("CMS báo lỗi: Bài viết vừa bị người khác sửa", 409)
        a.update({k: x for k, x in v["b"].items() if k not in ("submit_type", "expected_updated_at")})
        a["updated_at"] = self._tick()
        return {"id": v["id"]}

    def articles_transform_preview(self, v):
        t = v["b"]["target_type"]
        return {"title": f"Tiêu đề {t}", "caption": f"Lời {t}", "hashtags": ["#baomat", f"#t{t}"]}

    def propose_zernio_post(self, v):
        return {"publishId": f"pub{len(self.ops('propose_zernio_post'))}", "status": "PROPOSED"}


@pytest.fixture
def fake(monkeypatch):
    f = FakeCms()
    monkeypatch.setattr(cms, "gql", f.gql)
    monkeypatch.setattr(cms, "upload", f.upload)
    monkeypatch.setattr(cms, "load", lambda: (settings(), []))
    return f


@pytest.fixture
def run_dir(tmp_path):
    d = tmp_path / "synology"
    (d / "cover").mkdir(parents=True)
    (d / "final.mp4").write_bytes(b"video-1")
    (d / "cover" / "thumb-16x9.jpg").write_bytes(b"wide-1")
    (d / "cover" / "thumb-9x16.jpg").write_bytes(b"tall-1")
    (d / "cover" / "cover.json").write_text(json.dumps({"title": "NAS Synology chưa vá bị tống tiền"}), encoding="utf-8")
    (d / publish.META).write_text(json.dumps(META, ensure_ascii=False), encoding="utf-8")
    return d


def statuses(rec: dict) -> dict:
    return {s["key"]: s["status"] for s in rec["steps"]}


def test_first_send_creates_once_and_proposes_once(fake, run_dir):
    rec = publish.send(run_dir)
    assert rec["state"] == "done" and rec["warning"] is None
    assert len(fake.ops("upload")) == 3 and len(fake.ops("articles_create")) == 1
    assert len(fake.ops("articles_transform_preview")) == 3 and len(fake.ops("propose_zernio_post")) == 1
    assert not fake.ops("articles_update")
    aid = rec["article_id"]
    assert rec["link"] == f"https://cms.dev.example/article/edit/personal/1/{aid}"
    assert set(statuses(rec).values()) == {"done"} and [s["key"] for s in rec["steps"]] == [k for k, _ in publish.STEPS]
    body = fake.ops("articles_create")[0]["b"]
    assert body["title"] == "NAS Synology chưa vá bị tống tiền" and body["avatar1_id"] == 901 and body["avatar2_id"] == 902
    assert "903_final.mp4" in body["content"]
    (p,) = fake.ops("propose_zernio_post")
    assert p["i"]["articleId"] == aid and p["i"]["content"] == "Lời 9002"
    assert p["i"]["mediaItems"] == [{"type": "video", "fileId": 903}]
    assert p["i"]["platforms"] == [
        {"platform": "FACEBOOK", "accountId": "fb1", "customContent": "Lời 9002\n\n#baomat #t9002"},
        {"platform": "YOUTUBE", "accountId": "yt1", "customContent": "Lời 9003\n\n#baomat #t9003",
         "platformSpecificData": {"title": "Tiêu đề 9003"}},
        {"platform": "TIKTOK", "accountId": "tt1", "customContent": "Lời 9004\n\n#baomat #t9004"}]
    saved = json.loads((run_dir / "cms.json").read_text(encoding="utf-8"))
    assert saved["dev"] == rec and publish.read(run_dir, "dev") == rec and publish.read(run_dir, "prod") == {}
    assert "BI-MAT-123" not in (run_dir / "cms.json").read_text(encoding="utf-8")


def test_second_send_with_nothing_new_writes_nothing(fake, run_dir):
    first = publish.send(run_dir)
    n = len(fake.calls)
    rec = publish.send(run_dir)
    later = [op for op, _ in fake.calls[n:]]
    assert later == ["articles_detail"]  # one read, no upload, no write
    assert rec["state"] == "done" and rec["article_id"] == first["article_id"] and rec["warning"] is None
    assert statuses(rec) == {"meta": "skip", "cover16": "skip", "cover9": "skip", "video": "skip", "article": "skip",
                             "social": "skip", "propose": "skip"}


def test_resend_keeps_tais_edits(fake, run_dir):
    aid = publish.send(run_dir)["article_id"]
    fake.articles[aid]["title"] = "Tai sửa"
    fake.articles[aid]["updated_at"] = fake._tick()
    (run_dir / "cover" / "gemini-16x9.jpg").write_bytes(b"gemini-wide")
    n = len(fake.calls)
    rec = publish.send(run_dir)
    assert [op for op, _ in fake.calls[n:]].count("upload") == 1
    (upd,) = fake.ops("articles_update")
    b = upd["b"]
    assert set(b) == {"title", "slug", "department_id", "article_type_id", "workflow_id", "content", "avatar1_id",
                      "avatar2_id", "submit_type", "expected_updated_at"}
    assert b["title"] == "Tai sửa" and b["avatar1_id"] == 904 and b["avatar2_id"] == 902
    assert rec["state"] == "done" and fake.articles[aid]["avatar1_id"] == 904
    assert next(s["label"] for s in rec["steps"] if s["key"] == "article") == "Cập nhật ảnh và video"


def test_rebuilt_video_swaps_the_block_and_warns(fake, run_dir):
    aid = publish.send(run_dir)["article_id"]
    fake.articles[aid]["content"] += "<p>Tai viết</p>"
    old = "https://cdn.example/original/videos/903_final.mp4"
    (run_dir / "final.mp4").write_bytes(b"video-2")
    rec = publish.send(run_dir)
    content = fake.articles[aid]["content"]
    assert old not in content and "904_final.mp4/master.m3u8" in content and "<p>Tai viết</p>" in content
    assert rec["warning"] == "Đề xuất mạng xã hội đang dùng video cũ, sửa trong CMS"
    assert len(fake.ops("propose_zernio_post")) == 1 and rec["state"] == "done"


def test_crash_between_upload_and_update_still_swaps(fake, run_dir):
    """The new video is uploaded and saved in cms.json, then the process dies: the next send still knows the old URL."""
    aid = publish.send(run_dir)["article_id"]
    (run_dir / "final.mp4").write_bytes(b"video-2")
    fake.before["articles_update"] = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        publish.send(run_dir)
    del fake.before["articles_update"]
    rec = publish.send(run_dir)
    content = fake.articles[aid]["content"]
    assert "903_final.mp4" not in content and "904_final.mp4" in content and rec["state"] == "done"
    assert fake.ops("upload").count("final.mp4") == 2  # not uploaded a third time


def test_video_block_gone_warns_and_leaves_the_body(fake, run_dir):
    """Tai took the machine's video out of the article (or put another one in): the body is his, only a warning."""
    aid = publish.send(run_dir)["article_id"]
    fake.articles[aid]["content"] = "<p>Tai thay video khác</p>"
    (run_dir / "final.mp4").write_bytes(b"video-2")
    rec = publish.send(run_dir)
    assert fake.articles[aid]["content"] == "<p>Tai thay video khác</p>" and not fake.ops("articles_update")
    assert "video" in rec["warning"] and rec["state"] == "done"
    assert "video" in publish.send(run_dir)["warning"]  # still said on the next send


def test_left_private_writes_nothing(fake, run_dir):
    publish.send(run_dir)
    (run_dir / "cover" / "gemini-16x9.jpg").write_bytes(b"gemini-wide")
    fake.workflow_type = 3
    n = len(fake.calls)
    rec = publish.send(run_dir)
    assert [op for op, _ in fake.calls[n:]] == ["articles_detail"]
    assert rec["state"] == "left" and "Chờ duyệt" in rec["message"] and rec["link"]


def test_left_private_during_the_upload_writes_nothing(fake, run_dir):
    """Tai sends the article for review while the new cover is uploading: the step is read again before the update."""
    publish.send(run_dir)
    (run_dir / "cover" / "gemini-16x9.jpg").write_bytes(b"gemini-wide")
    fake.during_upload = lambda: setattr(fake, "workflow_type", 3)
    rec = publish.send(run_dir)
    assert rec["state"] == "left" and not fake.ops("articles_update")


def test_deleted_article_needs_recreate(fake, run_dir):
    aid = publish.send(run_dir)["article_id"]
    del fake.articles[aid]
    rec = publish.send(run_dir)
    assert rec["state"] == "deleted" and str(aid) in rec["message"] and len(fake.ops("articles_create")) == 1
    rec = publish.send(run_dir, recreate=True)
    assert rec["state"] == "done" and rec["article_id"] != aid and len(fake.ops("articles_create")) == 2
    assert fake.ops("upload").count("final.mp4") == 1  # the files are in the CMS's library already
    assert len(fake.ops("propose_zernio_post")) == 2  # the old proposal named the deleted article


def test_recreate_refused_while_the_article_is_there(fake, run_dir):
    aid = publish.send(run_dir)["article_id"]
    rec = publish.send(run_dir, recreate=True)
    assert rec["state"] == "error" and rec["article_id"] == aid and len(fake.ops("articles_create")) == 1
    assert publish.send(run_dir)["state"] == "done"


def test_crash_after_create_never_creates_twice(fake, run_dir):
    for crash in (KeyboardInterrupt(), cms.CmsError("Không kết nối được CMS: timed out", answered=False),
                  cms.CmsError("CMS trả lời lạ (HTTP 504)", 504, answered=False)):
        (run_dir / "cms.json").unlink(missing_ok=True)
        fake.after["articles_create"] = crash
        n = len(fake.ops("articles_create"))
        if isinstance(crash, KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                publish.send(run_dir)
        else:
            assert publish.send(run_dir)["state"] == "unsure"
        del fake.after["articles_create"]
        rec = publish.send(run_dir)
        assert rec["state"] == "unsure" and "Tạo bài mới" in rec["message"]
        assert len(fake.ops("articles_create")) == n + 1
    rec = publish.send(run_dir, recreate=True)
    assert rec["state"] == "done" and len(fake.ops("articles_create")) == 4


def test_create_refused_by_the_cms_can_retry(fake, run_dir):
    fake.before["articles_create"] = cms.CmsError("CMS báo lỗi: thiếu chuyên mục", 400)
    rec = publish.send(run_dir)
    assert rec["state"] == "error" and "thiếu chuyên mục" in rec["message"] and not rec["creating"]
    assert statuses(rec)["article"] == "error"
    del fake.before["articles_create"]
    assert publish.send(run_dir)["state"] == "done"


def test_error_midway_resumes(fake, run_dir):
    def fail_on_video():
        if fake.ops("upload")[-1] == "final.mp4":
            raise cms.CmsError("Kho file không nhận final.mp4 (HTTP 403)", 403)

    fake.during_upload = fail_on_video
    rec = publish.send(run_dir)
    assert rec["state"] == "error" and statuses(rec)["video"] == "error" and statuses(rec)["cover9"] == "done"
    assert "final.mp4" in rec["message"]
    fake.during_upload = None
    n = len(fake.ops("upload"))
    assert publish.send(run_dir)["state"] == "done" and fake.ops("upload")[n:] == ["final.mp4"]


def test_agent_failure_is_an_error(fake, run_dir, monkeypatch):
    (run_dir / publish.META).unlink()

    def agent_fails(*a):
        raise auto.AgentError("vs-researcher lỗi ở bước cms_meta (mã 1): hết lượt")

    monkeypatch.setattr(auto, "run_claude", agent_fails)
    rec = publish.send(run_dir)
    assert rec["state"] == "error" and statuses(rec)["meta"] == "error" and "hết lượt" in rec["message"]
    assert not fake.ops("upload")


def test_env_records_are_separate(fake, run_dir, monkeypatch):
    dev = publish.send(run_dir)
    monkeypatch.setattr(cms, "load", lambda: (settings(env="prod", admin="https://cms.example"), []))
    prod = publish.send(run_dir)
    assert prod["article_id"] != dev["article_id"] and len(fake.ops("articles_create")) == 2
    assert len(fake.ops("upload")) == 6  # a dev file id means nothing to prod
    assert publish.read(run_dir, "dev") == dev and prod["link"].startswith("https://cms.example/")


def test_platform_without_account_is_skipped(fake, run_dir, monkeypatch):
    monkeypatch.setattr(cms, "load", lambda: (settings(zernio={"facebook": "fb1", "youtube": "yt1", "tiktok": ""}), []))
    publish.send(run_dir)
    assert len(fake.ops("articles_transform_preview")) == 2
    assert [p["platform"] for p in fake.ops("propose_zernio_post")[0]["i"]["platforms"]] == ["FACEBOOK", "YOUTUBE"]


def test_no_platform_proposes_nothing(fake, run_dir, monkeypatch):
    monkeypatch.setattr(cms, "load", lambda: (settings(zernio={"facebook": "", "youtube": "", "tiktok": ""}), []))
    rec = publish.send(run_dir)
    assert rec["state"] == "done" and not fake.ops("propose_zernio_post")
    assert statuses(rec)["social"] == statuses(rec)["propose"] == "skip"


def test_crash_after_propose_never_proposes_twice(fake, run_dir):
    fake.after["propose_zernio_post"] = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        publish.send(run_dir)
    del fake.after["propose_zernio_post"]
    rec = publish.send(run_dir)
    assert len(fake.ops("propose_zernio_post")) == 1 and rec["state"] == "done" and "đề xuất" in rec["warning"]


def test_missing_settings_say_what(fake, run_dir, monkeypatch):
    monkeypatch.setattr(cms, "load", lambda: (None, ["thiếu token_file"]))
    rec = publish.send(run_dir)
    assert rec["state"] == "error" and "token_file" in rec["message"] and not fake.calls


def test_read_survives_a_broken_file(run_dir):
    (run_dir / "cms.json").write_text("{không phải json")
    assert publish.read(run_dir, "dev") == {}
    (run_dir / "cms.json").write_text('["x"]')
    assert publish.read(run_dir, "dev") == {}


def test_no_title_yet_is_said_before_any_upload(fake, run_dir):
    (run_dir / "cover" / "cover.json").unlink()
    rec = publish.send(run_dir)
    assert rec["state"] == "error" and "cover.json" in rec["message"] and not fake.calls
