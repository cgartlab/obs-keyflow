# -*- coding: utf-8 -*-
"""向当前 OBS 场景集合里注入 obs-keyflow 浏览器源（幂等）。

默认生成**紧凑、未锁定、可直接鼠标拖拽**的部件源：
浏览器源尺寸 = 可拖动的边框，内容在框内自动居中/缩放（页面侧 ?fit=1），
所以在 OBS 预览里用鼠标拖这个框就能移动按键。

用法（先关闭 OBS，否则 OBS 退出时会覆盖场景文件）：

    python scripts/add-obs-source.py                    # 底部居中，880x160 可拖部件
    python scripts/add-obs-source.py --pos "1240,760"   # 指定位置
    python scripts/add-obs-source.py --full-canvas      # 老方案：铺满画布 + ?anchor=/?margin=
    python scripts/add-obs-source.py --dry-run          # 只预览不写入

默认会读取 OBS 的 global.ini 找到「当前场景集合」，不用手写文件名。
"""
from __future__ import annotations

import argparse
import configparser
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:16900/"
WIDGET_URL = "http://127.0.0.1:16900/?fit=1"
SOURCE_NAME = "按键显示"


def obs_config_root() -> Path:
    return Path.home() / "AppData/Roaming/obs-studio"


def active_scene_file(root: Path) -> Path:
    global_ini = root / "global.ini"
    if global_ini.is_file():
        # OBS 写出的 global.ini 带 BOM，configparser 直接读会报 MissingSectionHeader，
        # 所以按 utf-8-sig 解码后再解析，失败则退回逐行扫描。
        name = ""
        try:
            text = global_ini.read_bytes().decode("utf-8-sig")
            parser = configparser.ConfigParser()
            parser.read_string(text)
            name = parser.get("Basic", "SceneCollectionFile", fallback="").strip()
        except (configparser.Error, OSError, UnicodeDecodeError):
            name = ""
        if not name:
            try:
                text = global_ini.read_bytes().decode("utf-8-sig", errors="replace")
                for line in text.splitlines():
                    if line.strip().startswith("SceneCollectionFile="):
                        name = line.split("=", 1)[1].strip()
                        break
            except OSError:
                name = ""
        if name:
            candidates = [name]
            if not name.lower().endswith(".json"):
                candidates.append(name + ".json")      # global.ini 里常只存集合名，不带扩展名
            for cand in candidates:
                candidate = root / "basic" / "scenes" / cand
                if candidate.is_file():
                    return candidate
    scenes = sorted((root / "basic" / "scenes").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not scenes:
        sys.exit("找不到任何 OBS 场景集合文件")
    print(f"[提示] 未能从 global.ini 读到当前集合，改用最新的 {scenes[0].name}")
    return scenes[0]


def obs_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe"],
                             capture_output=True, text=True, timeout=10).stdout
        return "obs64.exe" in out
    except Exception:
        return False


def parse_pair(text: str, what: str) -> tuple[int, int]:
    """接受 "1920x1080" 或 "1920,1080" 两种写法。"""
    raw = str(text).strip().lower().replace("x", ",").replace("*", ",")
    try:
        a, b = (int(x.strip()) for x in raw.split(","))
        return a, b
    except Exception:
        sys.exit(f'--{what} 需要形如 "宽x高" 或 "x,y"，收到: {text!r}')


def main() -> int:
    ap = argparse.ArgumentParser(description="把 obs-keyflow 浏览器源注入 OBS 场景（默认紧凑可拖拽部件）")
    ap.add_argument("--scene", default=None, help="目标场景名（默认取当前场景）")
    ap.add_argument("--name", default=SOURCE_NAME, help=f"源名称（默认 {SOURCE_NAME}）")
    ap.add_argument("--url", default=None, help="浏览器源地址（默认按模式决定）")
    ap.add_argument("--canvas", default="1920x1080", help="画布尺寸，用于算默认位置（默认 1920x1080）")
    ap.add_argument("--width", type=int, default=880, help="部件模式源宽度（默认 880）")
    ap.add_argument("--height", type=int, default=160, help="部件模式源高度（默认 160）")
    ap.add_argument("--pos", default=None, help='源位置 "x,y"；默认水平居中、距底 40px')
    ap.add_argument("--anchor", default=None, help="写进 URL 的 anchor（仅 --full-canvas 有意义）")
    ap.add_argument("--margin", type=int, default=None, help="写进 URL 的 margin（仅 --full-canvas 有意义）")
    ap.add_argument("--full-canvas", action="store_true",
                    help="老方案：源铺满整块画布，用 URL 的 anchor/margin 定位（不能直观拖拽）")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--scene-file", default=None, help="直接指定场景集合 json 路径")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要做的改动")
    args = ap.parse_args()

    root = obs_config_root()
    path = Path(args.scene_file) if args.scene_file else active_scene_file(root)
    print(f"场景集合: {path}")

    if obs_running() and not args.dry_run:
        sys.exit("OBS 正在运行，请先关闭 OBS 再执行（否则退出时会把改动覆盖掉）")

    canvas_w, canvas_h = parse_pair(args.canvas, "canvas")

    if args.full_canvas:
        width, height = canvas_w, canvas_h
        query = []
        if args.anchor:
            query.append(f"anchor={args.anchor}")
        if args.margin is not None:
            query.append(f"margin={args.margin}")
        url = args.url or (DEFAULT_URL + ("?" + "&".join(query) if query else ""))
        pos = (0, 0)
        locked = True
    else:
        width, height = args.width, args.height
        url = args.url or WIDGET_URL
        pos = parse_pair(args.pos, "pos") if args.pos else ((canvas_w - width) // 2, canvas_h - height - 40)
        locked = False          # 关键：不锁定才能在预览里用鼠标拖

    data = json.loads(path.read_bytes().decode("utf-8-sig"))
    scene_name = args.scene or data.get("current_scene") or data["sources"][0]["name"]
    scene = next((s for s in data["sources"] if s["id"] == "scene" and s["name"] == scene_name), None)
    if scene is None:
        available = [s["name"] for s in data["sources"] if s["id"] == "scene"]
        sys.exit(f"找不到场景 {scene_name!r}，可选: {available}")

    # 幂等：先移除同名源
    old_uuids = {s["uuid"] for s in data["sources"] if s["name"] == args.name}
    data["sources"] = [s for s in data["sources"] if s["name"] != args.name]
    scene["settings"]["items"] = [
        i for i in scene["settings"]["items"] if i.get("source_uuid") not in old_uuids
    ]

    used = [i["id"] for i in scene["settings"]["items"]]
    next_id = max(used + [scene["settings"].get("id_counter", 1)]) + 1
    scene["settings"]["id_counter"] = next_id + 1
    src_uuid = str(uuid.uuid4())

    source = {
        "prev_ver": 536870914,
        "name": args.name,
        "uuid": src_uuid,
        "id": "browser_source",
        "versioned_id": "browser_source",
        "settings": {
            "url": url,
            "width": width,
            "height": height,
            "fps": args.fps,
            "fps_custom": True,
            "css": "",
            "shutdown": False,
            "restart_when_active": False,
            "reroute_audio": False,
            "is_local_file": False,
        },
        "mixers": 0, "sync": 0, "flags": 0,
        "volume": 1.0, "balance": 0.5,
        "enabled": True, "muted": False,
        "push-to-mute": False, "push-to-mute-delay": 0,
        "push-to-talk": False, "push-to-talk-delay": 0,
        "hotkeys": {},
        "deinterlace_mode": 0, "deinterlace_field_order": 0,
        "monitoring_type": 0,
        "private_settings": {},
    }
    item = {
        "name": args.name,
        "source_uuid": src_uuid,
        "visible": True,
        "locked": locked,
        "rot": 0.0,
        "scale_ref": {"x": canvas_w, "y": canvas_h},
        "align": 5,
        "bounds_type": 0, "bounds_align": 0, "bounds_crop": False,
        "crop_left": 0, "crop_top": 0, "crop_right": 0, "crop_bottom": 0,
        "id": next_id,
        "group_item_backup": False,
        "pos": {"x": float(pos[0]), "y": float(pos[1])},
        # OBS 32 以 pos_rel 为准（相对画布中心，按画布半高归一化）；pos 只是缓存值
        "pos_rel": {
            "x": (pos[0] - canvas_w / 2) / (canvas_h / 2),
            "y": (pos[1] - canvas_h / 2) / (canvas_h / 2),
        },
        "scale": {"x": 1.0, "y": 1.0},
        "scale_rel": {"x": 1.0, "y": 1.0},
        "bounds": {"x": 0.0, "y": 0.0},
        "bounds_rel": {"x": 0.0, "y": 0.0},
        "scale_filter": "area",
        "blend_method": "default", "blend_type": "normal",
        "show_transition": {"duration": 0},
        "hide_transition": {"duration": 0},
        "private_settings": {},
    }
    hk = scene.setdefault("hotkeys", {})
    hk[f"libobs.show_scene_item.{next_id}"] = []
    hk[f"libobs.hide_scene_item.{next_id}"] = []

    data["sources"].append(source)
    scene["settings"]["items"].append(item)      # 末尾 = 最上层

    mode = "full-canvas（铺满画布）" if args.full_canvas else "widget（紧凑可拖拽）"
    print(f"场景: {scene_name}   模式: {mode}   锁定: {locked}")
    print(f"源尺寸: {width}x{height}  位置: x={pos[0]} y={pos[1]}   url={url}")
    print("图层顺序: " + " | ".join(i["name"] for i in scene["settings"]["items"]))

    if args.dry_run:
        print("[dry-run] 未写入文件")
        return 0

    backup = path.with_suffix(path.suffix + ".keyflow-backup")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"备份: {backup.name}")
    path.write_bytes(json.dumps(data, ensure_ascii=False, indent=4).encode("utf-8"))
    print("已写入。重新打开 OBS 后，在预览里直接拖这个源即可移动按键。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
