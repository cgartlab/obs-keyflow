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
                pass                      # slow client must never stall the hook

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)
