"""vshort.cms: the settings file, the GraphQL client, the three-call upload. No real CMS: a FakeHttp answers."""
import json
import os
from pathlib import Path

import pytest

from vshort import cms

TOKEN = "BI-MAT-123"
REAL_HTTP = cms._http  # taken at import, before conftest's no_real_cms replaces it


class FakeHttp:
    """Stands in for cms._http: records every call, answers from a list of (status, body) or exceptions in order."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[tuple[str, str, dict, bytes | None]] = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        status, payload = a
        return status, payload if isinstance(payload, bytes) else json.dumps(payload).encode()


def write_settings(tmp_path: Path, monkeypatch, *, use="dev", mode=0o600, token=TOKEN, **over) -> Path:
    tok = tmp_path / "cms-dev.token"
    tok.write_text(token + "\n")
    os.chmod(tok, mode)
    sec = {"api": "https://api.dev.example", "admin": "https://cms.dev.example", "token_file": str(tok),
           "act_as": "phongvien01", "department_id": 1, "private_workflow_id": 7, "article_type_id": 1,
           "categories": [11, 12], "genres": [21], "kinds": [31], "icon_id": 41} | over

    def val(v):
        return json.dumps(v)  # TOML accepts JSON strings, ints and arrays of ints as they are

    lines = [f'use = "{use}"', "[dev]", *(f"{k} = {val(v)}" for k, v in sec.items()),
             'zernio = { facebook = "fb1", youtube = "yt1", tiktok = "tt1" }']
    f = tmp_path / "cms.toml"
    f.write_text("\n".join(lines) + "\n")
    monkeypatch.setattr(cms, "config", lambda: {"cms_file": str(f)})
    return f


def settings(**over) -> cms.Settings:
    base = dict(env="dev", api="https://api.dev.example", admin="https://cms.dev.example", token=TOKEN,
                act_as="phongvien01", department_id=1, private_workflow_id=7, article_type_id=1,
                categories=[11, 12], genres=[21], kinds=[31], icon_id=41,
                zernio={"facebook": "fb1", "youtube": "yt1", "tiktok": "tt1"})
    return cms.Settings(**(base | over))


def test_load_reports_what_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(cms, "config", lambda: {"cms_file": str(tmp_path / "none.toml")})
    s, missing = cms.load()
    assert s is None and missing and "none.toml" in missing[0]

    write_settings(tmp_path, monkeypatch, use="x")
    s, missing = cms.load()
    assert s is None and any("use" in m for m in missing)

    write_settings(tmp_path, monkeypatch, private_workflow_id=0)
    s, missing = cms.load()
    assert s is None and missing == [m for m in missing if "private_workflow_id" in m] and missing

    write_settings(tmp_path, monkeypatch, icon_id=0)  # "Loại bài viết" of the sample (Short Video)
    s, missing = cms.load()
    assert s is None and missing == [m for m in missing if "icon_id" in m] and missing

    write_settings(tmp_path, monkeypatch, kinds=[])  # article_kind_ids may be empty
    s, missing = cms.load()
    assert missing == [] and s.kinds == [] and s.icon_id == 41

    write_settings(tmp_path, monkeypatch, api="http://api.dev.example")  # the token would cross the LAN in clear
    s, missing = cms.load()
    assert s is None and any("api" in m for m in missing)


def test_load_refuses_a_token_others_can_read(tmp_path, monkeypatch):
    write_settings(tmp_path, monkeypatch, mode=0o644)
    assert cms.load() == (None, ["token_file phải để quyền 600"])

    write_settings(tmp_path, monkeypatch)
    s, missing = cms.load()
    assert missing == [] and s.token == TOKEN and s.env == "dev" and s.categories == [11, 12]
    assert s.zernio == {"facebook": "fb1", "youtube": "yt1", "tiktok": "tt1"}


def test_gql_sends_the_machine_headers(monkeypatch):
    fake = FakeHttp((200, {"data": {"x": 1}}))
    monkeypatch.setattr(cms, "_http", fake)
    assert cms.gql(settings(), "query { x }", {"a": 1}) == {"x": 1}
    method, url, headers, body = fake.calls[0]
    assert (method, url) == ("POST", "https://api.dev.example/graphql")
    assert headers == {"Authorization": f"Bearer {TOKEN}", "x-mcp-act-as": "phongvien01", "x-department-id": "1",
                       "Content-Type": "application/json"}
    assert json.loads(body) == {"query": "query { x }", "variables": {"a": 1}}

    fake = FakeHttp((200, {"data": {}}))
    monkeypatch.setattr(cms, "_http", fake)
    cms.gql(settings(act_as="Thái Thiện"), "query { x }", {})
    assert fake.calls[0][2]["x-mcp-act-as"] == "Th%C3%A1i%20Thi%E1%BB%87n"  # a header is latin-1; the CMS decodes it


def test_gql_errors(monkeypatch):
    # the CMS's formatError puts `code` beside `message`, and sets the HTTP status to it (graphql.conf.ts)
    monkeypatch.setattr(cms, "_http", FakeHttp((404, {"errors": [{"message": "Not Found", "code": 404}], "data": None})))
    with pytest.raises(cms.CmsError) as e:
        cms.gql(settings(), "q", {})
    assert e.value.not_found is True and e.value.answered is True and e.value.code == 404

    monkeypatch.setattr(cms, "_http", FakeHttp((200, {"errors": [{"message": "x", "extensions": {"code": 404}}]})))
    with pytest.raises(cms.CmsError) as e:
        cms.gql(settings(), "q", {})
    assert e.value.not_found is True

    monkeypatch.setattr(cms, "_http", FakeHttp(cms.CmsError("Không kết nối được CMS: timed out", answered=False)))
    with pytest.raises(cms.CmsError) as e:
        cms.gql(settings(), "q", {})
    assert e.value.answered is False and e.value.not_found is False

    monkeypatch.setattr(cms, "_http", FakeHttp((403, {"errors": [{"message": "Bạn không có quyền", "code": 403}]})))
    with pytest.raises(cms.CmsError) as e:
        cms.gql(settings(), "q", {})
    assert e.value.not_found is False and e.value.answered is True and "Bạn không có quyền" in e.value.message

    # a proxy's 504 page, or the CMS's own 500: the write may have happened, so it is not an answer
    for status, body in [(504, b"<html>Gateway Time-out</html>"), (500, {"errors": [{"message": "boom", "code": 500}]})]:
        monkeypatch.setattr(cms, "_http", FakeHttp((status, body)))
        with pytest.raises(cms.CmsError) as e:
            cms.gql(settings(), "q", {})
        assert e.value.answered is False and e.value.code == status


def test_upload_three_calls(tmp_path, monkeypatch):
    f = tmp_path / "final.mp4"
    f.write_bytes(b"\0" * 1234)
    fake = FakeHttp((201, {"uploadUrl": "https://minio.example/put?sig=1", "s3Key": "videos/k.mp4", "expiresIn": 900}),
                    (200, b""),
                    (201, {"upload": {"id": 55, "url": "https://cdn.example/original/videos/k.mp4", "name": "k"}}))
    monkeypatch.setattr(cms, "_http", fake)
    assert cms.upload(settings(), f, "video/mp4") == {"id": 55, "url": "https://cdn.example/original/videos/k.mp4"}
    (m1, u1, h1, b1), (m2, u2, h2, b2), (m3, u3, h3, b3) = fake.calls
    assert (m1, u1) == ("POST", "https://api.dev.example/files/presigned-upload")
    assert json.loads(b1) == {"file_name": "final.mp4", "mime_type": "video/mp4", "file_size": 1234, "department_id": 1}
    assert h1["Authorization"] == f"Bearer {TOKEN}"
    assert (m2, u2, h2, b2) == ("PUT", "https://minio.example/put?sig=1", {"Content-Type": "video/mp4"}, b"\0" * 1234)
    assert (m3, u3) == ("POST", "https://api.dev.example/files/confirm-upload") and json.loads(b3) == {"s3_key": "videos/k.mp4"}


def test_upload_refused_says_why(tmp_path, monkeypatch):
    f = tmp_path / "a.jpg"
    f.write_bytes(b"x")
    monkeypatch.setattr(cms, "_http", FakeHttp((400, {"statusCode": 400, "message": ["file_size quá lớn"]})))
    with pytest.raises(cms.CmsError) as e:
        cms.upload(settings(), f, "image/jpeg")
    assert "file_size quá lớn" in e.value.message and e.value.answered is True


def test_token_never_leaves(monkeypatch):
    s = settings()
    assert TOKEN not in repr(s)

    echo = {"errors": [{"message": f"bad header Authorization: Bearer {TOKEN}", "code": 401}]}
    monkeypatch.setattr(cms, "_http", FakeHttp((401, echo)))
    with pytest.raises(cms.CmsError) as e:
        cms.gql(s, "q", {})
    assert TOKEN not in str(e.value) and TOKEN not in e.value.message and "***" in e.value.message

    monkeypatch.setattr(cms, "_http", FakeHttp(cms.CmsError(f"Không kết nối được CMS: {TOKEN}", answered=False)))
    with pytest.raises(cms.CmsError) as e:
        cms.gql(s, "q", {})
    assert TOKEN not in str(e.value)


def test_http_never_follows_a_redirect(monkeypatch):
    """urllib would send the Authorization header on to wherever a redirect points."""
    import urllib.request
    handlers = [type(h) for h in cms._OPENER.handlers]
    assert urllib.request.HTTPRedirectHandler not in handlers and any(
        issubclass(h, urllib.request.HTTPRedirectHandler) for h in handlers)


def test_load_refuses_a_token_with_spaces_or_line_breaks(tmp_path, monkeypatch):
    """http.client would put the whole header, token and all, into a ValueError that ends up in auto.log."""
    for bad in ("BI-MAT\r123", "BI MAT", "BI-MÂT"):
        write_settings(tmp_path, monkeypatch, token=bad)
        s, missing = cms.load()
        assert s is None and missing and all(bad not in m for m in missing)


def test_a_header_http_refuses_never_carries_the_token():
    """The request is refused before anything is sent (no network): a CmsError that does not repeat the header."""
    with pytest.raises(cms.CmsError) as e:
        REAL_HTTP("POST", "https://127.0.0.1:9/graphql", {"Authorization": f"Bearer {TOKEN}\nX: y"}, b"{}", 5)
    assert TOKEN not in str(e.value) and e.value.answered is False  # not sure what went out: never "refused"


def test_load_never_raises(tmp_path, monkeypatch):
    """load() runs on every /api/state poll: an odd token file must be a line on the CMS box, never a down home page."""
    write_settings(tmp_path, monkeypatch)
    (tmp_path / "cms-dev.token").write_bytes(b"\xff\xfe\x00bad")
    s, missing = cms.load()
    assert s is None and missing
    write_settings(tmp_path, monkeypatch, token_file="~no-such-user-vshort/cms.token")
    s, missing = cms.load()
    assert s is None and missing
