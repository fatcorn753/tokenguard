"""tokenguard: Claude Code のトークン消費を計測し、どこを削れば効くかを示す。

使い方:
  tokenguard report [--days 14] [--top 10]   全体の内訳・重いセッション・重いツール
  tokenguard trend  [--days 28]              日ごとの消費と平均文脈の推移(対策の効果確認用)
  tokenguard simulate [--window 200000 300000]  過去ログを別の窓で再計算し、節約量を見積もる
  tokenguard bench [--window ...] [--reps N]    記憶テスト。窓ごとに compact で事実を忘れるかを測る
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

    from .cache import breakdown
    print("\n## cache write の原因(書き直しは 2 倍の単価)")
    names = {"start": "会話の開始", "ttl": "cache 切れ(TTL 超過)", "compact": "compact 直後",
             "break": "TTL 内の書き直し", "incremental": "増分(正常)"}
    for k, (n, tok, wt) in breakdown(ss).items():
        print(f"  {names[k]:18s} {int(n):6d}回 {_m(tok):>7s}  費用の {wt / W:5.1%}")

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
    from .cache import breakdown
    ttl = breakdown(ss)["ttl"]
    if ttl[2] / W > 0.05:
        out.append(f"cache 切れ(1 時間以上空けてから再開)の書き直しが費用の {ttl[2] / W:.0%}。"
                   "長い会話へ時間を空けて戻るときは、別件なら /clear か新しい会話で始める(ttl_guard hook)")
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


def cmd_simulate(a) -> None:
    from .simulate import scenarios, simulate, ttl_scenarios
    ss = T.load(a.days)
    print(f"# 直近 {a.days:g} 日の会話ログを、autoCompactWindow を変えて再計算")
    print("  画像縮小・/handoff による分割は含めない(節約は少なめに出る)。品質の変化は測れない\n")
    rows = []
    for w in a.window:
        for sc in scenarios(w):
            if sc.window is None and rows:
                continue
            rows.append((sc, simulate(ss, sc)))
        if a.clear_on_ttl:
            rows += [(sc, simulate(ss, sc)) for sc in ttl_scenarios(w, a.clear_on_ttl)]
    base = rows[0][1].weighted
    print(f"{'条件':40s} {'重み付き':>9s} {'差':>6s} {'平均文脈':>8s} {'compact':>8s} {'cache切れ':>9s} {'clear':>6s}")
    for sc, r in rows:
        print(f"{sc.name:40s} {_m(r.weighted):>9s} {r.weighted / base - 1:+6.0%} {_m(r.ctx_sum / max(r.calls, 1)):>8s}"
              f" {r.compactions:8d} {r.ttl_events:9d} {r.clears:6d}")


def cmd_bench(a) -> None:
    from dataclasses import asdict

    from .bench import WORK, run_trial
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / "results.jsonl"
    rows = []
    for rep in range(a.reps):
        for w in a.window:  # 条件を交互に回し、時間帯の偏りを減らす
            tr = run_trial(w, a.seed + rep, a.files, a.model, log=lambda m: print(m, file=sys.stderr))
            rows.append(tr)
            with open(out, "a") as f:
                f.write(json.dumps({**asdict(tr), "model": a.model, "files": a.files}, ensure_ascii=False) + "\n")
            print(f"{w // 1000}k s{tr.seed}: 正答 {tr.score}/{tr.total} 誤り {tr.wrong} compact {tr.compactions} "
                  f"最大 {_m(tr.peak)} 重み {_m(tr.weighted)} ${tr.cost_usd:.2f} {tr.seconds:.0f}s {tr.error}", flush=True)
    print(f"\n結果は {out} に追記した")
    bench_summary(rows)


def bench_summary(rows) -> None:
    by = collections.defaultdict(list)
    for r in rows:
        if not r.error:
            by[r.window].append(r)
    print(f"{'窓':>6s} {'試行':>4s} {'正答率':>6s} {'重み平均':>8s} {'USD平均':>8s} {'compact':>7s}")
    for w in sorted(by):
        rs = by[w]
        acc = sum(r.score for r in rs) / max(1, sum(r.total for r in rs))
        print(f"{w // 1000:5d}k {len(rs):4d} {acc:6.0%} {_m(statistics.mean(r.weighted for r in rs)):>8s} "
              f"{statistics.mean(r.cost_usd for r in rs):8.2f} {statistics.mean(r.compactions for r in rs):7.1f}")


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
    si = sp.add_parser("simulate")
    si.add_argument("--days", type=float, default=14)
    si.add_argument("--window", type=int, nargs="+", default=[200_000, 300_000])
    si.add_argument("--clear-on-ttl", type=float, nargs="*", default=[],
                    help="cache 切れの後に /clear する割合(例: 0.25 0.5 1)。ttl_guard の効果の見積もり")
    b = sp.add_parser("bench", help="記憶テスト(claude -p を実際に動かす。使用量を消費する)")
    b.add_argument("--window", type=int, nargs="+", default=[1_000_000, 300_000, 200_000])
    b.add_argument("--reps", type=int, default=1)
    b.add_argument("--files", type=int, default=16, help="埋め草ファイル数(1 つ約 2 万トークン)")
    b.add_argument("--model", default="sonnet")
    b.add_argument("--seed", type=int, default=1)
    se = sp.add_parser("session")
    se.add_argument("sid")
    cx = sp.add_parser("ctx")
    cx.add_argument("transcript")
    a = p.parse_args(argv)
    if a.cmd == "ctx":
        print(T.last_context(a.transcript))
        return
    {"report": cmd_report, "trend": cmd_trend, "simulate": cmd_simulate, "bench": cmd_bench, "session": cmd_session}[a.cmd](a)


if __name__ == "__main__":
    main()
