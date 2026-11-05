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
