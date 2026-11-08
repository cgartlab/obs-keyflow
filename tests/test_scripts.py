# -*- coding: utf-8 -*-
"""脚本编码回归测试。

Windows 上这些脚本由「老式」解释器读取，编码不对会直接崩：
  * Windows PowerShell 5.1 对无 BOM 的 UTF-8 .ps1 按 ANSI 解析 —— 中文注释可能把语法打散
  * Windows Script Host 读取 .vbs 用 ANSI —— 非 ASCII 字符有解析风险
两处都踩过坑，这里用测试钉住。
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
UTF8_BOM = b"\xef\xbb\xbf"


class ScriptEncodingTests(unittest.TestCase):
    def test_ps1_files_have_utf8_bom(self):
        files = sorted(SCRIPTS.glob("*.ps1"))
        self.assertTrue(files, "scripts/ 下没有 .ps1 脚本？")
        for path in files:
            with self.subTest(script=path.name):
                data = path.read_bytes()
                self.assertTrue(
                    data.startswith(UTF8_BOM),
                    f"{path.name} 缺少 UTF-8 BOM：Windows PowerShell 5.1 会按 ANSI 解析，中文注释会破坏语法",
                )

    def test_vbs_files_are_ascii_only(self):
        files = sorted(SCRIPTS.glob("*.vbs"))
        self.assertTrue(files, "scripts/ 下没有 .vbs 脚本？")
        for path in files:
            with self.subTest(script=path.name):
                data = path.read_bytes()
                bad = [b for b in data if b > 127]
                self.assertFalse(
                    bad,
                    f"{path.name} 含 {len(bad)} 个非 ASCII 字节：Windows Script Host 按 ANSI 读取，请把注释改成英文",
                )

    def test_ps1_uses_crlf(self):
        for path in sorted(SCRIPTS.glob("*.ps1")):
            with self.subTest(script=path.name):
                data = path.read_bytes()
                self.assertIn(b"\r\n", data, f"{path.name} 应使用 CRLF 换行")


if __name__ == "__main__":
    unittest.main()
