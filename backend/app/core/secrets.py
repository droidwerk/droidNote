from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes

SECRET_SETTING_KEYS = frozenset({"asr_api_key"})
DPAPI_PREFIX = "dpapi:v1:"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def protect_setting(key: str, value: str) -> str:
    if key not in SECRET_SETTING_KEYS or not value:
        return value
    return DPAPI_PREFIX + _protect(value)


def unprotect_setting(key: str, value: str | None) -> str | None:
    if value is None or key not in SECRET_SETTING_KEYS:
        return value
    if not value:
        return value
    if value.startswith(DPAPI_PREFIX):
        return _unprotect(value[len(DPAPI_PREFIX) :])
    return value


def _protect(plain: str) -> str:
    if sys.platform != "win32":
        return base64.b64encode(plain.encode("utf-8")).decode("ascii")
    blob = _crypt_protect(plain.encode("utf-8"))
    return base64.b64encode(blob).decode("ascii")


def _unprotect(payload: str) -> str:
    raw = base64.b64decode(payload.encode("ascii"))
    if sys.platform != "win32":
        return raw.decode("utf-8")
    return _crypt_unprotect(raw).decode("utf-8")


def _crypt_protect(data: bytes) -> bytes:
    buffer = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError("Não foi possível proteger a chave da API neste Windows.")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _crypt_unprotect(data: bytes) -> bytes:
    buffer = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError("Não foi possível ler a chave da API protegida.")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
