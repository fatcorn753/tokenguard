GitHub の読み取り結果のみをまとめます。作成・編集・コメント等は行っていません。スター数は取得結果に含まれなかったため、すべて「未確認」です。

## 1. `anthropics/claude-code` の関連 issue

1. **Let plugins read the session's prompt cache lifetime**  
   URL: https://github.com/anthropics/claude-code/issues/110535  
   要点: キャッシュ TTL が 5 分か 1 時間かをプラグインから判別できず、アイドル後の不要な全コンテキスト再書き込みを防げない。50 万トークンでは、キャッシュ読み取りより再書き込みの費用が大きくなると報告。  
   状態: **Open**

2. **Prompt cache misses mid-session within TTL**  
   URL: https://github.com/anthropics/claude-code/issues/108511  
   要点: TTL 内でも `cache_read_input_tokens` が system/tools 部分だけに戻り、会話全体が再度 cache write される事例。約 8,500 リクエスト中 93 回、約 540 万トークンの余分な書き込みを観測。  
   状態: **Open**

3. **Prompt cache: CLAUDE.md context is never shared across sessions**  
   URL: https://github.com/anthropics/claude-code/issues/102042  
   要点: `CLAUDE.md` 等の注入コンテキストが最初のユーザープロンプトと同じ cache segment に入り、セッションごとに再書き込みされる。system prompt 側へ移す、または breakpoint を追加する案が提示されている。  
   状態: **Open**

4. **Prompt-cache forensics from 30 real sessions**  
   URL: https://github.com/anthropics/claude-code/issues/94177  
   要点: 30 セッションの分析で、cache write の 68% が TTL expiry、microcompact、resume/model switch など 36 イベントに集中。キャッシュが冷えたタイミングで compact する、prune をまとめて行う、履歴を bounded にする案が示されている。  
   状態: **Open**

5. **Prompt cache re-written on every user turn; fixed by CLAUDE_CODE_DISABLE_AUTO_MEMORY=1**  
   URL: https://github.com/anthropics/claude-code/issues/96578  
   要点: 特定リポジトリで毎ターン約 24.6k トークンが cache write され、`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` で改善したという報告。hook の `additionalContext` や auto memory が prefix の安定性に影響する可能性がある。  
   状態: **Open**

6. **Subagents use the 5-minute prompt cache while the main session uses 1-hour**  
   URL: https://github.com/anthropics/claude-code/issues/99360  
   要点: メインセッションが 1 時間 TTL でもサブエージェントは 5 分 TTL となり、遅い応答中にキャッシュが失効。16 サブエージェントで約 19.65M cache-write tokens、44 回の大規模 cache miss が発生した。  
   状態: **Open**

7. **Prompt cache lookup fails intermittently mid-session**  
   URL: https://github.com/anthropics/claude-code/issues/87966  
   要点: 長時間セッションで stable prefix 以降の cache lookup が断続的に失敗し、最大 75 万トークンの会話全体を再書き込み。89 回で約 5,900 万 cache-creation tokens、API 換算で約 558 ドル相当の超過と報告。  
   状態: **Closed（not planned）**

8. **Prompt cache repeatedly dropped mid-session**  
   URL: https://github.com/anthropics/claude-code/issues/83542  
   要点: 3 時間で 17 回キャッシュが落ち、毎回 55〜68 万トークンを再書き込み。約 1,041 万 cache-creation tokens、セッション費用の約 60% に相当したと報告。  
   状態: **Closed（not planned）**

9. **Prompt cache misses beyond ~16K prefix in large multimodal subagent**  
   URL: https://github.com/anthropics/claude-code/issues/89621  
   要点: スクリーンショットを大量に含む約 50〜60 万トークンのサブエージェントで、system prefix 約 16k 以外が毎回 cache miss。午後だけで約 3,740 万 cache-write tokens を消費した。  
   状態: **Closed（not planned）**

10. **Unused connectors and MCP servers still cost tokens in every session**  
    URL: https://github.com/anthropics/claude-code/issues/102333  
    要点: 未使用の MCP／connector でもツール名、UUID 付き名称、サーバー instructions が毎セッション読み込まれる。163 ツール名と約 1.7k tokens の instructions が例示され、サーバー単位の遅延ロードが提案されている。  
    状態: **Open**

11. **Subagents receive all MCP servers' instructions**  
    URL: https://github.com/anthropics/claude-code/issues/104791  
    要点: サブエージェントの `tools:` に含まれない MCP サーバーの instructions まで注入され、約 20 サーバーで約 12k tokens の固定オーバーヘッド。許可された MCP だけ注入する仕組みが提案されている。  
    状態: **Open**

12. **Remote Control MCP tools skip tool search and always load**  
    URL: https://github.com/anthropics/claude-code/issues/104651  
    要点: Remote Control の 27 ツール、約 15.8k tokens が毎ターン常時ロードされ、Tool Search の遅延ロード対象にならない。`isDeferred: true` を返す hook では改善できたと報告。  
    状態: **Open**

13. **Per-subagent token visibility and step/context limits**  
    URL: https://github.com/anthropics/claude-code/issues/106025  
    要点: 35 サブエージェントを含む実行で 2.41B tokens の 98% が再送コンテキスト、80 ステップ以降だけで 71% を消費。サブエージェントごとの token/context 表示、step/context 上限、巨大な fork 前の警告を要求している。  
    状態: **Open**

14. **Background subagents have no token, turn or time cap**  
    URL: https://github.com/anthropics/claude-code/issues/94013  
    要点: 背景サブエージェント 3 個が合計 1,710,388 tokens を消費したが、Agent tool に token・turn・時間上限がなかった。`max_tokens`、`max_turns`、`max_duration`、事前承認などが提案されている。  
    状態: **Open**

15. **Tool output is fully expanded by default**  
    URL: https://github.com/anthropics/claude-code/issues/57060  
    要点: 大きな tool 出力の折りたたみ UI が機能せず、履歴の可読性が低下。ただし issue 本文では「context-window usage は影響しない」と明記されており、トークン削減問題とは別の UI 問題。  
    状態: **Closed（not planned）**

## 2. Claude Code 向けの OSS 実装例

| リポジトリ | URL | 仕組み | スター数の目安 |
|---|---|---|---|
| `alexgreensh/token-optimizer` | https://github.com/alexgreensh/token-optimizer | `PostToolUse` で Bash 出力を圧縮し、Bash・Read・Glob・Grep・Agent・`mcp__.*` の結果をアーカイブ。`Stop` で compact checkpoint とメトリクスを保存。 | 未確認 |
| `ojuschugh1/sqz` | https://github.com/ojuschugh1/sqz | Claude Code の `PreToolUse` と `PostToolUse` を利用。Bash 実行前後の出力、Read 結果、MCP tool 結果を決定的に圧縮し、重複結果は短い参照へ置換。ローカルキャッシュと byte-exact 復元も実装。 | 未確認 |
| `zdk/lowfat` | https://github.com/zdk/lowfat | `PreToolUse[Bash]` でコマンドを低ノイズ版へ書き換え、`PostToolUse[Read]` でコメント・関数本体・lock file・JSON 等を圧縮。`lite/full/ultra` の段階設定がある。 | 未確認 |
| `graykode/abtop` | https://github.com/graykode/abtop | hook で rate-limit 情報を収集し、TUI で Claude Code の token 使用量、context window 使用率、サブエージェント、compact 状態を監視。削減処理ではなく、使い過ぎの早期検知に使う道具。 | 未確認 |
| `sirmalloc/ccstatusline` | https://github.com/sirmalloc/ccstatusline | Claude Code の status line に context window、現在の context length、rate limit、compact counter 等を表示。トークン上限接近を把握して早めに `/compact` やセッション分割を判断できる。 | 未確認 |

※ `ccusage` は確認を試みましたが、`ovinc/ccusage` は GitHub API 上で 404 となり、正しいリポジトリを特定できなかったため未掲載です。
