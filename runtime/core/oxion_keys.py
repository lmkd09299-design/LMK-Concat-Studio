"""Windows DPAPI store for optional local Oxion API key (never commit secrets).

Only Windows implements persistent secret storage. Keys are encrypted to
the current Windows user through CryptProtectData and never appear on the
command line. Model settings can be public; the key must remain private.
"""
from __future__ import annotations

import os
import pathlib
import urllib.parse

from .media import MediaError


def is_oxion(url: str) -> bool:
    parts = urllib.parse.urlsplit(url.strip())
    return parts.scheme == "https" and (parts.hostname or "").lower().removeprefix("www.") == "oxionai.com" and parts.path.rstrip("/") in ("/v1", "/v1/chat/completions")


def verify_model_access(base_url: str, model: str, key: str, timeout: int = 15) -> bool:
    """Return True if model metadata was verified, False if key is inference-only.

    Oxion separates GET /models (models:read) from POST /chat/completions
    (inference). Missing models:read must not block an inference-only key.
    False does not certify key/model validity; the actual chat request does.
    """
    import json
    import urllib.error
    import urllib.request

    if not is_oxion(base_url):
        raise MediaError("URL Oxion không hợp lệ.")
    if not key.strip():
        raise MediaError("Chưa có API key Oxion. Nhập key một lần hoặc bật lưu key trên Windows.")
    if not model.strip():
        raise MediaError("Chưa chọn Model ID Oxion.")
    root = base_url.rstrip("/")
    if root.endswith("/chat/completions"):
        root = root.rsplit("/chat/completions", 1)[0]
    url = root + "/models/" + urllib.parse.quote(model, safe="")
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + key.strip(),
                                                    "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
        if data.get("id") != model:
            raise MediaError("Oxion trả về model ID không trùng cấu hình.")
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            # Only allow the documented narrow-scope error from the models
            # endpoint. Other 403 errors can mean a blocked account, etc.
            try:
                error = json.loads(exc.read(8192)).get("error", {})
            except (ValueError, AttributeError, TypeError):
                error = {}
            if isinstance(error, dict) and error.get("code") == "insufficient_scope":
                return False  # Continue; chat/completions checks inference.
        messages = {
            401: "API key Oxion không hợp lệ hoặc đã bị thu hồi.",
            403: "Oxion từ chối quyền truy cập (403) ngoài trường hợp thiếu models:read. Kiểm tra tài khoản và key.",
            404: "Oxion không có model này trong danh sách được phép sử dụng.",
            429: "Oxion đang giới hạn lượt gọi API. Thử lại sau.",
        }
        raise MediaError(messages.get(exc.code, f"Không kiểm tra được Oxion (HTTP {exc.code}).")) from exc
    except urllib.error.URLError as exc:
        raise MediaError("Không kết nối được Oxion để kiểm tra model. Kiểm tra mạng và URL.") from exc



def verify_inference_access(base_url: str, model: str, key: str, timeout: int = 45) -> None:
    """Probe the permission actually needed by Movie Recap: inference.

    Unlike GET /models, a tiny POST /chat/completions needs only 'inference'.
    Oxion bills the token usage for this probe. No source video or transcript
    leaves the machine during this check.
    """
    import json
    import urllib.error
    import urllib.request

    if not is_oxion(base_url):
        raise MediaError("URL API Oxion không hợp lệ.")
    if not key or not key.strip():
        raise MediaError("Chưa nhập Oxion API key. Hãy nhập key mới trên máy Windows.")
    if not model or not model.strip():
        raise MediaError("Chưa chọn Oxion Model ID.")
    root = base_url.strip().rstrip("/")
    if root.endswith("/chat/completions"):
        root = root[:-len("/chat/completions")]
    url = root + "/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Say OK."}],
        "max_tokens": 24
    }).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + key.strip(),
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
        if not isinstance(body, dict) or not isinstance(body.get("choices"), list) or not body["choices"]:
            raise MediaError("Oxion trả phản hồi AI sai định dạng dù HTTP thành công.")
    except urllib.error.HTTPError as exc:
        messages = {
            400: "Oxion từ chối yêu cầu thử AI (400). Kiểm tra model và tham số.",
            401: "Oxion API key không hợp lệ hoặc đã bị thu hồi (401).",
            402: "Oxion không còn hạn mức API hoặc số dư để chạy model (402).",
            403: "Oxion từ chối quyền inference (403). Cần key có quyền inference.",
            404: "Oxion không tìm thấy Model ID đang chọn (404).",
            422: "Oxion từ chối cấu trúc yêu cầu API (422).",
            429: "Oxion đang giới hạn tốc độ API (429).",
        }
        raise MediaError(messages.get(exc.code, f"Oxion báo HTTP {exc.code} khi gọi inference.")) from exc
    except urllib.error.URLError as exc:
        raise MediaError("Không kết nối được endpoint chat/completions Oxion. Kiểm tra mạng.") from exc


def _file() -> pathlib.Path:
    home = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not home:
        raise MediaError("Lưu API key chỉ hỗ trợ Windows, sử dụng key trong phiên hiện tại.")
    return pathlib.Path(home) / "LMK-Concat-Studio" / "oxion.dpapi"


def _crypt(data: bytes, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise MediaError("Windows DPAPI không khả dụng trên hệ điều hành này.")
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    raw = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = DataBlob(len(data), raw)
    dest = DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    if decrypt:
        func = crypt32.CryptUnprotectData
        func.argtypes = [ctypes.POINTER(DataBlob), ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         wintypes.DWORD, ctypes.POINTER(DataBlob)]
        args = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest))
    else:
        func = crypt32.CryptProtectData
        func.argtypes = [ctypes.POINTER(DataBlob), wintypes.LPCWSTR,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         wintypes.DWORD, ctypes.POINTER(DataBlob)]
        args = (ctypes.byref(source), "LMK Oxion API key", None, None, None,
                1, ctypes.byref(dest))
    func.restype = wintypes.BOOL
    if not func(*args):
        raise MediaError("Không thể mã hóa/giải mã API key bằng Windows DPAPI.")
    try:
        return ctypes.string_at(dest.pbData, dest.cbData)
    finally:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(ctypes.cast(dest.pbData, ctypes.c_void_p))


def store(key: str) -> None:
    if not key or not key.strip():
        raise MediaError("API key trống, không lưu.")
    encrypted = _crypt(key.strip().encode("utf-8"))
    target = _file()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    try:
        temporary.write_bytes(encrypted)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def load() -> str:
    target = _file()
    if not target.is_file():
        return ""
    try:
        return _crypt(target.read_bytes(), decrypt=True).decode("utf-8")
    except Exception as exc:
        raise MediaError("Không đọc được Oxion API key đã lưu. Hãy xóa key cũ và nhập key mới.") from exc


def clear() -> None:
    _file().unlink(missing_ok=True)
