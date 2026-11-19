"""Claude Code の会話ログ(~/.claude/projects/**/*.jsonl)を読み、API 呼び出し単位の使用量に直す。

ログは 1 回の API 応答を content ブロックごとに複数行へ分けて書くので、
同じ message.id の usage が何度も現れる。数え過ぎを防ぐため message.id で重複を除く。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

PROJECTS = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"

# 入力トークン 1 個を 1 とした相対単価。API 単価の比率(cache write 5 分=1.25 倍、
# cache read=0.1 倍、output=5 倍)で、モデルが違っても比率は同じ。
WEIGHTS = {"input": 1.0, "cache_write": 1.25, "cache_read": 0.1, "output": 5.0}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


@dataclass
class Call:
    ts: str
    model: str
    input: int
    cache_write: int
    cache_read: int
    output: int

    @property
    def context(self) -> int:
        return self.input + self.cache_write + self.cache_read

    @property
    def weighted(self) -> float:
        return (self.input * WEIGHTS["input"] + self.cache_write * WEIGHTS["cache_write"]
                + self.cache_read * WEIGHTS["cache_read"] + self.output * WEIGHTS["output"])


@dataclass
class Session:
    sid: str
    path: Path
    title: str = ""
    cwd: str = ""
    calls: list[Call] = field(default_factory=list)
    # ツール名ごとの [回数, 結果の文字数]
    tools: dict[str, list[int]] = field(default_factory=dict)
    images: int = 0
    compactions: int = 0
    is_subagent: bool = False

    @property
    def weighted(self) -> float:
        return sum(c.weighted for c in self.calls)

    @property
    def peak(self) -> int:
        return max((c.context for c in self.calls), default=0)


def _is_title(t: str) -> bool:
    # compact 後の続き要約やシステム差し込みは件名にしない
    return bool(t) and not t.startswith("<") and not t.startswith("This session is being continued")


def _tool_key(block: dict) -> str:
    name = block.get("name", "?")
    if name == "Bash":
        cmd = ((block.get("input") or {}).get("command") or "").split()
        return "Bash:" + (cmd[0] if cmd else "")
    if name == "Read":
        ext = Path((block.get("input") or {}).get("file_path", "")).suffix.lower()
        return "Read:image" if ext in IMAGE_EXT else ("Read:pdf" if ext == ".pdf" else "Read")
    return name


def parse(path: Path) -> Session:
    s = Session(sid=path.stem, path=path, is_subagent="subagents" in path.parts)
    seen: dict[str, Call] = {}
    pending: dict[str, str] = {}
    with open(path, errors="ignore") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            # compact 1 回につき境界行と要約行が両方書かれるので、境界行だけを数える
            if d.get("type") == "system" and d.get("subtype") == "compact_boundary":
                s.compactions += 1
            m = d.get("message")
            if not isinstance(m, dict):
                continue
            if not s.cwd and d.get("cwd"):
                s.cwd = d["cwd"]
            if d.get("type") == "assistant":
                u = m.get("usage") or {}
                mid = m.get("id") or d.get("requestId") or d.get("uuid")
                if u and mid:
                    # 同じ応答の後の行ほど output が確定しているので上書きする
                    seen[mid] = Call(d.get("timestamp", ""), m.get("model", "?"),
                                     u.get("input_tokens") or 0,
                                     u.get("cache_creation_input_tokens") or 0,
                                     u.get("cache_read_input_tokens") or 0,
                                     u.get("output_tokens") or 0)
                for b in m.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        pending[b.get("id")] = _tool_key(b)
            elif d.get("type") == "user":
                c = m.get("content")
                if isinstance(c, str) and not s.title and _is_title(c):
                    s.title = c.strip().replace("\n", " ")[:40]
                if not isinstance(c, list):
                    continue
                for b in c:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text" and not s.title and _is_title(b.get("text", "")):
                        s.title = b["text"].strip().replace("\n", " ")[:40]
                    if b.get("type") == "tool_result":
                        key = pending.get(b.get("tool_use_id"), "?")
                        body = b.get("content")
                        size = len(json.dumps(body, ensure_ascii=False))
                        if isinstance(body, list):
                            s.images += sum(1 for x in body if isinstance(x, dict) and x.get("type") == "image")
                        t = s.tools.setdefault(key, [0, 0])
                        t[0] += 1
                        t[1] += size
    s.calls = sorted((c for c in seen.values() if c.context), key=lambda c: c.ts)
    return s


def load(days: float) -> list[Session]:
    cutoff = time.time() - days * 86400
    out = []
    for p in PROJECTS.rglob("*.jsonl"):
        try:
            if p.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        s = parse(p)
        if s.calls:
            out.append(s)
    return out


def last_context(transcript: str | Path, tail_bytes: int = 400_000) -> int:
    """会話ログの末尾から、直近の API 呼び出しが読んだ文脈の大きさを返す。hook から使う。"""
    try:
        with open(transcript, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            lines = f.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return 0
    for line in reversed(lines):
        if '"usage"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        u = (d.get("message") or {}).get("usage") or {}
        ctx = (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
        if ctx:
            return ctx
    return 0
