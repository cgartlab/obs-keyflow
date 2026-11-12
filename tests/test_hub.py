# -*- coding: utf-8 -*-
"""Hub 单元测试：自动重复过滤、自愈释放、广播与背压。"""
import queue
import unittest

from keyflow.hub import Hub


class HubTests(unittest.TestCase):
    def setUp(self):
        self.hub = Hub()

    def test_repeat_is_filtered(self):
        self.assertTrue(self.hub.key_down("a", 0x41))
        self.assertFalse(self.hub.key_down("a", 0x41))       # 自动重复
        self.assertEqual(self.hub.pressed, ["a"])
        self.assertTrue(self.hub.key_up("a"))
        self.assertFalse(self.hub.key_up("a"))               # 重复抬起无效

    def test_simultaneous_keys_keep_order(self):
        self.hub.key_down("controlleft", 0xA2)
        self.hub.key_down("c", 0x43)
        self.assertEqual(self.hub.pressed, ["controlleft", "c"])
        self.hub.key_up("c")
        self.assertEqual(self.hub.pressed, ["controlleft"])

    def test_snapshot_is_a_copy(self):
        self.hub.key_down("x", 0x58)
        snap = self.hub.snapshot()
        snap["pressed"].append("bogus")
        self.assertEqual(self.hub.pressed, ["x"])

    def test_reconcile_releases_physically_up_keys(self):
        self.hub.key_down("a", 0x41)
        self.hub.key_down("b", 0x42)
        # 只认为 0x41 还按着 → 另一个应被自愈释放
        released = self.hub.reconcile(lambda vk: vk == 0x41)
        self.assertEqual(released, 1)
        self.assertEqual(self.hub.pressed, ["a"])

    def test_reconcile_keeps_physically_down_keys(self):
        self.hub.key_down("a", 0x41)
        self.assertEqual(self.hub.reconcile(lambda vk: True), 0)
        self.assertEqual(self.hub.pressed, ["a"])

    def test_reconcile_ignores_unknown_vk(self):
        self.hub.key_down("weird", 0)
        self.assertEqual(self.hub.reconcile(lambda vk: False), 0)
        self.assertEqual(self.hub.pressed, ["weird"])

    def test_subscriber_receives_events(self):
        q = self.hub.subscribe()
        self.hub.key_down("a", 0x41)
        self.hub.key_up("a")
        first = q.get_nowait()
        second = q.get_nowait()
        self.assertEqual(first, {"t": "key", "k": "a", "d": True})
        self.assertEqual(second, {"t": "key", "k": "a", "d": False})
        self.hub.unsubscribe(q)
        self.assertEqual(self.hub.subscriber_count, 0)

    def test_slow_subscriber_never_blocks(self):
        q = queue.Queue(maxsize=1)
        self.hub._subs.add(q)                                  # 模拟卡死的客户端
        for i in range(50):
            self.hub.key_down(f"k{i}", 0x41 + i)
        self.assertEqual(q.qsize(), 1)                          # 背压丢弃而不是阻塞

    def test_overflow_resyncs_with_snapshot(self):
        """客户端积压时不能只丢事件，必须补一份全量快照，否则会永远停在旧状态。"""
        q = queue.Queue(maxsize=2)
        self.hub._subs.add(q)
        self.hub.key_down("a", 0x41)
        self.hub.key_down("b", 0x42)
        self.hub.key_down("c", 0x43)          # 队列已满 -> 丢积压 + 补快照
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        self.assertEqual(len(items), 1, "积压应被替换成一份快照")
        self.assertEqual(items[0]["t"], "snap")
        self.assertEqual(items[0]["pressed"], ["a", "b", "c"])
        self.assertGreaterEqual(self.hub.resync_count, 1)

    def test_release_all(self):
        for key in ("a", "b", "c"):
            self.hub.key_down(key, 0x41)
        self.hub.release_all()
        self.assertEqual(self.hub.pressed, [])


if __name__ == "__main__":
    unittest.main()
