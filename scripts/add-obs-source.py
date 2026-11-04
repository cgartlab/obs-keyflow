# -*- coding: utf-8 -*-
"""向当前 OBS 场景集合里注入 obs-keyflow 浏览器源（幂等）。

用法（先关闭 OBS，否则 OBS 退出时会覆盖场景文件）：

    python scripts/add-obs-source.py
    python scripts/add-obs-source.py --scene "B站" --url "http://127.0.0.1:16900/?n=6"
    python scripts/add-obs-source.py --dry-run

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
SOURCE_NAME = "按键显示"


def obs_config_root() -> Path:
    return Path.home() / "AppData/Roaming/obs-studio"


def active_scene_file(root: Path) -> Path:
    global_ini = root / "global.ini"
    if global_ini.is_file():
        parser = configparser.ConfigParser()
        parser.read(global_ini, encoding="utf-8")
        name = parser.get("Basic", "SceneCollectionFile", fallback="").strip()
        if name:
            candidate = root / "basic" / "scenes" / name
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


def main() -> int:
    ap = argparse.ArgumentParser(description="把 obs-keyflow 浏览器源注入 OBS 场景")
    ap.add_argument("--scene", default=None, help="目标场景名（默认取当前场景）")
    ap.add_argument("--name", default=SOURCE_NAME, help=f"源名称（默认 {SOURCE_NAME}）")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"浏览器源地址（默认 {DEFAULT_URL}）")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--scene-file", default=None, help="直接指定场景集合 json 路径")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要做的改动")
    args = ap.parse_args()

    root = obs_config_root()
    path = Path(args.scene_file) if args.scene_file else active_scene_file(root)
    print(f"场景集合: {path}")

    if obs_running() and not args.dry_run:
        sys.exit("OBS 正在运行，请先关闭 OBS 再执行（否则退出时会把改动覆盖掉）")

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
            "url": args.url,
            "width": args.width,
            "height": args.height,
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
        "locked": True,
        "rot": 0.0,
        "scale_ref": {"x": args.width, "y": args.height},
        "align": 5,
        "bounds_type": 0, "bounds_align": 0, "bounds_crop": False,
        "crop_left": 0, "crop_top": 0, "crop_right": 0, "crop_bottom": 0,
        "id": next_id,
        "group_item_backup": False,
        "pos": {"x": 0.0, "y": 0.0},
        "pos_rel": {"x": -1.7777777910232544, "y": -1.0},
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

    print(f"场景: {scene_name}  |  图层顺序: " +
          " | ".join(i["name"] for i in scene["settings"]["items"]))
    print(f"新增源: {args.name}  url={args.url}  item_id={next_id}")

    if args.dry_run:
        print("[dry-run] 未写入文件")
        return 0

    backup = path.with_suffix(path.suffix + ".keyflow-backup")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"备份: {backup.name}")
    path.write_bytes(json.dumps(data, ensure_ascii=False, indent=4).encode("utf-8"))
    print("已写入。重新打开 OBS 即可看到该源。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
