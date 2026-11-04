# -*- coding: utf-8 -*-
"""keymap 单元测试：确保 vk → key id 的稳定契约。"""
import unittest

from keyflow.keymap import key_from_vk, is_modifier


class KeymapTests(unittest.TestCase):
    def test_letters_and_digits(self):
        self.assertEqual(key_from_vk(ord("A"), 0x1E, False), "a")
        self.assertEqual(key_from_vk(ord("Z"), 0x2C, False), "z")
        self.assertEqual(key_from_vk(ord("0"), 0x0B, False), "0")
        self.assertEqual(key_from_vk(ord("9"), 0x0A, False), "9")

    def test_named_keys(self):
        self.assertEqual(key_from_vk(0x0D, 0x1C, False), "enter")
        self.assertEqual(key_from_vk(0x20, 0x39, False), "space")
        self.assertEqual(key_from_vk(0x08, 0x0E, False), "backspace")
        self.assertEqual(key_from_vk(0x1B, 0x01, False), "esc")
        self.assertEqual(key_from_vk(0x70, 0x3B, False), "f1")
        self.assertEqual(key_from_vk(0x7B, 0x57, False), "f12")

    def test_generic_modifiers_use_scan_code(self):
        # 通用 VK + 扫描码 → 左右区分
        self.assertEqual(key_from_vk(0x10, 0x2A, False), "shiftleft")
        self.assertEqual(key_from_vk(0x10, 0x36, False), "shiftright")
        self.assertEqual(key_from_vk(0x11, 0x1D, False), "controlleft")
        self.assertEqual(key_from_vk(0x11, 0x1D, True), "controlright")
        self.assertEqual(key_from_vk(0x12, 0x38, False), "altleft")
        self.assertEqual(key_from_vk(0x12, 0x38, True), "altright")

    def test_side_specific_modifiers(self):
        self.assertEqual(key_from_vk(0xA0, 0x2A, False), "shiftleft")
        self.assertEqual(key_from_vk(0xA1, 0x36, False), "shiftright")
        self.assertEqual(key_from_vk(0xA2, 0x1D, False), "controlleft")
        self.assertEqual(key_from_vk(0xA3, 0x1D, True), "controlright")
        self.assertEqual(key_from_vk(0xA4, 0x38, False), "altleft")
        self.assertEqual(key_from_vk(0xA5, 0x38, True), "altright")
        self.assertEqual(key_from_vk(0x5B, 0x5B, True), "metaleft")
        self.assertEqual(key_from_vk(0x5C, 0x5C, True), "metaright")

    def test_modifier_fallback_without_scan(self):
        self.assertEqual(key_from_vk(0x10, 0, False), "shiftleft")
        self.assertEqual(key_from_vk(0x11, 0, False), "controlleft")
        self.assertEqual(key_from_vk(0x12, 0, False), "altleft")

    def test_unknown_vk(self):
        self.assertIsNone(key_from_vk(0xFF, 0xFF, False))

    def test_is_modifier(self):
        for key in ("shiftleft", "controlright", "altleft", "metaright"):
            self.assertTrue(is_modifier(key))
        for key in ("a", "1", "enter", "f5"):
            self.assertFalse(is_modifier(key))


if __name__ == "__main__":
    unittest.main()
