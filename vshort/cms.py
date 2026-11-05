"""The Tạp chí An ninh mạng CMS, as `vshort cms` talks to it: the settings file, GraphQL, the three-call file upload.

The machine token lives in its own file (mode 600) on the server and only ever goes into the Authorization header of a
request to the CMS API: never into an error message, cms.json, a log, or a page (`repr=False`, `_scrub`).
Every network call goes through `_http`, so the tests put a fake CMS there."""
import http.client
import json
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from vshort.run import config

ENVS = ("dev", "prod")
PLATFORMS = ("facebook", "youtube", "tiktok")
GQL_TIMEOUT = 120  # seconds; articles_transform_preview runs the CMS's AI
PUT_TIMEOUT = 600  # a 30 MB video to MinIO

ARTICLE_FIELDS = ("id title slug content department_id article_type_id workflow_id avatar1_id avatar2_id updated_at "
                  "workflow { workflow_type_id name }")
ARTICLE_TYPES = "query { article_types_all { id name department_id status_id } }"
ARTICLE = f"query($id: Int!) {{ articles_detail(id: $id) {{ {ARTICLE_FIELDS} }} }}"
CREATE = "mutation($b: ArticleSaveInputDto!) { articles_create(body: $b) { id } }"
UPDATE = "mutation($id: Int!, $b: ArticleSaveInputDto!) { articles_update(id: $id, body: $b) { id } }"
TRANSFORM = ("mutation($b: ArticleTransformPreviewInput!) { articles_transform_preview(body: $b) "
             "{ title caption hashtags } }")
PROPOSE = "mutation($i: ProposeZernioPostInput!) { propose_zernio_post(input: $i) { publishId status } }"
WORKFLOWS = "query($b: BaseInput!) { workflows_all(body: $b) { id name type_id workflow_type_id sub_type_id } }"
ZERNIO = "query { zernio_accounts { id platform username displayName needsReauth } }"
# skips the department check (@SkipDepartmentCheck): what department_id the act-as editor may use
PROFILE = "query { auth_profile { id user_name userDepartments { department { id name } } } }"
SAMPLE = (f"query($id: Int!) {{ articles_detail(id: $id) {{ {ARTICLE_FIELDS} desc icon_id icon {{ name }} "
          "articleCategories { category_id is_major category { name } } "
          "articleGenres { article_genre_id is_major articleGenre { name } } "
          "articleKinds { article_kind_id } articleTags { tag { name } } } }")


@dataclass
class Settings:
    env: str
    api: str
    admin: str
    token: str = field(repr=False)
    act_as: str
    department_id: int
    private_workflow_id: int
    article_type_id: int
    categories: list[int]
    genres: list[int]
    kinds: list[int]  # article_kind_ids (IMAGE 1, VIDEO 2…), may be empty
    icon_id: int  # "Loại bài viết" in CMS-Admin (article_types_all), e.g. Short Video
    zernio: dict[str, str]


class CmsError(Exception):
    """`answered`: the CMS itself refused (a 4xx). False for a network error, a timeout, a 5xx or a page that is not
    the CMS's JSON: then a write may still have happened."""

    def __init__(self, message: str, code: int | None = None, answered: bool = True):
        super().__init__(message)
        self.message, self.code, self.answered = message, code, answered

    @property
    def not_found(self) -> bool:
        return self.code == 404


def _id(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def load(env: str | None = None, ids: bool = True) -> tuple[Settings | None, list[str]]:
    """The settings of the set `use` names (or `env`), or what is missing (in Vietnamese, for the page). `ids=False`:
    only what a call needs (api, token, act_as, department_id), for `vshort cms-probe` to find the other ids."""
    path = Path(config().get("cms_file", "~/.config/vshort/cms.toml")).expanduser()
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"chưa có file cấu hình {path}"]
    except (OSError, ValueError) as e:
        return None, [f"không đọc được {path}: {e}"]
    env = env or doc.get("use")
    if env not in ENVS:
        return None, ['use phải là "dev" hoặc "prod"']
    sec = doc.get(env)
    if not isinstance(sec, dict):
        return None, [f"thiếu bảng [{env}]"]
    missing = []
    for k in ("api", "admin", "act_as", "token_file"):
        if not (isinstance(sec.get(k), str) and sec[k].strip()):
            missing.append(f"thiếu {k}")
    if isinstance(sec.get("api"), str) and sec["api"].strip() and not sec["api"].startswith("https://"):
        missing.append("api phải là https:// (token không được đi qua mạng dạng chữ trần)")
    for k in ("department_id", "private_workflow_id", "article_type_id", "icon_id") if ids else ("department_id",):
        if not _id(sec.get(k)):
            missing.append(f"{k} chưa điền (phải là số id > 0)")
    for k in ("categories", "genres") if ids else ():
        if not (isinstance(sec.get(k), list) and sec[k] and all(_id(v) for v in sec[k])):
            missing.append(f"{k} chưa điền (danh sách id > 0)")
    if ids and not (isinstance(sec.get("kinds", []), list) and all(_id(v) for v in sec.get("kinds", []))):
        missing.append("kinds phải là danh sách id > 0 (để [] nếu bài mẫu không có)")
    zernio = sec.get("zernio") if ids else {}
    if not (isinstance(zernio, dict) and all(isinstance(zernio.get(p, ""), str) for p in PLATFORMS)):
        missing.append("thiếu bảng zernio = { facebook, youtube, tiktok } (để trống nền tảng không đăng)")
    if missing:
        return None, missing
    tok = Path(sec["token_file"]).expanduser()
    try:
        if tok.stat().st_mode & 0o077:
            return None, ["token_file phải để quyền 600"]
        token = tok.read_text(encoding="utf-8").strip()
    except OSError:
        return None, [f"không có token_file {tok}"]
    if not token:
        return None, ["token_file rỗng"]
    return Settings(env=env, api=sec["api"].rstrip("/"), admin=sec["admin"].rstrip("/"), token=token,
                    act_as=sec["act_as"].strip(), department_id=sec["department_id"],
                    private_workflow_id=sec.get("private_workflow_id", 0), article_type_id=sec.get("article_type_id", 0),
                    categories=list(sec.get("categories", [])), genres=list(sec.get("genres", [])),
                    kinds=list(sec.get("kinds", [])), icon_id=sec.get("icon_id", 0), zernio={p: zernio.get(p, "").strip() for p in PLATFORMS}), []


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib would carry the Authorization header on to wherever a redirect points: a 3xx is an answer, not a hop."""

    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _http(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: int) -> tuple[int, bytes]:
    """The only call that touches the network: (HTTP status, body). CmsError(answered=False) when nothing came back."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except (OSError, http.client.HTTPException):
            return e.code, b""
    except (OSError, http.client.HTTPException) as e:  # URLError, a timeout and a reset are all OSError
        why = getattr(e, "reason", None) or e
        raise CmsError(f"Không kết nối được CMS: {why}", answered=False) from None


def _scrub(s: Settings, text: str) -> str:
    return text.replace(s.token, "***") if s.token else text


def _call(s: Settings, method: str, url: str, headers: dict[str, str], body: bytes | None,
          timeout: int) -> tuple[int, bytes]:
    try:
        return _http(method, url, headers, body, timeout)
    except CmsError as e:
        raise CmsError(_scrub(s, e.message), e.code, e.answered) from None


def _headers(s: Settings) -> dict[str, str]:
    # a header is latin-1; the CMS reads x-mcp-act-as through decodeURIComponent (jwt-auth.guard.ts)
    act = s.act_as if s.act_as.isascii() else urllib.parse.quote(s.act_as)
    return {"Authorization": f"Bearer {s.token}", "x-mcp-act-as": act, "x-department-id": str(s.department_id)}


def _refused(status: int) -> bool:
    return 400 <= status < 500


def gql(s: Settings, query: str, variables: dict) -> dict:
    """`data` of one GraphQL call. The CMS's formatError puts `code` next to `message` and makes it the HTTP status
    (CMS-Backend src/configs/graphql.conf.ts), so the body is read whatever the status."""
    status, raw = _call(s, "POST", f"{s.api}/graphql", _headers(s) | {"Content-Type": "application/json"},
                        json.dumps({"query": query, "variables": variables}).encode(), GQL_TIMEOUT)
    try:
        doc = json.loads(raw)
    except ValueError:
        doc = None
    errors = doc.get("errors") if isinstance(doc, dict) else None
    if isinstance(errors, list) and errors:
        e0 = errors[0] if isinstance(errors[0], dict) else {}
        code = e0.get("code", (e0.get("extensions") or {}).get("code"))
        code = code if _id(code) else status  # Apollo's own errors carry a string code ("GRAPHQL_VALIDATION_FAILED")
        raise CmsError(_scrub(s, f"CMS báo lỗi: {e0.get('message') or 'không rõ lý do'}"), code, _refused(code))
    if status != 200 or not isinstance(doc, dict) or not isinstance(doc.get("data"), dict):
        raise CmsError(f"CMS trả lời lạ (HTTP {status})", status, _refused(status))
    return doc["data"]


def _rest(s: Settings, path: str, payload: dict) -> dict:
    status, raw = _call(s, "POST", f"{s.api}/{path}", _headers(s) | {"Content-Type": "application/json"},
                        json.dumps(payload).encode(), GQL_TIMEOUT)
    try:
        doc = json.loads(raw)
    except ValueError:
        doc = None
    if 200 <= status < 300 and isinstance(doc, dict):
        return doc
    why = doc.get("message") if isinstance(doc, dict) else None
    why = "; ".join(map(str, why)) if isinstance(why, list) else why
    raise CmsError(_scrub(s, f"CMS báo lỗi ở {path}: {why or f'HTTP {status}'}"), status, _refused(status))


def upload(s: Settings, path: Path, mime: str) -> dict:
    """One file into the CMS's file library: presign, PUT the bytes to MinIO, confirm. {"id", "url"} (url: on the CDN)."""
    pre = _rest(s, "files/presigned-upload", {"file_name": path.name, "mime_type": mime,
                                              "file_size": path.stat().st_size, "department_id": s.department_id})
    url, key = pre.get("uploadUrl"), pre.get("s3Key")
    if not (isinstance(url, str) and url.startswith(("https://", "http://")) and isinstance(key, str)):
        raise CmsError("CMS không trả địa chỉ tải file lên", answered=True)
    # only Content-Type: the token is for the CMS, not for MinIO
    status, _ = _call(s, "PUT", url, {"Content-Type": mime}, path.read_bytes(), PUT_TIMEOUT)
    if not 200 <= status < 300:
        raise CmsError(f"Kho file không nhận {path.name} (HTTP {status})", status, _refused(status))
    up = _rest(s, "files/confirm-upload", {"s3_key": key}).get("upload")
    if not (isinstance(up, dict) and _id(up.get("id")) and isinstance(up.get("url"), str)):
        raise CmsError(f"CMS không xác nhận được file {path.name}", answered=True)
    return {"id": up["id"], "url": up["url"]}
