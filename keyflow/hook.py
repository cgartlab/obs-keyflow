# -*- coding: utf-8 -*-
"""Windows low-level keyboard hook (WH_KEYBOARD_LL).

Design notes
------------
* The hook lives on its own thread with a message pump; it never blocks long
  enough to be dropped by Windows (the hook timeout would unhook us).
* Every Win32 entry point gets explicit ``argtypes``/``restype``.  A missing
  ``restype`` silently truncates 64-bit handles to 32 bits and makes
  ``SetWindowsHookExW`` fail with a useless error.
* Installation is retried forever: losing the hook for a few seconds must not
  take the overlay down.
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes
from typing import Callable

from .keymap import key_from_vk

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
WM_QUIT = 0x0012
LLKHF_EXTENDED = 0x01

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_user32.CallNextHookEx.restype = LRESULT
_user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
_user32.GetMessageW.restype = wintypes.BOOL
_user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
_user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
_user32.DispatchMessageW.restype = LRESULT
_user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
_user32.GetAsyncKeyState.restype = ctypes.c_short
_kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def is_physically_down(vk: int) -> bool:
    """True while the physical key ``vk`` is held (used for self-healing)."""
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


class KeyboardHook(threading.Thread):
    def __init__(
        self,
        on_down: Callable[[str, int], None],
        on_up: Callable[[str], None],
        logger: logging.Logger,
        retry_seconds: float = 5.0,
    ) -> None:
        super().__init__(name="keyflow-hook", daemon=True)
        self._on_down = on_down
        self._on_up = on_up
        self._log = logger
        self._retry = retry_seconds
        self._tid: int | None = None
        self._hook = None
        self._stopping = threading.Event()
        self._callback = HOOKPROC(self._proc)   # keep a strong reference

    # ------------------------------------------------------------ internals
    def _proc(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code == 0:
            info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            try:
                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP):
                    key_id = key_from_vk(info.vkCode, info.scanCode, bool(info.flags & LLKHF_EXTENDED))
                    if key_id:
                        if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                            self._on_down(key_id, info.vkCode)
                        else:
                            self._on_up(key_id)
            except Exception:                  # never let a bug unhook us
                self._log.exception("hook callback failed")
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _install(self):
        hmod = _kernel32.GetModuleHandleW(None)
        return _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._callback, hmod, 0)

    def run(self) -> None:
        self._tid = _kernel32.GetCurrentThreadId()
        while not self._stopping.is_set():
            hook = self._install()
            if not hook:
                err = ctypes.get_last_error()
                self._log.error("键盘钩子安装失败 (WinError %s), %.0fs 后重试", err, self._retry)
                time.sleep(self._retry)
                continue
            self._hook = hook
            self._log.info("键盘钩子已安装")
            msg = wintypes.MSG()
            while not self._stopping.is_set():
                ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret <= 0:               # WM_QUIT / error
                    break
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
            if self._hook:
                _user32.UnhookWindowsHookEx(self._hook)
                self._hook = None
                self._log.info("键盘钩子已卸载")
            if not self._stopping.is_set():
                self._log.warning("钩子消息循环意外结束, 重新安装")
                time.sleep(1.0)

    def stop(self) -> None:
        self._stopping.set()
        if self._tid:
            _user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
