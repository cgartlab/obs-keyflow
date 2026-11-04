# -*- coding: utf-8 -*-
"""HTTP 服务测试：路由、快照、SSE 首帧、路径穿越防护。"""
import json
import logging
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from keyflow.hub import Hub
from keyflow.server import OverlayServer

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _get(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, resp.read()


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.getLogger("test").addHandler(logging.NullHandler())
        cls.hub = Hub()
        cls.server = OverlayServer(("127.0.0.1", 0), cls.hub, WEB_DIR, logging.getLogger("test"))
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      kwargs={"poll_interval": 0.05}, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def test_healthz(self):
        status, body = _get(self.url("/healthz"))
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["service"], "obs-keyflow")
        self.assertEqual(payload["status"], "ok")

    def test_index_served(self):
        with urllib.request.urlopen(self.url("/"), timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))
            body = resp.read()
        self.assertIn(b"obs-keyflow", body)

    def test_state_reflects_hub(self):
        self.hub.key_down("a", 0x41)
        try:
            _, body = _get(self.url("/state"))
            self.assertEqual(json.loads(body)["pressed"], ["a"])
        finally:
            self.hub.key_up("a")

    def test_unknown_path(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            _get(self.url("/nope"))
        self.assertEqual(ctx.exception.code, 404)
        ctx.exception.close()

    def test_path_traversal_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            _get(self.url("/assets/../../keyflow/__main__.py"))
        self.assertIn(ctx.exception.code, (403, 404))
        ctx.exception.close()

    def test_sse_first_frame_is_snapshot(self):
        self.hub.key_down("b", 0x42)
        try:
            with urllib.request.urlopen(self.url("/events"), timeout=5) as resp:
                self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))
                line = resp.readline().decode("utf-8").strip()
                self.assertTrue(line.startswith("data:"))
                payload = json.loads(line[5:])
                self.assertEqual(payload["t"], "snap")
                self.assertEqual(payload["pressed"], ["b"])
        finally:
            self.hub.key_up("b")

    def test_sse_broadcasts_key_events(self):
        result: list[dict] = []

        def read_two():
            # 一帧是 "data: {...}\n" 加一个空行，必须只挑 data: 行
            with urllib.request.urlopen(self.url("/events"), timeout=5) as resp:
                while len(result) < 2:
                    line = resp.readline()
                    if not line:
                        break
                    text = line.decode("utf-8").strip()
                    if text.startswith("data:"):
                        result.append(json.loads(text[5:]))

        worker = threading.Thread(target=read_two, daemon=True)
        worker.start()
        for _ in range(100):
            if self.hub.subscriber_count:
                break
            threading.Event().wait(0.02)
        self.hub.key_down("c", 0x43)
        self.hub.key_up("c")
        worker.join(timeout=5)
        self.assertGreaterEqual(len(result), 2)
        self.assertEqual(result[0]["t"], "snap")
        self.assertEqual(result[1], {"t": "key", "k": "c", "d": True})


if __name__ == "__main__":
    unittest.main()
