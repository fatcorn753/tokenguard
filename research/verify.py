#!/usr/bin/env python3
"""調査役(agy)が出した主張の引用が、出典の本文に実在するかを機械的に確かめる。

使い方: python3 -I research/verify.py research/raw/*.out
  - 各主張の URL を取得し、HTML を本文テキストに直して、quote が含まれるかを見る
  - 比較の前に、空白・引用符・ダッシュ・大文字小文字をそろえる(言い換えは通さない)
  - arXiv の abs ページで見つからなければ、同じ論文の HTML 版(arxiv.org/html/ID)も見る
  - GitHub の issue は gh で本文とコメントを取る
結果: research/claims.json(全件と判定)と research/claims.md(通ったものの一覧)
取得したページは research/.cache/ に置く(リポジトリには入れない)。
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache"
UA = "Mozilla/5.0 (compatible; citation-check/1.0)"
THEMES = {"a": "a. プロンプト・文脈の圧縮", "b": "b. エージェントの記憶管理", "c": "c. プロンプトキャッシュの仕組みと費用",
          "d": "d. ツール出力の削減", "e": "e. モデルの振り分けとカスケード", "gh_claims": "GitHub の issue・実装例",
          "own_claims": "作業者(Claude)が出典を読んで加えたもの"}


def fetch(url: str) -> str:
    CACHE.mkdir(exist_ok=True)
    f = CACHE / hashlib.sha1(url.encode()).hexdigest()
    if f.exists():
        return f.read_text(errors="ignore")
    m = re.match(r"https://github\.com/([^/]+/[^/]+)/(issues|pull)/(\d+)", url)
    if m:
        cmd = ["gh", "issue" if m[2] == "issues" else "pr", "view", m[3], "-R", m[1], "--json", "title,body,comments"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            d = json.loads(r.stdout)
            text = "\n".join([d.get("title", ""), d.get("body", "")] + [c.get("body", "") for c in d.get("comments", [])])
            f.write_text(text)
            return text
    r = subprocess.run(["curl", "-sL", "--max-time", "40", "-A", UA, url], capture_output=True, timeout=60)
    text = r.stdout.decode("utf-8", "ignore") if r.returncode == 0 else ""
    f.write_text(text)
    return text


def to_text(page: str) -> str:
    page = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?s)<[^>]+>", " ", page)
    return html.unescape(page)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                                   "–": "-", "—": "-", "−": "-", "­": ""}))
    # Markdown の強調記号とリンク記法の括弧は、出典が .md でも HTML でも同じになるよう落とす
    s = re.sub(r"[*_`]", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def loose(s: str) -> str:
    # 記号と空白を全部落とした比較。ハイフネーションや改行位置の違いだけを許す
    return re.sub(r"[^0-9a-z]", "", norm(s))


def candidates(url: str) -> list[str]:
    out = [url]
    m = re.match(r"https?://arxiv\.org/(abs|pdf)/([0-9]+\.[0-9]+)(v\d+)?", url)
    if m:
        out += [f"https://arxiv.org/abs/{m[2]}", f"https://arxiv.org/html/{m[2]}"]
    return list(dict.fromkeys(out))


def check(claim: dict) -> str:
    q = claim.get("quote", "")
    if len(q.split()) < 5 or "..." in q or "…" in q:
        return "rejected:quote-format"
    nq, lq = norm(q), loose(q)
    fetched = False
    for u in candidates(claim.get("url", "")):
        page = fetch(u)
        if not page:
            continue
        fetched = True
        t = to_text(page)
        if nq in norm(t):
            return "verified"
        if len(lq) >= 30 and lq in loose(t):
            return "verified:loose"
    return "rejected:not-found" if fetched else "rejected:unreachable"


def parse_out(path: Path) -> dict:
    text = path.read_text(errors="ignore")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"theme": path.stem, "claims": []}
    try:
        return json.loads(m.group(0))
    except ValueError:
        return {"theme": path.stem, "claims": [], "error": "invalid json"}


def main(paths: list[str]) -> None:
    rows = []
    for p in map(Path, paths):
        d = parse_out(p)
        for c in d.get("claims", []):
            c["theme"] = p.stem
            c["status"] = check(c)
            rows.append(c)
            print(f"{c['status']:22s} {p.stem} {c.get('id', '?')} {c.get('url', '')}", file=sys.stderr)
    (HERE / "claims.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
    ok = [c for c in rows if c["status"].startswith("verified")]
    lines = ["# 検証済みの主張", "",
             f"`verify.py` で引用が出典の本文に実在すると確かめたもの: {len(ok)} / {len(rows)} 件。",
             "落ちたものと理由は `claims.json` の status にある。",
             "「主張」の文は調査役の要約で、引用より踏み込んでいることがある。根拠として使えるのは引用の範囲だけ。", ""]
    for theme in sorted({c["theme"] for c in ok}):
        lines += [f"## {THEMES.get(theme, theme)}", ""]
        for c in ok:
            if c["theme"] != theme:
                continue
            lines += [f"- **{c.get('id')}**({c.get('confidence')}): {c.get('claim')}",
                      f"  - 出典: [{c.get('title') or c['url']}]({c['url']})",
                      f"  - 引用: \"{c.get('quote')}\"",
                      f"  - 使い道: {c.get('applicability', '')}", ""]
    (HERE / "claims.md").write_text("\n".join(lines))
    print(f"verified {len(ok)} / {len(rows)}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
