# -*- coding: utf-8 -*-
"""Authoritative pressed-state registry + fan-out to overlay clients.

Everything that mutates state goes through here so that:
  * auto-repeat is filtered (a key that is already down never re-emits),
  * a key can be force-released when the physical key is gone (self-healing),
  * every subscriber sees exactly the same event stream.
"""
from __future__ import annotations

import queue
import threading
from typing import Callable, Iterable


class Hub:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pressed: dict[str, int] = {}   # key id -> vk code (for reconciliation)
        self._subs: set[queue.Queue] = set()
        self.resync_count = 0                # 因客户端积压而补发全量快照的次数
        self.subscribe_count = 0             # 累计 SSE 订阅次数（页面重载会 +1，用于诊断）

    # ------------------------------------------------------------ mutation
    def key_down(self, key_id: str, vk: int | None = None) -> bool:
        with self._lock:
            if key_id in self._pressed:
                return False              # auto-repeat
            self._pressed[key_id] = int(vk or 0)
        self.publish({"t": "key", "k": key_id, "d": True})
        return True

    def key_up(self, key_id: str) -> bool:
        with self._lock:
            if key_id not in self._pressed:
                return False
            del self._pressed[key_id]
        self.publish({"t": "key", "k": key_id, "d": False})
        return True

    def reconcile(self, is_physically_down: Callable[[int], bool]) -> int:
        """Release keys whose physical state says they are no longer held.

        Covers lost key-up events: window focus changes, hook re-installs,
        session lock/unlock, remote desktop, dropped injected events.
        """
        with self._lock:
            snapshot = list(self._pressed.items())
        released = 0
        for key_id, vk in snapshot:
            if vk and not is_physically_down(vk) and self.key_up(key_id):
                released += 1
        return released

    def release_all(self) -> None:
        with self._lock:
            keys = list(self._pressed)
        for key_id in keys:
            self.key_up(key_id)

    # ------------------------------------------------------------ reads
    def snapshot(self) -> dict:
        with self._lock:
            return {"t": "snap", "pressed": list(self._pressed)}

    @property
    def pressed(self) -> list[str]:
        with self._lock:
            return list(self._pressed)

    # ------------------------------------------------------------ fan-out
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=512)
        with self._lock:
            self._subs.add(q)
            self.subscribe_count += 1
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subs.discard(q)

    def publish(self, payload: dict) -> None:
        with self._lock:
            subs: Iterable[queue.Queue] = tuple(self._subs)
        for q in subs:
            try:
                q.put_nowait(payload)
            except queue.Full:
                # 慢客户端不能拖住钩子；但直接丢事件会让它永远停在旧状态
                #（典型表现：画面上一直残留一个"按住"的键帽）。
                # 正确做法是丢掉积压、改发一份全量快照，客户端收到 snap 后会整体校正。
                self._resync(q)

    def _resync(self, q: queue.Queue) -> None:
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(self.snapshot())
            self.resync_count += 1
        except queue.Full:
            pass

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)
