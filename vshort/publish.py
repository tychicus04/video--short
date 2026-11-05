"""`vshort cms`: a finished video as a personal (PRIVATE), unpublished article on the CMS, shaped like Tai's sample
article 22457, plus one social-post proposal that Tai approves in the CMS. Never publishes, never approves."""
import html
import json
import re

from vshort import auto
from vshort.cms import CmsError, Settings
from vshort.run import Run

META = "cover/cms-meta.json"
META_TIMEOUT = 600  # seconds
CMS_META = ("Việc riêng: viết sapo và từ khóa cho bài đăng video lên CMS, không làm gì khác (không tạo notebook, không "
            "nạp nguồn, không sửa brief, không tìm web). RUN={run}. Đọc {run}/script.vi.json (lời video thật sự nói), "
            "{run}/brief.vi.md và tiêu đề đăng (\"title\") trong {run}/cover/cover.json.\n\n"
            "\"sapo\": một câu tiếng Việt khoảng 40–50 chữ (nhiều nhất 2 câu, 40–300 ký tự) tóm điều video nói: sự việc, "
            "ai bị ảnh hưởng, hậu quả, việc nên làm. Không lặp nguyên tiêu đề. \"keywords\": 6 cụm từ khóa tiếng Việt "
            "(mỗi cụm ≤ 60 ký tự, không trùng nhau), cụm đầu là từ khóa chính người đọc sẽ tìm; có tên sản phẩm/hãng, "
            "mã CVE nếu video nói tới. Chỉ dùng dữ kiện có trong script.vi.json và brief.vi.md; không bịa số; không tên "
            "tệp/công cụ mà mục \"Lưu ý độ chính xác\" của brief cấm.\n\n"
            "Ghi {run}/cover/cms-meta.json: {{\"sapo\": \"…\", \"keywords\": [\"…\", \"…\", \"…\", \"…\", \"…\", \"…\"]}}.")


def video_block(url: str) -> str:
    """The video as CMS-Admin's editor inserts it (buildFigureVideoHtml in TextEditorTinyMce/utils.ts): the HLS
    playlist first for Safari/iOS, the mp4 for the rest. No poster: the CMS's thumbnail job makes none for us yet."""
    src = html.escape(url, quote=True)
    hls = (f'<source src="{src}/master.m3u8" type="application/vnd.apple.mpegurl">\n        '
           if url.split("?")[0].lower().endswith(".mp4") else "")
    return f"""
<figure class="mce-noneditable" data-align-image="center">
    <video controls playsinline preload="metadata" style="max-width: 100%; height: auto; display: block; width: 100%;">
        {hls}<source src="{src}" type="video/mp4">
        Your browser does not support the video tag.
    </video>
    <figcaption>
        <p class="mce-editable" style="text-align: center; font-style: italic;"></p>
    </figcaption>
</figure>
"""


def swap_video(content: str, old_url: str, new_url: str) -> str:
    """Every use of the old video (its mp4 and its m3u8 both start with it), the rest of the article as it is."""
    return content.replace(html.escape(old_url, quote=True), html.escape(new_url, quote=True))


def _check_meta(doc) -> str | None:
    """What is wrong with the agent's sapo and keywords, or None."""
    if not isinstance(doc, dict):
        return "file không phải object JSON"
    sapo, kws = doc.get("sapo"), doc.get("keywords")
    if not (isinstance(sapo, str) and 40 <= len(sapo.strip()) <= 300):
        return "sapo phải dài 40–300 ký tự"
    if len(re.findall(r"[.!?…](?:\s|$)", sapo.strip())) > 2:
        return "sapo nhiều hơn 2 câu"
    if not (isinstance(kws, list) and 1 <= len(kws) <= 6 and all(isinstance(k, str) and 0 < len(k.strip()) <= 60
                                                                  for k in kws)):
        return "từ khóa phải là 1–6 cụm, mỗi cụm ≤ 60 ký tự"
    if len({k.strip().casefold() for k in kws}) != len(kws):
        return "từ khóa bị trùng"
    return None


def ensure_meta(run: Run) -> dict:
    """{"sapo", "keywords"}: from cover/cms-meta.json, written once by an agent. A bad file is removed (the next send
    asks again) and nothing goes to the CMS."""
    f = run.file(META)
    if not f.exists():
        auto.run_claude(run, "cms_meta", "vs-researcher", CMS_META.format(run=run.path), META_TIMEOUT)
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = None
    if (why := "agent không ghi file" if doc is None else _check_meta(doc)) is not None:
        f.unlink(missing_ok=True)
        raise CmsError(f"sapo/từ khóa agent viết chưa đúng: {why}")
    return {"sapo": doc["sapo"].strip(), "keywords": [k.strip() for k in doc["keywords"]]}


def create_body(s: Settings, title: str, meta: dict, video_url: str, cover16_id: int, cover9_id: int) -> dict:
    """A new personal article like 22457: the video alone in the body, both covers, its categories, genre, kind, tags."""
    return {"title": title, "slug": "", "desc": meta["sapo"], "content": video_block(video_url),
            "avatar1_id": cover16_id, "avatar2_id": cover9_id,
            "workflow_id": s.private_workflow_id, "article_type_id": s.article_type_id, "department_id": s.department_id,
            "article_categories": [{"category_id": c, "display_order": i, "is_major": i == 0}
                                   for i, c in enumerate(s.categories)],
            "article_genres": [{"article_genre_id": g, "display_order": i, "is_major": i == 0}
                               for i, g in enumerate(s.genres)],
            "article_kind_ids": list(s.kinds),
            "article_tags": [{"name": k, "for_seo": True, "for_article": True} for k in meta["keywords"]],
            "is_seo": True, "is_push_notify": False, "submit_type": "save"}


def update_body(current: dict, avatar1_id: int, avatar2_id: int, content: str) -> dict:
    """Only the pictures and the video change. The CMS leaves alone every key not sent (sapo, tags, categories,
    genres, kinds: article-save-helper.service.ts returns early on undefined), so Tai's edits stay; the required ones
    and the step come from the article as it is now. expected_updated_at: the CMS answers 409 if Tai saved since."""
    return {"title": current["title"], "slug": current["slug"], "department_id": current["department_id"],
            "article_type_id": current["article_type_id"], "workflow_id": current["workflow_id"],
            "content": content, "avatar1_id": avatar1_id, "avatar2_id": avatar2_id, "submit_type": "save",
            "expected_updated_at": current.get("updated_at")}
