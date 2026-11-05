"""`vshort cms`: a finished video as a personal (PRIVATE), unpublished article on the CMS, shaped like Tai's sample
article 22457, plus one social-post proposal that Tai approves in the CMS. Never publishes, never approves."""
import fcntl
import hashlib
import html
import json
import os
import re
from pathlib import Path
from typing import IO

from vshort import auto, cms, cover
from vshort.cms import CmsError, Settings
from vshort.run import Run

FILE = "cms.json"
LOCK = "cms.lock"
STEPS = [("meta", "Viết sapo và từ khóa"), ("cover16", "Tải ảnh ngang 16:9"), ("cover9", "Tải ảnh dọc 9:16"),
         ("video", "Tải video"), ("article", "Tạo bài cá nhân"), ("social", "Viết lời mạng xã hội"),
         ("propose", "Đề xuất Facebook, YouTube, TikTok")]
UPDATE_LABEL = "Cập nhật ảnh và video"
FILES = ("cover16", "cover9", "video")
MIME = {"cover16": "image/jpeg", "cover9": "image/jpeg", "video": "video/mp4"}
PRIVATE = 1  # workflow_type_id of the personal (PRIVATE) step
RECYCLE_BIN = 4  # personal_status_id of an article Tai moved to the trash (it stays in the PRIVATE step)
# the CMS's social AI presets (AI_SOCIAL_PRESETS) by target type, and the Zernio platform each one goes to
TARGETS = [(9002, "facebook"), (9003, "youtube"), (9004, "tiktok")]
UNSURE = "Không chắc bài đã được tạo: mở CMS xem trong bài cá nhân; chưa có thì bấm Tạo bài mới"
OLD_VIDEO = "Đề xuất mạng xã hội đang dùng video cũ, sửa trong CMS"
UNSURE_PROPOSAL = "Không chắc đề xuất mạng xã hội đã gửi: xem trong CMS, máy không gửi lại"
NO_BLOCK = "Bài trên CMS không còn khối video máy chèn (có thể bạn đã thay video): máy không sửa nội dung bài"

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
    """A new personal article like 22457: the video alone in the body, both covers, its categories, genre, kind, tags,
    and its "Loại bài viết" (icon_id)."""
    return {"title": title, "slug": "", "desc": meta["sapo"], "content": video_block(video_url),
            "avatar1_id": cover16_id, "avatar2_id": cover9_id, "icon_id": s.icon_id,
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


# --- one send at a time ------------------------------------------------------------------------------------------

def sender(run_dir: Path) -> int | None:
    """The pid of the live `vshort cms` sending this video, if any; for the page (it never takes the lock)."""
    lock = Path(run_dir) / LOCK
    try:
        pid, since = lock.read_text().strip(), lock.stat().st_mtime
    except OSError:
        return None
    return int(pid) if pid.isdigit() and auto._alive(int(pid), since) else None


def acquire(run_dir: Path) -> IO | None:
    """The lock, held until release() or the process ends; None when another send has it. flock, not a pid file
    alone: two clicks start two processes, and a check-then-write would let both create the article. The pid in the
    file is only for sender()."""
    if sender(run_dir):
        return None
    f = open(Path(run_dir) / LOCK, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    f.truncate(0)
    f.write(str(os.getpid()))
    f.flush()
    return f


def release(f: IO) -> None:
    """Emptied, not removed: a process waiting on the old file would lock a name nobody else sees."""
    f.truncate(0)
    f.close()


# --- the send ------------------------------------------------------------------------------------------------------

def _all(run_dir: Path) -> dict:
    try:
        doc = json.loads((Path(run_dir) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def read(run_dir: Path, env: str) -> dict:
    """The record of one CMS (dev or prod) in RUN/cms.json, or {}."""
    rec = _all(run_dir).get(env)
    return rec if isinstance(rec, dict) else {}


def _save(run_dir: Path, env: str, rec: dict) -> None:
    """After every step, whole file or nothing (as Run._save): a send that dies resumes from here."""
    f = Path(run_dir) / FILE
    doc = _all(run_dir) | {env: rec}
    tmp = f.with_name(f".{FILE}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _paths(run_dir: Path) -> dict[str, Path]:
    """The cover Tai drew in Gemini when there is one, the one made from the video otherwise; final.mp4."""
    c = Path(run_dir) / "cover"

    def pick(shape: str) -> Path:
        return c / cover.GEMINI[shape] if (c / cover.GEMINI[shape]).is_file() else c / f"thumb-{shape}.jpg"

    return {"cover16": pick("16x9"), "cover9": pick("9x16"), "video": Path(run_dir) / "final.mp4"}


def _article(s: Settings, rec: dict) -> dict | None:
    """The article as the CMS has it now, or None after setting the record to deleted / left (nothing is written then)."""
    try:
        a = cms.gql(s, cms.ARTICLE, {"id": rec["article_id"]})["articles_detail"]
    except CmsError as e:
        if not e.not_found:
            raise
        rec.update(state="deleted", link=None, message=f"Bài số {rec['article_id']} không còn trên CMS (đã bị xóa). Bấm Tạo bài mới "
                                            "để tạo lại.")
        return None
    wf = a.get("workflow") or {}
    rec["workflow"] = wf.get("name") or ""
    if wf.get("workflow_type_id") != PRIVATE:
        rec.update(state="left", message=f"Bài đã rời luồng cá nhân (chặng {rec['workflow'] or 'khác'}), sửa trong CMS")
        return None
    if a.get("personal_status_id") == RECYCLE_BIN:  # any save without this status takes it out of the trash
        rec.update(state="deleted", message=f"Bài số {rec['article_id']} đang ở thùng rác trong CMS: khôi phục trong CMS "
                                            "rồi bấm Gửi lại, hoặc bấm Tạo bài mới.")
        return None
    return a


def _source_text(run_dir: Path) -> str:
    """What the CMS's social AI reads instead of the article body (only the video): the title, the sapo and what the
    video says. articles_transform_preview takes it as the source's live content and still checks the article's rights."""
    def load(name: str):
        try:
            return json.loads((run_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    title = (load("cover/cover.json") or {}).get("title") or ""
    meta = load(META)
    sapo = meta.get("sapo", "") if isinstance(meta, dict) else ""
    script = load("script.vi.json")
    said = " ".join(" ".join(r["phrases"].replace("|", " ").split()) for r in script
                    if isinstance(r, dict) and isinstance(r.get("phrases"), str)) if isinstance(script, list) else ""
    return "".join(f"<{tag}>{html.escape(x)}</{tag}>" for tag, x in (("h1", title), ("p", sapo), ("p", said)) if x)


def _has(content: str, url: str | None) -> bool:
    return bool(url) and html.escape(url, quote=True) in (content or "")


def send(run_dir: Path, recreate: bool = False) -> dict:
    """Send one finished video to the CMS the settings name, step by step; the record (also in RUN/cms.json).
    Safe to run again: an article is created once, never written after it left the personal step, and only its
    pictures and video change on later sends. Never raises for the CMS or the agent: the record says what failed."""
    run_dir = Path(run_dir)
    s, missing = cms.load()
    if s is None:
        return {"state": "error", "message": "Thiếu cấu hình CMS: " + "; ".join(missing), "steps": []}
    rec = {"files": {}, "creating": False, "proposing": False, "article_id": None, "article_files": {}, "workflow": "",
           "social": {}, "proposal": None} | read(run_dir, s.env)
    if recreate:
        if rec.get("state") not in ("deleted", "unsure"):
            rec.update(state="error", message="Chỉ tạo bài mới khi bài cũ đã bị xóa hoặc không chắc đã tạo")
            _save(run_dir, s.env, rec)
            return rec
        rec.update(article_id=None, article_files={}, creating=False, proposing=False, proposal=None, social={})
    if rec["creating"] and not rec["article_id"]:
        rec.update(state="unsure", message=UNSURE)
        _save(run_dir, s.env, rec)
        return rec
    rec.update(state="running", message="", warning=None, link=None,
               steps=[{"key": k, "label": UPDATE_LABEL if k == "article" and rec["article_id"] else label,
                       "status": "next"} for k, label in STEPS])
    _save(run_dir, s.env, rec)
    at = {"key": None}

    def step(key: str, status: str = "running") -> None:
        at["key"] = key if status == "running" else None
        next(x for x in rec["steps"] if x["key"] == key)["status"] = status
        _save(run_dir, s.env, rec)

    try:
        _send(s, run_dir, rec, step)
    except (CmsError, auto.AgentError) as e:
        if at["key"]:
            next(x for x in rec["steps"] if x["key"] == at["key"])["status"] = "error"
        rec.update(state="error", message=e.message if isinstance(e, CmsError) else str(e))
        _save(run_dir, s.env, rec)
    return rec


def _send(s: Settings, run_dir: Path, rec: dict, step) -> None:
    aid = rec["article_id"]
    current = None
    if aid:
        rec["link"] = f"{s.admin}/article/edit/personal/{s.article_type_id}/{aid}"
        if (current := _article(s, rec)) is None:
            _save(run_dir, s.env, rec)
            return
        step("meta", "skip")
    else:
        try:
            title = json.loads((run_dir / "cover" / "cover.json").read_text(encoding="utf-8"))["title"]
        except (OSError, ValueError, KeyError, TypeError):
            raise CmsError("Chưa có tiêu đề đăng (cover/cover.json): làm lại bước ảnh bìa trước") from None
        step("meta")
        meta = ensure_meta(Run(run_dir))
        step("meta", "done")

    paths = _paths(run_dir)
    for k in FILES:
        step(k)
        if not paths[k].is_file():
            raise CmsError(f"Thiếu file {paths[k].relative_to(run_dir)}")
        sha = _sha(paths[k])
        if rec["files"].get(k, {}).get("sha") == sha:
            step(k, "skip")
            continue
        rec["files"][k] = {"sha": sha} | cms.upload(s, paths[k], MIME[k])
        step(k, "done")
    files = rec["files"]

    step("article")
    if not aid:
        rec["creating"] = True
        _save(run_dir, s.env, rec)
        try:
            out = cms.gql(s, cms.CREATE, {"b": create_body(s, title, meta, files["video"]["url"], files["cover16"]["id"],
                                                         files["cover9"]["id"])})
        except CmsError as e:
            if e.answered:  # the CMS said no: nothing was made
                rec["creating"] = False
                raise
            rec.update(state="unsure", message=f"{UNSURE} ({e.message})")
            step("article", "error")
            return
        aid = int(out["articles_create"]["id"])
        rec.update(article_id=aid, article_files={k: files[k] for k in FILES}, creating=False,
                   link=f"{s.admin}/article/edit/personal/{s.article_type_id}/{aid}")
        content = create_body(s, title, meta, files["video"]["url"], 0, 0)["content"]
        step("article", "done")
    elif all(rec["article_files"].get(k, {}).get("sha") == files[k]["sha"] for k in FILES):
        content = current["content"]
        step("article", "skip")
    else:
        # read again: Tai may have sent the article on while the files went up, and the update carries its step
        if (current := _article(s, rec)) is None:
            _save(run_dir, s.env, rec)
            return
        content = current["content"]
        old = rec["article_files"].get("video", {}).get("url")
        if rec["article_files"].get("video", {}).get("sha") != files["video"]["sha"] and _has(content, old):
            content = swap_video(content, old, files["video"]["url"])
        # a cover whose file did not change keeps what the article has: Tai may have picked another one in the CMS
        av1, av2 = (files[k]["id"] if rec["article_files"].get(k, {}).get("sha") != files[k]["sha"]
                    else current.get(f"avatar{n}_id") for n, k in ((1, "cover16"), (2, "cover9")))
        if (content, av1, av2) != (current["content"], current.get("avatar1_id"), current.get("avatar2_id")):
            cms.gql(s, cms.UPDATE, {"id": aid, "b": update_body(current, av1, av2, content)})
        rec["article_files"] = {k: files[k] for k in FILES}
        step("article", "done")
    warnings = [] if _has(content, files["video"]["url"]) else [NO_BLOCK]

    platforms = [(t, p) for t, p in TARGETS if s.zernio.get(p)]
    if rec["proposal"] or rec["proposing"] or not platforms:
        step("social", "skip")
    else:
        step("social")
        text = _source_text(run_dir)
        for t, _ in platforms:
            if str(t) not in rec["social"]:
                out = cms.gql(s, cms.TRANSFORM, {"b": {"target_type": t, "sources": [
                    {"article_id": aid, "role": "primary", **({"content": text} if text else {})}]}})
                r = out["articles_transform_preview"]
                # "#" in front of each, as CMS-Admin does (socialDraftToComposerData): the AI gives them bare
                tags = [h.strip().lstrip("#").strip() for h in r.get("hashtags") or [] if isinstance(h, str)]
                rec["social"][str(t)] = {"title": r.get("title") or "", "caption": (r.get("caption") or "").strip(),
                                         "hashtags": [f"#{h}" for h in tags if h]}
                _save(run_dir, s.env, rec)
        step("social", "done")

    if rec["proposal"]:
        step("propose", "skip")
        if rec["proposal"].get("video_sha") != files["video"]["sha"]:
            warnings.append(OLD_VIDEO)
    elif rec["proposing"]:  # died after asking: Zernio may have it already
        step("propose", "skip")
        warnings.append(UNSURE_PROPOSAL)
    elif not platforms:
        step("propose", "skip")
    else:
        step("propose")
        texts = {p: rec["social"][str(t)] for t, p in platforms}
        first = texts.get("facebook") or texts[platforms[0][1]]
        rec["proposing"] = True
        _save(run_dir, s.env, rec)
        try:
            out = cms.gql(s, cms.PROPOSE, {"i": {
                "articleId": aid, "content": first["caption"],
                "mediaItems": [{"type": "video", "fileId": files["video"]["id"]}],
                "platforms": [{"platform": p.upper(), "accountId": s.zernio[p],
                               "customContent": (x["caption"] + "\n\n" + " ".join(x["hashtags"])).strip(),
                               **({"platformSpecificData": {"title": x["title"][:100]}} if p == "youtube" and x["title"]
                                  else {})}
                              for p, x in texts.items()]}})
        except CmsError as e:
            if e.answered:
                rec["proposing"] = False
            raise
        rec.update(proposal={"publishId": str(out["propose_zernio_post"]["publishId"]), "video_sha": files["video"]["sha"]},
                   proposing=False)
        step("propose", "done")
    rec.update(state="done", message="", warning="\n".join(warnings) or None)
    _save(run_dir, s.env, rec)
