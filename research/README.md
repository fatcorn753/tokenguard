# 調査と判断の記録(2026-11-21)

Claude Code のトークン消費を減らす新しい仕組みを探した記録。文献の主張は、引用が出典の本文に実在すると
スクリプトで確かめたものだけを使う。

## 進め方

1. 調査: agy(Gemini 4 Argon High。agy の CHANGELOG で `pro` サブエージェントが Argon と確認)に、5 つのテーマを
   読み取り専用で並列に調べさせた。各主張に URL・原文の引用・確信度を付けさせた。生の出力は `raw/a〜e.out`
   - a: プロンプト・文脈の圧縮 / b: エージェントの記憶管理 / c: プロンプトキャッシュの仕組みと費用
   - d: ツール出力の削減 / e: モデルの振り分けとカスケード
2. 引用の検証: `verify.py` が各 URL を取得し、引用が本文に含まれるかを機械的に確かめた。
   含まれないものと取得できないものは捨てた。agy の 72 件中 61 件が通った。落ちた 11 件は、OpenAI・vLLM の文書、SGLang・SWE-agent の論文、Manus 記事・
   Anthropic の文書(compaction・costs・building effective agents)の一部で、引用が本文に見つからなかったもの。
   ほかに、根拠に使う GitHub の issue など 5 件(`raw/gh_claims.json`)と、作業者が加えた 1 件(`raw/own_claims.json`)も
   同じ方法で確かめた。結果は `claims.json`(全件と判定)と `claims.md`(通ったもの)
3. 実装例の調査: Copilot(`delegate gh`)で anthropics/claude-code の issue と関連 OSS を調べた。`raw/gh.md`。
   採用の根拠に使った issue は、`gh issue view` で本文を自分で読み直した
4. 発想と見積もり: 検証を通った主張と、作者の会話ログ(14 日・303 会話・36,566 回の呼び出し)の分析から案を出し、
   `tokenguard simulate` を拡張して実ログで効果を見積もった

注意: `claims.md` の「主張」の文は調査役の要約で、引用より踏み込んでいることがある。根拠として使えるのは引用の範囲だけ。

## ログ分析で分かったこと

cache write(費用の 26%)を原因別に分けた(`tokenguard report` の「cache write の原因」)。

| 原因 | 14 日分 | 直近 3 日分(300k 窓の導入後) |
|---|---|---|
| cache 切れ(最後の応答から 1 時間超)の書き直し | 450 回・費用の 15.6% | 42 回・6.1% |
| TTL 内の書き直し(原因不明) | 96 回・2.0% | 15 回・0.8% |
| 増分(正常) | 7.0% | 10.7% |
| 会話の開始 / compact 直後 | 0.9% / 0.4% | 1.6% / 1.3% |

- cache 切れの書き直しが cache write の 6 割。1 回で最大 960k トークンを 2 倍の単価で書き直していた
- 文献側の裏付け: 1 時間 TTL の書き込みは 2 倍(own: ttl1h_price)、cache read は 0.1 倍(c: c2)、cache は使うたびに延長(c: c3)、同種の観察が
  [anthropics/claude-code#94177](https://github.com/anthropics/claude-code/issues/94177)
  (30 会話で cache write の 68% が TTL 切れ・microcompact・resume の 36 回に集中)
- サブエージェントは費用の 0.45% だけだった

## 案と判断(期待効果の大きい順)

| 案 | 見積もり(300k 窓を基準) | 判断 | 理由 |
|---|---|---|---|
| **ttl_guard**: cache が切れた長い会話へ戻ったとき、送信を一度止めて別件なら /clear を促す | 14 日 -2.8〜-7.7%、直近 3 日 -1.1〜-2.6%(/clear の割合 25〜100%) | **採用** | 費用が増える場面がない(続きなら送り直すだけ)。hook だけで作れる |
| **cache write の原因の計測**(`report`) | 計測のみ | **採用** | 上の案の前提。利用者ごとに効くかを先に判断できる |
| **simulate の書き直し量の上限**(修正) | 300k 窓の 14 日見積もり -30% → -39% | **採用** | 窓で小さくなった文脈に、実ログの巨大な書き直しを数えていた誤り |
| 55 分放置で自動 compact(cache が切れる前に縮める。sparkjoy と同じ考え方) | 標準 -9.8% / -3.6%、悲観 +5.5% / +10.1% | 見送り | 要約が大きいと費用が増える。戻らない会話でも compact が走る。hook は放置中に動けない(プラグイン API が要る)。先行実装がある |
| cache を温め続ける(1 時間以内に軽い呼び出しを送る) | 未計算 | 見送り | cache は使うたびに無料で延長される(c3)が、デスクトップアプリと CLI でシステムプロンプトが違い(固定分 70k と 28k)、外から送る呼び出しでは同じ prefix を作れない。戻らない会話でも費用がかかる |
| ツール出力の圧縮(LLMLingua 系・observation masking・hook での grep) | 未計算 | 見送り | Claude Code は古いツール結果を自動で消している。圧縮はコードの正確さを損なう恐れがあり品質検証が重い。同種の OSS(sqz、lowfat、token-optimizer)が既にある |
| モデルの振り分け(Explore を Haiku に・カスケード) | サブエージェントは費用の 0.45% | 見送り | この利用者では効く余地がほぼない。主会話のモデル変更は品質の判断なので道具では決めない |
| ツール定義の遅延読み込み(Tool Search) | — | 見送り | Claude Code の MCP は既にツール定義を遅延読み込みしている(d: mcp_tool_search_default) |
| 記憶の外出し(MemGPT 系・memory tool) | — | 見送り | /handoff と auto memory で既にある。MEMORY.md は 200 行の上限(b: automemlimit)より十分小さい |
| TTL 内の書き直しの防止 | 2.0% / 0.8% | 見送り | Claude Code 側の問題([#108511](https://github.com/anthropics/claude-code/issues/108511))。利用者側では防げない。`report` で見えるようにはした |

## 再現方法

```bash
bin/tokenguard report                     # cache write の原因
bin/tokenguard simulate --window 300000 --clear-on-ttl 0.25 0.5 1
bin/tokenguard simulate --days 3 --window 300000 --clear-on-ttl 0.25 0.5 1
python3 -I research/verify.py research/raw/[a-e].out research/raw/gh_claims.json research/raw/own_claims.json   # 引用の検証(取得したページは research/.cache/)
```
