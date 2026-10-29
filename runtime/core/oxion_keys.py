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


def verify_model_access(base_url: str, model: str, key: str, timeout: int = 15) -> None:
    """Validate Oxion key + chosen model BEFORE a multi-hour movie analysis."""
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
    except urllib.error.HTTPError as exc:
        messages = {
            401: "API key Oxion không hợp lệ hoặc đã bị thu hồi.",
            403: "API key Oxion thiếu quyền models:read. Kiểm tra phạm vi key.",
            404: "Oxion không có model này trong danh sách được phép sử dụng.",
            429: "Oxion đang giới hạn lượt gọi API. Thử lại sau.",
        }
        raise MediaError(messages.get(exc.code, f"Không kiểm tra được Oxion (HTTP {exc.code}).")) from exc
    except urllib.error.URLError as exc:
        raise MediaError("Không kết nối được Oxion để kiểm tra model. Kiểm tra mạng và URL.") from exc


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
