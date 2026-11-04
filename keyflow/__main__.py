# -*- coding: utf-8 -*-
"""Command line entry point.

Run from the repository root::

    pythonw -m keyflow            # silent background service (used by auto-start)
    python  -m keyflow --console  # foreground with logging on stdout
"""
from __future__ import annotations

import argparse
import atexit
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import __version__
from .hub import Hub
from .server import OverlayServer

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 16900
RECONCILE_SECONDS = 1.0
LOG_MAX_BYTES = 512 * 1024
LOG_BACKUPS = 2


def default_log_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData/Local")
    return Path(base) / "obs-keyflow" / "logs" / "keyflow.log"


def build_logger(console: bool, log_path: Path, level: str) -> logging.Logger:
    log = logging.getLogger("keyflow")
    log.setLevel(getattr(logging, level.upper(), logging.INFO))
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")

    if console:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(fmt)
        log.addHandler(stream)

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        rotating = RotatingFileHandler(log_path, maxBytes=LOG_MAX_BYTES,
                                       backupCount=LOG_BACKUPS, encoding="utf-8")
        rotating.setFormatter(fmt)
        log.addHandler(rotating)
    except OSError as exc:                       # read-only profile etc.
        log.addHandler(logging.NullHandler())
        log.warning("无法写入日志文件 %s: %s", log_path, exc)

    if not log.handlers:
        log.addHandler(logging.NullHandler())
    return log


def probe_existing(host: str, port: int, timeout: float = 0.8) -> dict | None:
    """Return healthz payload if an obs-keyflow instance already owns the port."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/healthz", timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload if payload.get("service") == "obs-keyflow" else None
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def start_reconciler(hub: Hub, log: logging.Logger) -> threading.Thread:
    from .hook import is_physically_down

    def loop() -> None:
        while True:
            try:
                released = hub.reconcile(is_physically_down)
                if released:
                    log.debug("自愈: 释放 %d 个残留按键", released)
            except Exception:
                log.exception("按键状态自愈失败")
            time.sleep(RECONCILE_SECONDS)

    thread = threading.Thread(target=loop, name="keyflow-reconcile", daemon=True)
    thread.start()
    return thread


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="keyflow",
        description="OBS 按键显示：本地全局键盘钩子 + SSE 服务，供 OBS 浏览器源渲染。",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址（默认仅本机 127.0.0.1）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口（默认 16900）")
    parser.add_argument("--console", action="store_true", help="日志同时输出到控制台")
    parser.add_argument("--no-hook", action="store_true", help="只起 HTTP 服务（调试用）")
    parser.add_argument("--no-reconcile", action="store_true", help="关闭按键状态自愈")
    parser.add_argument("--log", default=str(default_log_path()), help="日志文件路径")
    parser.add_argument("--log-level", default="INFO", help="日志级别 (DEBUG/INFO/WARNING)")
    parser.add_argument("--version", action="version", version=f"obs-keyflow {__version__}")
    args = parser.parse_args(argv)

    log = build_logger(args.console, Path(args.log), args.log_level)

    if os.name != "nt":
        log.error("obs-keyflow 目前只支持 Windows（依赖 WH_KEYBOARD_LL / GetAsyncKeyState）")
        return 2

    existing = probe_existing(args.host, args.port)
    if existing is not None:
        log.info("已有实例在 %s:%s 运行 (version=%s, clients=%s)，本次启动忽略",
                 args.host, args.port, existing.get("version"), existing.get("clients"))
        return 0

    hub = Hub()
    web_dir = Path(__file__).resolve().parent.parent / "web"

    server = None
    for attempt in range(6):
        try:
            server = OverlayServer((args.host, args.port), hub, web_dir, log)
            break
        except OSError as exc:
            wait = 1.0 + attempt
            log.warning("端口 %s 暂时不可用 (%s)，%.1fs 后重试", args.port, exc, wait)
            time.sleep(wait)
    if server is None:
        log.error("无法监听 %s:%s，退出", args.host, args.port)
        return 1

    hook = None
    if not args.no_hook:
        from .hook import KeyboardHook

        hook = KeyboardHook(
            on_down=lambda key_id, vk: hub.key_down(key_id, vk),
            on_up=hub.key_up,
            logger=log,
        )
        hook.start()

    if not args.no_reconcile:
        start_reconciler(hub, log)

    def shutdown(*_args) -> None:
        log.info("正在退出")
        try:
            if hook:
                hook.stop()
            hub.release_all()
        finally:
            try:
                server.shutdown()
            except Exception:
                pass
            server.server_close()

    atexit.register(shutdown)

    log.info("obs-keyflow %s 已启动 http://%s:%s/  (web=%s)", __version__, args.host, args.port, web_dir)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        log.info("收到 Ctrl+C")
    finally:
        shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
