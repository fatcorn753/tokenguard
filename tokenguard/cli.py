"""tokenguard: Claude Code のトークン消費を計測し、どこを削れば効くかを示す。

使い方:
  tokenguard report [--days 14] [--top 10]   全体の内訳・重いセッション・重いツール
  tokenguard trend  [--days 28]              日ごとの消費と平均文脈の推移(対策の効果確認用)
  tokenguard session <id の先頭>             1 セッションの文脈の伸び方
  tokenguard ctx <transcript.jsonl>          直近の文脈サイズ(hook のデバッグ用)
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys

from . import transcripts as T


def _m(n: float) -> str:
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}k"
    return f"{n:.0f}"


def cmd_report(a) -> None:
    ss = T.load(a.days)
    calls = [c for s in ss for c in s.calls]
    if not calls:
        print("該当する会話ログがありません")
        return
    tot = {k: sum(getattr(c, k) for c in calls) for k in ("input", "cache_write", "cache_read", "output")}
    w = {k: tot[k] * T.WEIGHTS[k] for k in tot}
    W = sum(w.values())
    ctx = sorted(c.context for c in calls)
    print(f"# 直近 {a.days:g} 日: {len(ss)} 会話(subagent {sum(s.is_subagent for s in ss)}), API 呼び出し {len(calls)} 回")
    print(f"重み付き消費(入力トークン換算) {_m(W)}")
    for k in tot:
        print(f"  {k:12s} {_m(tot[k]):>8s}  費用の {w[k] / W:5.1%}")
    print(f"1 回あたりの文脈: 中央値 {_m(ctx[len(ctx) // 2])} / 平均 {_m(statistics.mean(ctx))} / p90 {_m(ctx[int(len(ctx) * .9)])}")
    firsts = sorted(s.calls[0].context for s in ss if not s.is_subagent)
    if firsts:
        # 会話の最初の呼び出し ≒ システムプロンプト・ツール定義・CLAUDE.md などの固定分
        print(f"固定分(会話の初回文脈): 中央値 {_m(firsts[len(firsts) // 2])}")
    for th in (200_000, 400_000):
        share = sum(c.weighted for c in calls if c.context > th) / W
        print(f"  文脈 {_m(th)} 超の呼び出しが費用の {share:.0%}")

    bym = collections.Counter()
    for c in calls:
        bym[c.model] += c.weighted
    print("\n## モデル別")
    for k, v in bym.most_common(6):
        print(f"  {k:28s} {v / W:5.1%}")

    print(f"\n## 重い会話 上位 {a.top}")
    ss.sort(key=lambda s: s.weighted, reverse=True)
    for s in ss[:a.top]:
        avg = sum(c.context for c in s.calls) / len(s.calls)
        print(f"  {s.sid[:8]} {s.weighted / W:5.1%} 呼出{len(s.calls):5d} 平均文脈{_m(avg):>5s} 最大{_m(s.peak):>5s}"
              f" compact{s.compactions:2d} 画像{s.images:4d}  {s.title}")

    tools = collections.defaultdict(lambda: [0, 0])
    for s in ss:
        for k, (n, size) in s.tools.items():
            tools[k][0] += n
            tools[k][1] += size
    print("\n## ツール結果の量(文字数。画像は base64 込みなので実トークンより大きく出る)")
    for k, (n, size) in sorted(tools.items(), key=lambda x: -x[1][1])[:a.top]:
        print(f"  {k:40s} {_m(size):>7s} {n:6d}回 平均{_m(size / n):>5s}")
    print("\n## 診断")
    for line in diagnose(ss, calls, W):
        print("  - " + line)


def diagnose(ss, calls, W) -> list[str]:
    out = []
    cr = sum(c.cache_read for c in calls) * T.WEIGHTS["cache_read"] / W
    if cr > 0.4:
        out.append(f"費用の {cr:.0%} が cache read。長い会話の文脈を毎回読み直している。"
                   "autoCompactWindow を下げる・作業の区切りで新しい会話にする(/handoff)のが最も効く")
    long_ = [s for s in ss if len(s.calls) > 500]
    if long_:
        out.append(f"500 回超の会話が {len(long_)} 件(費用の {sum(s.weighted for s in long_) / W:.0%})。区切りで分ける")
    imgs = sum(s.images for s in ss)
    if imgs > 100:
        out.append(f"画像が {imgs} 枚、文脈に入った。スクリーンショットより read_page/get_page_text、画像は縮小して読む")
    out_share = sum(c.output for c in calls) * T.WEIGHTS["output"] / W
    if out_share < 0.15:
        out.append(f"output は費用の {out_share:.0%} だけ。返答を短くする工夫(caveman 等)の効果は小さい")
    return out


def cmd_trend(a) -> None:
    ss = T.load(a.days)
    day = collections.defaultdict(list)
    for s in ss:
        for c in s.calls:
            day[c.ts[:10]].append(c)
    print("日付        呼出   重み付き   平均文脈")
    for d in sorted(day):
        cs = day[d]
        print(f"{d} {len(cs):6d} {_m(sum(c.weighted for c in cs)):>9s} {_m(statistics.mean(c.context for c in cs)):>9s}")


def cmd_session(a) -> None:
    hits = [p for p in T.PROJECTS.rglob(f"{a.sid}*.jsonl")]
    if not hits:
        sys.exit(f"{a.sid} に当たる会話がありません")
    s = T.parse(hits[0])
    print(f"{s.sid} {s.title} ({s.cwd}) 呼出 {len(s.calls)} compact {s.compactions}")
    step = max(1, len(s.calls) // 20)
    for i in range(0, len(s.calls), step):
        c = s.calls[i]
        print(f"  #{i:5d} {c.ts[11:19]} 文脈 {_m(c.context):>6s} " + "#" * int(c.context / 25_000))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="tokenguard", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("report")
    r.add_argument("--days", type=float, default=14)
    r.add_argument("--top", type=int, default=10)
    t = sp.add_parser("trend")
    t.add_argument("--days", type=float, default=28)
    se = sp.add_parser("session")
    se.add_argument("sid")
    cx = sp.add_parser("ctx")
    cx.add_argument("transcript")
    a = p.parse_args(argv)
    if a.cmd == "ctx":
        print(T.last_context(a.transcript))
        return
    {"report": cmd_report, "trend": cmd_trend, "session": cmd_session}[a.cmd](a)


if __name__ == "__main__":
    main()
