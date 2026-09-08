"""Login + API adapter for xue.zju.edu.cn (学在浙大).

Adapted from the public implementation pattern of
``zju-learning-assistant`` (PeiPei233/zju-learning-assistant).  Only the
requests needed by the product workbench are kept: ``login``,
``get_my_courses``, ``list_course_uploads`` and ``download_upload``.

The implementation keeps the same external URLs so we never stray from the
documented contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote

import httpx

from coursebook_agent.storage import atomic_write_text


CAS_LOGIN_URL = "https://zjuam.zju.edu.cn/cas/login"
CAS_PUBKEY_URL = "https://zjuam.zju.edu.cn/cas/v2/getPubKey"
WEBVPN_BASE = "https://webvpn.zju.edu.cn"
WEBVPN_LOGIN_URL = "https://webvpn.zju.edu.cn/login"
WEBVPN_CAS_LOGIN_URL = "https://webvpn.zju.edu.cn/cas/login"
COURSE_TREE_URL = "https://courses.zju.edu.cn/user/courses"
MY_COURSES_URL = "https://courses.zju.edu.cn/api/my-courses"
COURSE_ACTIVITIES_URL = "https://courses.zju.edu.cn/api/courses/{course_id}/activities"
UPLOAD_REFERENCE_BLOB_URL = "https://courses.zju.edu.cn/api/uploads/reference/{reference_id}/blob"
UPLOAD_BLOB_URL = "https://courses.zju.edu.cn/api/uploads/{id}/blob"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:88.0) Gecko/201001001 Firefox/88.0"
)
WEBVPN_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def webvpnify(url: str) -> str:
    """Rewrite a courses.zju.edu.cn URL into its WebVPN tunnel form.

    WebVPN exposes each upstream URL as either ``/cas/...`` (for CAS) or as
    ``/https/<host>/<path>?<query>`` for the upstream HTTPS endpoints.
    We only rewrite courses.zju.edu.cn URLs here.
    """
    if not url:
        return url
    if url.startswith(WEBVPN_BASE):
        return url
    if url.startswith("https://courses.zju.edu.cn/"):
        suffix = url[len("https://courses.zju.edu.cn/"):]
        return f"{WEBVPN_BASE}/https/courses.zju.edu.cn/{suffix}"
    return url


class XueZaiError(RuntimeError):
    pass


@dataclass
class XueZaiCourse:
    course_id: int
    name: str
    teacher: str | None = None
    term: str | None = None
    cover: str | None = None


@dataclass
class XueZaiUpload:
    upload_id: int
    reference_id: int
    filename: str
    size: int
    module: str = ""
    course_id: int = 0
    course_name: str = ""
    content_type: str | None = None
    url_path: str = ""


@dataclass
class XueZaiSource:
    """Stateful adapter that reuses one httpx cookie jar."""

    cache_dir: Path
    username: str = ""
    session_file: Path = field(default_factory=lambda: Path("./data/xuezai/session.json"))
    via_webvpn: bool = False

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self._client: httpx.Client | None = None
        self._authenticated = False
        self._restore_session()

    # ── low level ────────────────────────────────────────────────────────

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            headers = {"User-Agent": WEBVPN_USER_AGENT if self.via_webvpn else DEFAULT_USER_AGENT}
            self._client = httpx.Client(
                headers=headers,
                follow_redirects=True,
                timeout=30.0,
            )
        return self._client

    def _resolve(self, url: str) -> str:
        return webvpnify(url) if self.via_webvpn else url

    def _persist_session(self) -> None:
        cookies = []
        for cookie in self._client.cookies.jar:
            cookies.append({"name": cookie.name, "value": cookie.value, "domain": cookie.domain, "path": cookie.path})
        atomic_write_text(self.session_file, _encode_json({"username": self.username, "cookies": cookies}))

    def _restore_session(self) -> None:
        if not self.session_file.exists():
            return
        try:
            import json as _json
            payload = _json.loads(self.session_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        cookies = payload.get("cookies", []) if isinstance(payload, dict) else []
        if not cookies:
            return
        client = self._ensure_client()
        for item in cookies:
            client.cookies.set(item["name"], item["value"], domain=item.get("domain", "zju.edu.cn"), path=item.get("path", "/"))
        self.username = payload.get("username", "")
        self._authenticated = bool(cookies)

    def auth_status(self) -> dict[str, Any]:
        return {"authenticated": self._authenticated, "username": self.username}

    def logout(self) -> None:
        if self._client is not None:
            self._client.close()
        self._client = None
        self._authenticated = False
        self.username = ""
        if self.session_file.exists():
            self.session_file.unlink()

    # ── login ───────────────────────────────────────────────────────────

    def login(self, username: str, password: str) -> dict[str, Any]:
        username, password = username.strip(), password.strip()
        if not username or not password:
            raise XueZaiError("请输入学号和密码")
        client = self._ensure_client()
        try:
            if self.via_webvpn:
                # WebVPN requires a pre-flight GET to establish its session
                # cookie before the upstream CAS login is reachable through
                # the tunnel.
                try:
                    preflight = client.get(WEBVPN_LOGIN_URL)
                    if preflight.status_code >= 400:
                        raise XueZaiError(f"WebVPN 入口不可用（HTTP {preflight.status_code}）")
                except XueZaiError:
                    raise
                except Exception as exc:
                    raise XueZaiError(f"WebVPN 入口访问失败：{exc}") from exc
                cas_url = WEBVPN_CAS_LOGIN_URL
            else:
                cas_url = CAS_LOGIN_URL
            login_page = client.get(cas_url)
            if "统一身份认证平台" not in login_page.text:
                raise XueZaiError("无法访问统一身份认证平台")
            execution = re.search(r'name="execution" value="([^"]+)"', login_page.text)
            if not execution:
                raise XueZaiError("登录页结构变化，无法识别登录参数")
            pubkey_resp = client.get(cas_url.replace("/cas/login", "/cas/v2/getPubKey"))
            pubkey = pubkey_resp.json()
            rsa_password = _rsa_encrypt(password, pubkey["modulus"], pubkey["exponent"])
            response = client.post(
                cas_url,
                data={
                    "username": username,
                    "password": rsa_password,
                    "execution": execution.group(1),
                    "_eventId": "submit",
                    "authcode": "",
                },
            )
            if "统一身份认证平台" in response.text:
                # WebVPN + CAS will inject "loginView.sendsms.error" for
                # unfamiliar devices/IPs; surface that explicitly so the
                # caller knows they must complete an SMS challenge in the
                # browser first.
                if "sendsms.error" in response.text:
                    raise XueZaiError("CAS 触发短信二次验证（sendsms.error）：请先在浏览器登录 webvpn 完成手机短信验证后重试")
                raise XueZaiError("学号或密码错误")
            # Prime the courses.zju.edu.cn cookie store.  Any GET that returns
            # 200 is fine — we just need the auth flow to complete.
            client.get(self._resolve(COURSE_TREE_URL))
            self.username = username
            self._authenticated = True
            self._persist_session()
            return self.auth_status()
        except XueZaiError:
            raise
        except Exception as exc:  # noqa: BLE001 — surface a friendly error
            raise XueZaiError(f"登录失败：{exc}") from exc

    # ── course catalog ──────────────────────────────────────────────────

    def list_my_courses(self, refresh: bool = False) -> list[XueZaiCourse]:
        if not self._authenticated:
            raise XueZaiError("尚未登录")
        cache_path = self.cache_dir / "my-courses.json"
        if not refresh and cache_path.exists():
            try:
                import json as _json
                cached = _json.loads(cache_path.read_text(encoding="utf-8"))
                if cached:
                    return [_course_from_json(item) for item in cached]
            except (OSError, ValueError):
                pass
        client = self._ensure_client()
        try:
            payload = {
                "fields": "id,name,course_code,display_name,instructors(id,name),academic_year_id,semester_id,start_date,end_date,cover",
                "page": 1,
                "page_size": 100,
                "conditions": {
                    "status": ["ongoing", "notStarted", "closed"],
                    "keyword": "",
                    "classify_type": "recently_started",
                    "display_studio_list": False,
                },
                "showScorePassedStatus": False,
            }
            response = client.post(self._resolve(MY_COURSES_URL), json=payload)
            response.raise_for_status()
            data = response.json()
            items = data.get("courses", []) or []
            atomic_write_text(cache_path, _encode_json(items))
            return [_course_from_json(item) for item in items]
        except XueZaiError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise XueZaiError(f"读取我的课程失败：{exc}") from exc

    def list_course_uploads(self, course_id: int, refresh: bool = False) -> list[XueZaiUpload]:
        if not self._authenticated:
            raise XueZaiError("尚未登录")
        cache_path = self.cache_dir / f"uploads-{course_id}.json"
        if not refresh and cache_path.exists():
            try:
                import json as _json
                cached = _json.loads(cache_path.read_text(encoding="utf-8"))
                if cached:
                    return [_upload_from_json(item, course_id) for item in cached]
            except (OSError, ValueError):
                pass
        client = self._ensure_client()
        try:
            response = client.get(self._resolve(COURSE_ACTIVITIES_URL.format(course_id=course_id)))
            response.raise_for_status()
            data = response.json()
            activities = data.get("activities", []) or []
            uploads: list[dict[str, Any]] = []
            for activity in activities:
                for upload in activity.get("uploads", []) or []:
                    upload = dict(upload)
                    upload.setdefault("module", activity.get("module") or activity.get("title") or "")
                    uploads.append(upload)
            atomic_write_text(cache_path, _encode_json(uploads))
            return [_upload_from_json(item, course_id) for item in uploads]
        except XueZaiError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise XueZaiError(f"读取课件列表失败：{exc}") from exc

    # ── download ────────────────────────────────────────────────────────

    def download_upload(self, upload: XueZaiUpload) -> bytes:
        if not self._authenticated:
            raise XueZaiError("尚未登录")
        client = self._ensure_client()
        # The reference endpoint serves the original file; fall back to the
        # per-upload blob endpoint when the teacher disabled direct downloads.
        for url in (self._resolve(UPLOAD_REFERENCE_BLOB_URL.format(reference_id=upload.reference_id)), self._resolve(UPLOAD_BLOB_URL.format(id=upload.upload_id))):
            try:
                response = client.get(url)
            except XueZaiError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise XueZaiError(f"下载课件失败：{exc}") from exc
            if response.status_code == httpx.codes.OK:
                content = response.content
                if content:
                    return content
        raise XueZaiError(f"课件不可下载：{upload.filename}")


def _course_from_json(item: dict[str, Any]) -> XueZaiCourse:
    instructors = item.get("instructors") or []
    teacher = None
    if instructors:
        teacher = ", ".join(instructor.get("name", "") for instructor in instructors if instructor.get("name"))
    term_parts = [str(item.get("academic_year_id") or ""), str(item.get("semester_id") or "")]
    term = " · ".join(part for part in term_parts if part and part != "None")
    return XueZaiCourse(course_id=int(item["id"]), name=item.get("display_name") or item.get("name") or "未命名课程", teacher=teacher or None, term=term or None, cover=item.get("cover"))


def _upload_from_json(item: dict[str, Any], course_id: int) -> XueZaiUpload:
    name = item.get("name") or item.get("file_name") or f"upload-{item.get('id', 'unknown')}"
    reference_id = item.get("reference_id") or item.get("id") or 0
    upload_id = item.get("id") or reference_id
    size = int(item.get("size") or 0)
    return XueZaiUpload(upload_id=int(upload_id), reference_id=int(reference_id), filename=_safe_filename(name), size=size, module=item.get("module", ""), course_id=course_id, course_name=item.get("course_name", ""), content_type=item.get("content_type"), url_path=item.get("url") or "")


def _safe_filename(name: str) -> str:
    name = name.replace("/", "_").strip() or "upload"
    return unquote(name)


def _rsa_encrypt(password: str, modulus: str, exponent: str) -> str:
    """Encrypt the CAS password using the current public key.

    Mirrors the ZJU CAS JavaScript helper: build a reversed RSA message by
    feeding bytes through both modulus/exponent halves, then base64 encode.
    """
    from base64 import b64encode
    from Crypto.PublicKey import RSA
    from Crypto.Util.number import bytes_to_long, long_to_bytes

    modulus_int = int(modulus, 16)
    exponent_int = int(exponent, 16)
    key = RSA.construct((modulus_int, exponent_int))
    password_bytes = password.encode("utf-8")
    reversed_bytes = password_bytes[::-1]
    # ZJU CAS uses raw (no-padding) RSA on the reversed bytes.  Older
    # pycryptodome accepted ``key.encrypt(reversed, 0x10)`` but the
    # maintained API exposes ``_encrypt`` for the same primitive.
    ciphertext_int = key._encrypt(bytes_to_long(reversed_bytes))  # type: ignore[attr-defined]
    encoded = b64encode(long_to_bytes(ciphertext_int, key.size_in_bytes())).decode("ascii")
    return encoded


def _encode_json(items: Iterable[Any]) -> str:
    import json as _json
    return _json.dumps(list(items), ensure_ascii=False, indent=2)