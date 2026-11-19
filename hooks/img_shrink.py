#!/usr/bin/env python3
"""PreToolUse hook (Read): 大きな画像を縮小した複製に差し替えて読ませる。

画像のトークンはおよそ 幅×高さ/750 で、一度読んだ画像は会話が続く限り毎回読み直される。
長辺を MAX_EDGE に縮めれば、1568px 上限の画像なら約 3 割減る。
ただし細かい文字が読めなくなる恐れがあるので、同じ画像を 10 分以内にもう一度 Read したら
原寸のまま通す(「読めないので読み直す」が逃げ道になる)。縮小には macOS 標準の sips を使う。
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

MAX_EDGE = int(os.environ.get("TOKENGUARD_IMG_EDGE", "1280"))
CACHE = Path(os.environ.get("TOKENGUARD_IMG_CACHE", Path.home() / ".cache/tokenguard/img"))
EXT = {".png", ".jpg", ".jpeg", ".webp"}
RETRY_SEC = 600


def dims(p: Path):
    if not shutil.which("sips"):  # macOS 以外では何もしない(原寸のまま読ませる)
        return None
    r = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(p)],
                       capture_output=True, text=True, timeout=10)
    v = [int(line.split()[-1]) for line in r.stdout.splitlines() if "pixel" in line]
    return (v[0], v[1]) if len(v) == 2 else None


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    inp = data.get("tool_input") or {}
    src = Path(inp.get("file_path", ""))
    if src.suffix.lower() not in EXT or not src.is_file() or str(src).startswith(str(CACHE)):
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    st = src.stat()
    key = hashlib.sha1(f"{src}:{st.st_mtime_ns}:{st.st_size}".encode()).hexdigest()[:16]
    mark = CACHE / f"{key}.seen"
    # 2 回目の Read(10 分以内)は原寸で通す
    if mark.exists() and time.time() - mark.stat().st_mtime < RETRY_SEC:
        mark.unlink()
        return
    d = dims(src)
    if not d or max(d) <= MAX_EDGE:
        return
    out = CACHE / f"{key}{src.suffix.lower()}"
    if not out.exists():
        r = subprocess.run(["sips", "-Z", str(MAX_EDGE), str(src), "--out", str(out)],
                           capture_output=True, timeout=30)
        if r.returncode or not out.exists():
            return
    mark.touch()
    new = dict(inp, file_path=str(out))
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "updatedInput": new,
        "additionalContext": (f"[tokenguard] {src.name} を長辺 {MAX_EDGE}px に縮小して読ませた(元 {d[0]}x{d[1]})。"
                              "文字が読めなければ同じパスをもう一度 Read すると原寸になる。"),
    }}, ensure_ascii=False))


if __name__ == "__main__":
    main()
