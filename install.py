#!/usr/bin/env python3
"""tokenguard を ~/.claude に組み込む。何度実行しても同じ状態になる。--uninstall で外す。

- settings.json: autoCompactWindow と 3 つの hook を足す(既存の hook は残す)。変更前に .bak を作る
- ~/.claude/skills/handoff: このリポジトリの skills/handoff へのシンボリックリンク
- ~/.local/bin/tokenguard: 計測 CLI
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLAUDE = Path.home() / ".claude"
SETTINGS = CLAUDE / "settings.json"
SKILL = CLAUDE / "skills" / "handoff"
BIN = Path.home() / ".local" / "bin" / "tokenguard"
META = Path.home() / ".cache" / "tokenguard" / "install.json"  # settings.json に未知のキーを足さないため外に置く
# 自分の hook を見分ける目印。clone 先のフォルダ名に依らないよう、スクリプト名で見る
OURS = ("/hooks/ctx_guard.py", "/hooks/img_shrink.py", "/hooks/ttl_guard.py")

HOOKS = {
    "UserPromptSubmit": {"hooks": [{"type": "command", "command": f"python3 {ROOT}/hooks/ctx_guard.py", "timeout": 10},
                                   {"type": "command", "command": f"python3 {ROOT}/hooks/ttl_guard.py", "timeout": 10}]},
    "PreToolUse": {"matcher": "Read", "hooks": [{"type": "command", "command": f"python3 {ROOT}/hooks/img_shrink.py", "timeout": 30}]},
}


def strip_ours(settings: dict) -> None:
    for event, groups in list(settings.get("hooks", {}).items()):
        kept = [g for g in groups if not any(h.get("command", "").endswith(OURS) for h in g.get("hooks", []))]
        if kept:
            settings["hooks"][event] = kept
        else:
            del settings["hooks"][event]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--window", type=int, default=300_000, help="autoCompactWindow (100000〜1000000)")
    a = ap.parse_args()
    if not 100_000 <= a.window <= 1_000_000:
        sys.exit("--window は 100000〜1000000")

    settings = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    if SETTINGS.exists():
        bak = SETTINGS.with_name(f"settings.json.bak-tokenguard-{time.strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(SETTINGS, bak)
        print(f"バックアップ: {bak}")
    strip_ours(settings)
    meta = json.loads(META.read_text()) if META.exists() else {}

    if a.uninstall:
        if "prevAutoCompactWindow" in meta:
            if meta["prevAutoCompactWindow"] is None:
                settings.pop("autoCompactWindow", None)
            else:
                settings["autoCompactWindow"] = meta["prevAutoCompactWindow"]
        META.unlink(missing_ok=True)
        if SKILL.is_symlink():
            SKILL.unlink()
        if BIN.is_symlink():
            BIN.unlink()
        print("外しました")
    else:
        if "prevAutoCompactWindow" not in meta:
            # 元の値を覚えておき、uninstall で戻す
            meta["prevAutoCompactWindow"] = settings.get("autoCompactWindow")
        META.parent.mkdir(parents=True, exist_ok=True)
        META.write_text(json.dumps(meta))
        settings["autoCompactWindow"] = a.window
        for event, group in HOOKS.items():
            settings.setdefault("hooks", {}).setdefault(event, []).append(group)
        SKILL.parent.mkdir(parents=True, exist_ok=True)
        if not SKILL.exists():
            SKILL.symlink_to(ROOT / "skills" / "handoff")
        BIN.parent.mkdir(parents=True, exist_ok=True)
        if not BIN.exists():
            BIN.symlink_to(ROOT / "bin" / "tokenguard")
        print(f"組み込みました: autoCompactWindow={a.window}, hook 3 件, /handoff, {BIN}")

    tmp = SETTINGS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
    json.loads(tmp.read_text())  # 壊れた JSON で上書きしないための確認
    tmp.replace(SETTINGS)


if __name__ == "__main__":
    main()
