# -*- coding: utf-8 -*-
"""Virtual-key code → stable key id.

The ids produced here are a public contract: the web overlay and any third-party
consumer rely on them.  Display labels live in the web layer (``web/index.html``),
so the server stays presentation-free.
"""
from __future__ import annotations

# Windows reports generic VKs (0x10/0x11/0x12) and left/right VKs (0xA0..0xA5)
# depending on how the event was injected or produced.
MOD_VK: dict[int, str] = {
    0x10: "shiftleft", 0xA0: "shiftleft", 0xA1: "shiftright",
    0x11: "controlleft", 0xA2: "controlleft", 0xA3: "controlright",
    0x12: "altleft", 0xA4: "altleft", 0xA5: "altright",
    0x5B: "metaleft",
    0x5C: "metaright",
}

# Scan codes disambiguate the physical left/right modifier.
MOD_SCAN: dict[int, str] = {
    0x2A: "shiftleft", 0x36: "shiftright",
    0x1D: "controlleft", 0xE01D: "controlright",
    0x38: "altleft", 0xE038: "altright",
}

VK_NAMES: dict[int, str] = {}
for _c in range(ord("A"), ord("Z") + 1):
    VK_NAMES[_c] = chr(_c).lower()
for _c in range(ord("0"), ord("9") + 1):
    VK_NAMES[_c] = chr(_c)
for _i in range(1, 13):
    VK_NAMES[0x6F + _i] = f"f{_i}"
for _i in range(10):
    VK_NAMES[0x60 + _i] = f"numpad{_i}"
VK_NAMES.update({
    0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x1B: "esc", 0x20: "space",
    0x14: "capslock", 0x90: "numlock", 0x91: "scrolllock", 0x13: "pause",
    0x2C: "printscreen", 0x2D: "insert", 0x2E: "delete",
    0x24: "home", 0x23: "end", 0x21: "pageup", 0x22: "pagedown",
    0x25: "arrowleft", 0x26: "arrowup", 0x27: "arrowright", 0x28: "arrowdown",
    0xBA: "semicolon", 0xBB: "equal", 0xBC: "comma", 0xBD: "minus",
    0xBE: "period", 0xBF: "slash", 0xC0: "backquote",
    0xDB: "bracketleft", 0xDC: "backslash", 0xDD: "bracketright", 0xDE: "quote",
    0x5D: "contextmenu",
    # numpad operators
    0x6A: "numpadmultiply", 0x6B: "numpadadd", 0x6D: "numpadsubtract",
    0x6E: "numpaddecimal", 0x6F: "numpaddivide",
    # media / system keys — without these they would silently vanish
    0xAD: "audiomute", 0xAE: "volumeup", 0xAF: "volumedown",
    0xB0: "medianext", 0xB1: "mediaprev", 0xB2: "mediastop", 0xB3: "mediaplay",
})

# Canonical modifier order used when rendering combos (Ctrl → Win → Alt → Shift).
MOD_ORDER: dict[str, int] = {
    "controlleft": 0, "controlright": 0,
    "metaleft": 1, "metaright": 1,
    "altleft": 2, "altright": 2,
    "shiftleft": 3, "shiftright": 3,
}


def key_from_vk(vk: int, scan: int, extended: bool) -> str | None:
    """Resolve a raw low-level hook event to a stable key id."""
    mod = MOD_VK.get(vk)
    if mod is not None:
        s = (scan | 0xE000) if extended else scan
        return MOD_SCAN.get(s) or MOD_SCAN.get(scan) or mod
    if vk not in VK_NAMES and scan in MOD_SCAN:
        return MOD_SCAN[scan]
    return VK_NAMES.get(vk)


def is_modifier(key_id: str) -> bool:
    return key_id in MOD_ORDER
