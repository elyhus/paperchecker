# -*- coding: utf-8 -*-
"""跨平台密钥存储。

    macOS    Keychain          security add-generic-password / find-generic-password
    Windows  凭据管理器        CredWriteW / CredReadW（advapi32）
    Linux    Secret Service    secret-tool（libsecret-tools）

三者都不可用时**只读环境变量** PAPERCHECKER_API_KEY，不写明文文件——
宁可让用户每次启动时输入，也不把密钥落到磁盘上。
"""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess

SERVICE = "paperchecker"
ENV_NAME = "PAPERCHECKER_API_KEY"


# ----------------------------- macOS -----------------------------

def _mac_load() -> str:
    out = subprocess.run(
        ["security", "find-generic-password", "-s", SERVICE, "-w"],
        capture_output=True, text=True, timeout=5, check=False,
    )
    return out.stdout.strip()


def _mac_save(key: str) -> bool:
    subprocess.run(
        ["security", "add-generic-password", "-s", SERVICE, "-a", "default", "-w", key, "-U"],
        check=True, capture_output=True, timeout=5,
    )
    return True


# ----------------------------- Windows -----------------------------

class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),
        ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", ctypes.c_ulong),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
        ("Persist", ctypes.c_ulong),
        ("AttributeCount", ctypes.c_ulong),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


def _win_load() -> str:
    advapi32 = ctypes.windll.advapi32
    pointer = ctypes.POINTER(_CREDENTIAL)()
    ok = advapi32.CredReadW(SERVICE, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer))
    if not ok:
        return ""
    try:
        blob = ctypes.string_at(pointer.contents.CredentialBlob,
                                pointer.contents.CredentialBlobSize)
        return blob.decode("utf-16-le").rstrip("\x00")
    finally:
        advapi32.CredFree(pointer)


def _win_save(key: str) -> bool:
    advapi32 = ctypes.windll.advapi32
    blob = key.encode("utf-16-le")
    buffer = ctypes.create_string_buffer(blob, len(blob))
    credential = _CREDENTIAL()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = SERVICE
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = "default"
    return bool(advapi32.CredWriteW(ctypes.byref(credential), 0))


# ----------------------------- Linux -----------------------------

def _linux_available() -> bool:
    return shutil.which("secret-tool") is not None


def _linux_load() -> str:
    out = subprocess.run(
        ["secret-tool", "lookup", "service", SERVICE],
        capture_output=True, text=True, timeout=5, check=False,
    )
    return out.stdout.strip()


def _linux_save(key: str) -> bool:
    out = subprocess.run(
        ["secret-tool", "store", "--label", "PaperChecker API Key", "service", SERVICE],
        input=key, text=True, capture_output=True, timeout=5, check=False,
    )
    return out.returncode == 0


# ----------------------------- 对外接口 -----------------------------

def backend() -> str:
    """当前可用的后端名称，用于界面提示与报告里说明平台适配情况。"""
    system = platform.system()
    if system == "Darwin" and shutil.which("security"):
        return "macOS Keychain"
    if system == "Windows":
        return "Windows 凭据管理器"
    if _linux_available():
        return "Linux Secret Service"
    return "环境变量（不支持保存）"


def load_key() -> str:
    key = os.environ.get(ENV_NAME, "").strip()
    if key:
        return key
    try:
        if backend() == "macOS Keychain":
            return _mac_load()
        if backend() == "Windows 凭据管理器":
            return _win_load()
        if backend() == "Linux Secret Service":
            return _linux_load()
    except Exception:
        return ""
    return ""


def save_key(key: str) -> bool:
    key = (key or "").strip()
    if not key:
        return False
    try:
        if backend() == "macOS Keychain":
            return _mac_save(key)
        if backend() == "Windows 凭据管理器":
            return _win_save(key)
        if backend() == "Linux Secret Service":
            return _linux_save(key)
    except Exception:
        return False
    return False
