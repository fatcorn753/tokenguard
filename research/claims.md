# 検証済みの主張

`verify.py` で引用が出典の本文に実在すると確かめたもの: 67 / 78 件。
落ちたものと理由は `claims.json` の status にある。
「主張」の文は調査役の要約で、引用より踏み込んでいることがある。根拠として使えるのは引用の範囲だけ。

## a. プロンプト・文脈の圧縮

- **llmlingua**(high): LLMLingua は小規模な言語モデルでプロンプト内のトークン重要度を計算し、予算制御と反復的トークン圧縮によって性能劣化を最小限に抑えつつ最大 20 倍のプロンプト圧縮を達成する。
  - 出典: [microsoft/LLMLingua: To speed up LLMs' inference and enhance LLM's perceive of key information, compress the prompt and KV-Cache, which achieves up to 20x compression with minimal performance loss.](https://github.com/microsoft/LLMLingua)
  - 引用: "This approach enables efficient inference with large language models (LLMs), achieving up to 20x compression with minimal performance loss."
  - 使い道: Claude Code の PreToolUse や UserPromptSubmit フック、あるいは外部ラッパースクリプトで長大なドキュメントやログを事前圧縮してからコンテキストに投入する運用に利用できる。

- **longllmlingua**(high): 質問認識型のプロンプト圧縮を行う LongLLMLingua は、長文脈における位置バイアスを緩和しつつ約 4 分の 1 のトークン数で精度を最大 21.4% 向上させ、LooGLE ベンチマークでは 94.0% のコスト削減を達成する。
  - 出典: [LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression](https://arxiv.org/abs/2310.06839)
  - 引用: "For instance, in the NaturalQuestions benchmark, LongLLMLingua boosts performance by up to 21.4% with around 4x fewer tokens in GPT-3.5-Turbo, leading to substantial cost savings. It achieves a 94.0% cost reduction in the LooGLE benchmark."
  - 使い道: Claude Code で長大なコードベースや複数ファイルを参照する際、現在の質問・タスクに関連する箇所だけを抽出・圧縮して渡すスキルや MCP サーバーの設計に応用できる。

- **llmlingua2**(high): LLMLingua-2 は双方向 Transformer エンコーダによるトークン分類としてプロンプト圧縮を定式化し、2〜5 倍の圧縮率でエンドツーエンドのレイテンシを 1.6〜2.9 倍高速化しつつ、従来の圧縮手法より 3〜6 倍高速に動作する。
  - 出典: [LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression](https://arxiv.org/abs/2403.12968)
  - 引用: "Additionally, our model is 3x-6x faster than existing prompt compression methods, while accelerating the end-to-end latency by 1.6x-2.9x with compression ratios of 2x-5x."
  - 使い道: 軽量な双方向エンコーダをローカルのコマンド出力フィルタや PostToolUse フックに組み込み、追加の API 呼び出しコストなしでツール出力を 2〜5 分の 1 に高速圧縮する仕組みに使える。

- **selective_context**(high): Selective Context は小型言語モデルが計算する自己情報量（self-information）に基づいて冗長な語彙単位を枝刈りし、下流タスクの性能低下をわずかに抑えながら文脈コストを 50%、推論時間を 32% 削減する。
  - 出典: [Compressing Context to Enhance Inference Efficiency of Large Language Models](https://arxiv.org/abs/2310.06201)
  - 引用: "Specifically, we achieve a 50% reduction in context cost, resulting in a 36% reduction in inference memory usage and a 32% reduction in inference time, while observing only a minor drop of .023 in BERTscore"
  - 使い道: Claude Code に読み込ませる長大な技術文書やログから情報量の低い定型句・反復表現をローカル前処理スクリプトで枝刈りし、cache write/read 対象トークン数を半減させる運用に使える。

- **recomp**(high): RAG 向けの圧縮手法 RECOMP は、取得文書を抽出型・生成型コンプレッサで要約し無関係な場合は空文字を返す選択的拡張と組み合わせることで、性能劣化を最小限に抑えつつ原文比 6% までの高圧縮率を達成する。
  - 出典: [RECOMP: Improving Retrieval-Augmented LMs with Compression and Selective Augmentation](https://arxiv.org/abs/2310.04408)
  - 引用: "We achieve a compression rate of as low as 6% with minimal loss in performance for both tasks, significantly outperforming the off-the-shelf summarization models."
  - 使い道: Claude Code の検索系スキルやサブエージェントにおいて、検索結果全文をメイン会話に返すのではなくタスクに無関係なら空を返し関係箇所のみ約 6% に要約して返す設計に活用できる。

- **gist_tokens**(high): Gist Tokens は Attention マスクの制御により長文プロンプトを少数のキャッシュ・再利用可能なトークン集合へ圧縮するよう学習させ、出力品質をほぼ損なわずにプロンプトを最大 26 倍圧縮し FLOPs を最大 40% 削減する。
  - 出典: [Learning to Compress Prompts with Gist Tokens](https://arxiv.org/abs/2304.08467)
  - 引用: "On decoder (LLaMA-7B) and encoder-decoder (FLAN-T5-XXL) LMs, gisting enables up to 26x compression of prompts, resulting in up to 40% FLOPs reductions, 4.2% wall time speedups, and storage savings, all with minimal loss in output quality."
  - 使い道: API 利用者側でモデルの Attention は直接変更できないが、反復利用する長大な規約や指示を極小の要約ブロックへ事前集約してキャッシュ再利用する CLAUDE.md・スキル設計の指針になる。

- **autocompressor**(high): AutoCompressor は最大 30,720 トークンの長文脈をセグメント単位で処理してコンパクトな要約ベクトル（soft prompts）へ再帰的に圧縮し、長文脈の情報を保持したまま推論コスト削減と精度向上を両立する。
  - 出典: [Adapting Language Models to Compress Contexts](https://arxiv.org/abs/2305.14788)
  - 引用: "We fine-tune OPT and Llama-2 models on sequences of up to 30,720 tokens and show that AutoCompressors can utilize long contexts to improve perplexity."
  - 使い道: Claude Code の長期セッションにおいて、長大な作業履歴や例示を一度に保持せずフェーズごとの短いチェックポイント要約へ段階的に畳み込む /compact 運用の理論的根拠として活用できる。

- **obs_masking_cost**(high): コーディングエージェントにおいて過去の思考・行動履歴を保持したまま古いツール出力（observation）のみをプレースホルダに置換する Observation Masking は、無圧縮時に比べてコストを半減させつつ LLM 要約と同等以上の解決率を達成する。
  - 出典: [The Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent Context Management](https://arxiv.org/abs/2508.21433)
  - 引用: "We find that a simple environment Observation Masking strategy halves cost relative to the Raw Agent while matching, and sometimes slightly exceeding, the solve rate of LLM-Summary."
  - 使い道: Claude Code のフックや MCP ツール設計で、数ターン前の巨大なファイル読取結果やテストログだけを短いプレースホルダやファイルパス参照に置き換え、思考過程は残す履歴管理に直接応用できる。

- **obs_masking_hybrid**(high): 古いツール出力を隠す Observation Masking を第一段階とし、文脈がさらに伸びた段階で LLM 要約を組み合わせるハイブリッド手法は、Observation Masking 単体よりさらに 7%、LLM 要約単体より 11% コストを削減する。
  - 出典: [The Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent Context Management](https://arxiv.org/abs/2508.21433)
  - 引用: "Additionally, we introduce a novel hybrid approach that further reduces costs by 7% and 11% compared to just Observation Masking or LLM-Summary, respectively."
  - 使い道: Claude Code で普段はツール出力の抑制（フックやサブエージェント）で文脈膨張を防ぎ、セッションが長引いた節目でのみ /compact（LLM 要約）を実行する二段構えの運用指針として使える。

- **jetbrains_obs_masking**(high): JetBrains Research の実証では、Observation Masking は要約生成用の追加 API 呼び出しを必要とせず、古いノイズの多いツール出力のみをプレースホルダで隠して直近の関連作業だけを残すため、高速かつ安価に文脈肥大化を防げる。
  - 出典: [Cutting Through the Noise: Smarter Context Management for LLM-Powered Agents](https://blog.jetbrains.com/research/2025/12/efficient-context-management/)
  - 引用: "We designed it this way because observation masking is fast and inexpensive: it hides old, noisy tool outputs with placeholders, keeping only the most relevant part of the agent's work as it moves forward."
  - 使い道: Claude Code で頻繁に /compact を呼んでキャッシュを再構築・要約トークンを消費するよりも、最初からツール出力自体を小さく保つフック設計を優先すべき根拠になる。

- **anthropic_context_editing**(high): Claude API のツール結果クリア機能は古いツール出力を削除して文脈を圧縮するが、削除のたびにキャッシュ済みプレフィックスが無効化され cache write コストが発生するため、clear_at_least で一度に十分なトークン数をまとめて削除する必要がある。
  - 出典: [Context editing - Claude Platform Docs](https://platform.claude.com/docs/en/build-with-claude/context-editing)
  - 引用: "Invalidates cached prompt prefixes when content is cleared. To account for this, clear enough tokens to make the cache invalidation worthwhile. Use the clear_at_least parameter to ensure a minimum number of tokens is cleared each time."
  - 使い道: 1 時間 TTL の cache write 単価が入力の 2 倍である前提下では、毎ターン少しずつ履歴を削るとキャッシュ破棄で逆効果になるため、文脈圧縮は一定の閾値に達した時点でまとめてバッチ実行する運用にすべきである。

- **claude_code_hooks_preprocess**(high): Claude Code のカスタムフックでツール出力を事前処理し、例えば 10,000 行のログファイルをそのまま読ませる代わりに ERROR 行のみを grep して返すことで、コンテキスト消費を数万トークンから数百トークンへ約 2 桁削減できる。
  - 出典: [Manage costs effectively - Claude Code Docs](https://code.claude.com/docs/en/costs)
  - 引用: "Instead of Claude reading a 10,000-line log file to find errors, a hook can grep for ERROR and return only matching lines, reducing context from tens of thousands of tokens to hundreds."
  - 使い道: テスト実行やビルド出力をフィルタリングする PreToolUse / PostToolUse フックや専用スキルを設定し、生ログがメイン文脈に入って cache write（26%）と以降の cache read（64%）を押し上げるのを未然に防げる。

## b. エージェントの記憶管理

- **memgpt**(high): OSの仮想メモリに着想を得た「仮想コンテキスト管理」により、高速な主記憶（コンテキストウィンドウ）と低速な外部記憶の間でデータを移動させることで、固定長のコンテキスト上限を超えた記憶領域を扱える。
  - 出典: [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560)
  - 引用: "we propose virtual context management, a technique drawing inspiration from hierarchical memory systems in traditional operating systems that provide the appearance of large memory resources through data movement between fast and slow memory."
  - 使い道: 常駐させる作業記憶（CLAUDE.md・MEMORY.md）を最小限に絞り、過去の調査ログや設計履歴を外部ファイルやSQLiteへ退避して必要時のみツールでページインする階層化メモリ運用に応用できる。

- **letta**(high): LettaのMemory Blocks（コアメモリ）はコンテキストウィンドウ内に常駐する構造化セクションであり、検索ツールを介さずに全ターンで常に参照される一方、総量を5万文字未満・20ブロック未満に抑える階層設計が推奨されている。
  - 出典: [Memory blocks (core memory) | Letta Docs](https://docs.letta.com/v1-sdk/memory/memory-blocks)
  - 引用: "Memory blocks are structured sections of the agent's context window that persist across all interactions. They are always visible - no retrieval needed."
  - 使い道: 毎ターンのcache read（費用の64%）に乗る常駐コンテキストを固定サイズの構造化ブロック（現在のゴール・制約のみ）に制限し、それ以外をオンデマンド参照のスキルや外部ファイルへ分離する設計指針になる。

- **mem0**(high): 会話履歴から重要情報を動的に抽出・統合・検索するMem0アーキテクチャは、全会話履歴をコンテキストに入れるフルコンテキスト方式と比較して、LLM-as-a-Judge指標を改善しつつp95レイテンシを91%削減し、トークン費用を90%以上削減する。
  - 出典: [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413)
  - 引用: "In particular, Mem0 attains a 91% lower p95 latency and saves more than 90% token cost, offering a compelling balance between advanced reasoning capabilities and practical deployment constraints."
  - 使い道: 長いセッションの生ログを保持し続ける代わりに、StopやPreCompactのhookで会話から決定事項やファクトだけを抽出して外部メモリに統合し、早めに/clearや/compactで文脈長をリセットする運用に使える。

- **amem**(high): Zettelkasten手法に基づくA-MEMは、新しい記憶の追加時に文脈説明・キーワード・タグを含む構造化ノートを生成し、既存の記憶とのリンク構築や既存記憶の属性更新（Memory Evolution）を動的に行うことで6つの基盤モデルで従来手法を上回る。
  - 出典: [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110)
  - 引用: "Following the basic principles of the Zettelkasten method, we designed our memory system to create interconnected knowledge networks through dynamic indexing and linking."
  - 使い道: Claude Codeのauto memoryやプロジェクト知識を単一ファイルに追記し続けるのではなく、タグと相互リンクを持つ小さなトピック別Markdownノート群としてスキルで管理・更新させることで、必要なノートだけを低トークンで読み込める。

- **genagents**(high): Generative Agentsは、自然言語による経験の全記録（メモリ・ストリーム）をそのまま使うだけでなく、時間経過とともに高次の抽象的な洞察（reflection）へ定期的に合成し、動的に検索して行動計画に利用する。
  - 出典: [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442)
  - 引用: "we describe an architecture that extends a large language model to store a complete record of the agent's experiences using natural language, synthesize those memories over time into higher-level reflections, and retrieve them dynamically to plan behavior."
  - 使い道: セッション終了時やタスク区切りで実行するreflectionスキルを定義し、冗長な試行錯誤の履歴を数行の教訓・設計原則へ抽象化してMEMORY.mdやrulesへ昇格させることで、次セッション以降の文脈長を大幅に圧縮できる。

- **readagent**(high): 長文をエピソード単位に区切って短い要約（gist memory）に圧縮し、詳細が必要な箇所だけ原文をインタラクティブに引き直すReadAgentは、3つの長文読解ベンチマークでベースラインを上回りつつ実効コンテキスト長を3.5〜20倍に拡張する。
  - 出典: [A Human-Inspired Reading Agent with Gist Memory of Very Long Contexts](https://arxiv.org/abs/2402.09727)
  - 引用: "These evaluations are performed on three long-document reading comprehension tasks: QuALITY, NarrativeQA, and QMSum. ReadAgent outperforms the baselines on all three tasks while extending the effective context window by 3.5-20x."
  - 使い道: 大規模コードベースや長い仕様書を丸ごと読み込ませず、各ファイル・モジュールの数行のgist（要約と行番号インデックス）を先に参照させ、該当行だけをReadツールで部分取得するスキル運用に直結する。

- **ctxmgmt84**(high): Claude Developer Platformのcontext editing（古いツール実行結果の自動消去など）は、100ターンのWeb検索評価において文脈枯渇による失敗を防ぎつつ、トークン消費量を84%削減した。
  - 出典: [Managing context on the Claude Developer Platform](https://www.anthropic.com/news/context-management)
  - 引用: "In a 100-turn web search evaluation, context editing enabled agents to complete workflows that would otherwise fail due to context exhaustion—while reducing token consumption by 84%."
  - 使い道: 長大になりがちなツール出力（検索結果・テスト出力・ログ）をメイン文脈に残さないよう、サブエージェントへの委譲やPostToolUse/PreToolUseのhookによる出力フィルタリングを行うことで同等のトークン削減効果を得られる。

- **ctxmgmt39**(high): Anthropicの評価において、context editing単体でベースライン比29%の性能向上が得られ、さらにmemory tool（ファイルベースの外部記憶）と組み合わせることで39%の性能向上が達成された。
  - 出典: [Managing context on the Claude Developer Platform](https://www.anthropic.com/news/context-management)
  - 引用: "The results demonstrate significant gains: combining the memory tool with context editing improved performance by 39% over baseline. Context editing alone delivered a 29% improvement."
  - 使い道: Claude Codeで/compactや/clearによって古い文脈を消去する前に、重要な中間調査結果を作業用Markdownファイルへ書き出させるワークフローをCLAUDE.mdやスキルでルール化することで、精度向上とコスト削減を両立できる。

- **ctxedit**(high): Context editingとmemory toolを併用すると、コンテキストが消去閾値に近づいた際に自動警告が送られ、古いツール結果が履歴から消去される前に重要情報をメモリファイルへ退避できる。
  - 出典: [Context editing - Claude Platform Docs](https://platform.claude.com/docs/en/build-with-claude/context-editing)
  - 引用: "When your conversation context approaches the configured clearing threshold, Claude receives an automatic warning to preserve important information. This allows Claude to save tool results or context to its memory files before they're cleared from the conversation history."
  - 使い道: Claude CodeのPreCompact hookやトークン使用量監視（status line / usage）を活用し、コンパクションが走る直前に必要な状態や未完了タスクを外部ファイルに退避させる自動運用を構築できる。

- **ctxeditcache**(high): 会話途中のツール結果を消去するとプロンプトキャッシュのプレフィックスが無効化されるため、clear_at_leastパラメータで1回あたりに消去する最小トークン数を指定し、キャッシュ破棄のコストに見合う場合のみ消去を発動させる設計が重要である。
  - 出典: [Context editing - Claude Platform Docs](https://platform.claude.com/docs/en/build-with-claude/context-editing)
  - 引用: "Ensures a minimum number of tokens is cleared each time the strategy activates. If the API can't clear at least the specified amount, the strategy isn't applied. This helps determine whether context clearing is worth breaking your prompt cache."
  - 使い道: 1時間TTLのcache write単価が入力の2倍・cache readが費用の64%を占める前提では、細切れに/compactを行うとキャッシュ再構築（cache write）が頻発するため、十分なトークンが溜まった段階やタスク切替時にまとめて/compact・/clearする運用基準として使える。

- **memtool**(high): Memory toolは、あらゆる関連情報を事前にコンテキストへ読み込むのではなく、学習した内容をメモリファイル群へ記録し、必要な時にオンデマンドで読み戻すJust-in-Timeな文脈取得を実現する。
  - 出典: [Memory tool - Claude Platform Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
  - 引用: "Memory supports just-in-time context retrieval. Rather than loading all relevant information up front, an agent records what it learns in memory files and reads them back on demand."
  - 使い道: プロジェクト固有の仕様や過去のトラブルシューティングをすべてCLAUDE.mdに書かず、ディレクトリやファイル単位の外部ドキュメントおよびスキルに切り出して必要時のみReadさせる運用に直接適用できる。

- **ctxeng**(high): Anthropicが提唱する構造化ノートテイキング（agentic memory）は、エージェントがコンテキストウィンドウ外の永続メモリに定期的にノートを書き出し、後から必要に応じてコンテキストに引き戻すことで、最小限のオーバーヘッドで長期タスクの一貫性を維持する。
  - 出典: [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  - 引用: "Structured note-taking, or agentic memory, is a technique where the agent regularly writes notes persisted to memory outside of the context window. These notes get pulled back into the context window at later times."
  - 使い道: 進捗チェックリストや調査メモを会話履歴内だけで追うのではなく、NOTES.mdやTODOファイルへ随時書き出させてから/clearで文脈をリセットし、新セッションでそのノートだけを読み込む運用により累積cache readを大幅に抑えられる。

- **claudemdsize**(high): Claude Code公式ドキュメントでは、CLAUDE.mdファイルは1ファイルあたり200行未満を目標とすることが推奨されており、長すぎるファイルは毎ターンのコンテキストを消費するだけでなく指示への追従性も低下させる。
  - 出典: [How Claude remembers your project](https://code.claude.com/docs/en/memory)
  - 引用: "Size: target under 200 lines per CLAUDE.md file. Longer files consume more context and reduce adherence."
  - 使い道: ルートCLAUDE.mdを200行未満（理想的には数十行の必須コマンドと規約のみ）に削ぎ落とし、特定タスク用の手順はオンデマンド読み込みされるスキル（.claude/skills/）やpath指定ルール（.claude/rules/）へ移すことで全リクエストの基礎トークンを削減できる。

- **automemlimit**(high): Claude Codeのauto memoryにおいて、毎セッション開始時に自動ロードされるのはMEMORY.mdの先頭200行または25KBのいずれか早い方までであり、それを超える内容はセッション開始時には読み込まれない。
  - 出典: [How Claude remembers your project](https://code.claude.com/docs/en/memory)
  - 引用: "The first 200 lines of MEMORY.md, or the first 25KB, whichever comes first, are loaded at the start of every conversation. Content beyond that threshold is not loaded at session start."
  - 使い道: MEMORY.mdが200行上限まで膨らむと毎セッションの初期cache write/readコストが増大するため、MEMORY.mdは簡潔な目次（インデックス）として保ち、詳細は別トピックファイルへ分割して定期整理する運用が有効である。

- **costshooks**(high): Claude Codeのカスタムhookでデータを前処理し、例えば1万行のログファイルをClaudeに直接読ませる代わりにhookでERROR行だけをgrepして返すことで、コンテキスト消費を数万トークンから数百トークンへ削減できる。
  - 出典: [Manage costs effectively](https://code.claude.com/docs/en/costs)
  - 引用: "Instead of Claude reading a 10,000-line log file to find errors, a hook can grep for ERROR and return only matching lines, reducing context from tens of thousands of tokens to hundreds."
  - 使い道: テスト実行・ビルドログ・大容量ファイル検索などをhookやラッパースクリプトで要約・フィルタリングしてからコンテキストに渡すことで、1時間TTLの巨大なcache writeおよび後続全ターンのcache read膨張を根本から防げる。

## c. プロンプトキャッシュの仕組みと費用

- **c1**(high): Anthropic の Prompt Caching におけるキャッシュ書き込み（cache write）単価は、デフォルトの 5 分 TTL では基本入力トークン単価の 1.25 倍、拡張された 1 時間 TTL（ttl: "1h"）では基本入力単価の 2 倍に設定されている。
  - 出典: [Prompt caching - Anthropic](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
  - 引用: "Cache write tokens with a 5-minute TTL are 1.25 times the base input tokens price."
  - 使い道: Claude Code で 1 時間 TTL（単価 2 倍）の cache write が費用全体の 26% を占めているため、5 分以内に連続 호출される対話セッションでは 5 分 TTL を選択するか、不要なキャッシュ再書き込み（キャッシュミス）を防ぐ運用で書き込みコストを直接削減できる。

- **c2**(high): Anthropic のキャッシュ読み込み（cache read / hit）単価はほとんどのモデルで基本入力トークン単価の 0.1 倍（90% 割引）であり、1 時間 TTL 書き込み（2 倍）と比較すると 20 分の 1 の単価で処理される。
  - 出典: [Prompt caching - Anthropic](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
  - 引用: "Cache read tokens are 0.1 times the base input tokens price (see the table footnote for per-model exceptions)."
  - 使い道: キャッシュヒットしても累積コンテキストが肥大化すると cache read が費用の 64% に達するため、キャッシュヒット率を維持しつつ、不要になった古い履歴を計画的に切り詰める二段階のコスト制御が有効になる。

- **c3**(high): Anthropic のプロンプトキャッシュはデフォルトで 5 分間の有効期限（TTL）を持つが、キャッシュされたコンテンツが再利用（ヒット）されるたびに追加費用なしで TTL が自動延長される。
  - 出典: [Prompt caching - Anthropic](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
  - 引用: "By default, the cache has a 5-minute lifetime. The cache is refreshed for no additional cost each time the cached content is used."
  - 使い道: Claude Code の利用者が離席して TTL が切れると高価な全文 cache write（入力の 2 倍）が再発生するため、長時間放置する前に `/compact` やセッション区切りを行う運用ルールが有効である。

- **c4**(high): Anthropic API では 1 リクエストあたり最大 4 つのキャッシュブレークポイント（cache_control）を設定でき、変更頻度の異なるセクション（ツール定義、システム指示、対話履歴など）を独立してキャッシュ管理できる。
  - 出典: [Prompt caching - Anthropic](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
  - 引用: "You can define up to 4 cache breakpoints if you want to: Cache different sections that change at different frequencies"
  - 使い道: Claude Code のプロキシやラッパー運用において、不変のツール定義・CLAUDE.md と、頻繁に追記されるメッセージ履歴の境界にブレークポイントを分けて配置することで、部分的な変更時の再書き込みトークン量を最小化できる。

- **c5**(high): Anthropic のプロンプトキャッシュにはモデルごとに最小キャッシュ可能トークン長（1,024〜4,096 トークン等）が定められており、それに満たない短いプレフィックスは cache_control を付与してもエラーなくキャッシュ対象外となる。
  - 出典: [Prompt caching - Anthropic](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
  - 引用: "Shorter prompts cannot be cached, even if marked with cache_control. Any requests to cache fewer than this number of tokens are processed without caching, and no error is returned."
  - 使い道: サブエージェントや軽量スキルを呼び出す際、システムプロンプトとツール定義の合計が最小トークン長を超えるか確認し、短命な単発タスクでは無理に長大な共通プレフィックスを載せない設計が有効である。

- **c6**(high): Anthropic のキャッシュプレフィックスは `tools` → `system` → `messages` の厳密な階層順序で構築され、上位階層を変更するとその階層だけでなく下位階層すべてのキャッシュが連鎖的に無効化される。
  - 出典: [Prompt caching - Anthropic](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
  - 引用: "Cache prefixes are created in the following order: tools, system, then messages. This order forms a hierarchy where each level builds upon the previous ones."
  - 使い道: セッション途中で MCP サーバーのツール定義（tools）や CLAUDE.md（system）を書き換えると数十万トークンの messages キャッシュまで全て無効化され 2 倍単価の cache write が発生するため、セッション中のツール・システム変更を禁止する運用が必須となる。

- **c7**(high): ツール定義の変更はキャッシュ全体を無効化し、system プロンプトの変更は system と messages を無効化するほか、画像の追加・削除、tool_choice の変更、thinking パラメータ（有効化や budget_tokens）の変更も messages 等のキャッシュを無効化する。
  - 出典: [Prompt caching - Anthropic](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
  - 引用: "Modifications to cached content can invalidate some or all of the cache. As described in Structuring your prompt, the cache follows the hierarchy: tools → system → messages. Changes at each level invalidate that level and all subsequent levels."
  - 使い道: Claude Code 利用時に会話の途中で Extended Thinking の ON/OFF や effort 設定を頻繁に切り替えたり、過去ターンの画像を動的に削除したりするとキャッシュミスを誘発するため、セッション開始時に thinking 設定を固定する運用が推奨される。

- **c8**(high): Claude Code はシステムプロンプトなどの反復コンテンツに対するプロンプトキャッシュと、コンテキスト上限接近時に対話履歴を要約する auto-compaction を組み合わせて自動的にコストを最適化している。
  - 出典: [Manage costs effectively - Claude Code Docs](https://code.claude.com/docs/en/costs)
  - 引用: "Claude Code automatically optimizes costs through prompt caching, which reduces costs for repeated content like system prompts, and auto-compaction, which summarizes conversation history when approaching context limits"
  - 使い道: コンテキスト上限に達して自動コンパクションが走るまで待つと毎ターンの cache read 費用が膨らむため、タスクの区切りごとに手動で `/compact` または `/clear` を実行してプレフィックス長自体を短縮する運用が効果的である。

- **c13**(high): Manus の本番 AI エージェントでは入力と出力のトークン比率が平均約 100:1 に達し、Claude Sonnet ではキャッシュ済み入力が 0.30 USD/MTok、非キャッシュ入力が 3 USD/MTok と 10 倍の価格差があるため、KV キャッシュヒット率が最重要指標となる。
  - 出典: [Context Engineering for AI Agents: Lessons from Building Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
  - 引用: "with Claude Sonnet, for instance, cached input tokens cost 0.30 USD/MTok, while uncached ones cost 3 USD/MTok—a 10x difference."
  - 使い道: Claude Code でも入力トークンが圧倒的割合（cache read 64% + cache write 26% = 90%）を占めるため、出力トークン削減よりもキャッシュミス（cache write の再発生）をゼロに近づける hook・プロンプト設計を最優先すべきである。

- **c14**(high): LLM の自己回帰的な性質上、プロンプト先頭付近に秒単位のタイムスタンプや非決定的な JSON キー順序による 1 トークンの差異が生じるだけで、その位置以降の KV キャッシュがすべて無効化されるため、コンテキストは追記専用（append-only）かつ決定論的に保つ必要がある。
  - 出典: [Context Engineering for AI Agents: Lessons from Building Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
  - 引用: "Due to the autoregressive nature of LLMs, even a single-token difference can invalidate the cache from that token onward"
  - 使い道: Claude Code の PreToolUse / PostToolUse hook や MCP ツール出力で JSON を返す際はキーを必ずソート（決定論的シリアライズ）し、システムプロンプトや過去ログを遡って書き換えない追記専用の運用を徹底することでキャッシュ無効化を防げる。

## d. ツール出力の削減

- **tool_search_85pct**(high): 全ツール定義を事前読み込みせず defer_loading でオンデマンド検索する Tool Search Tool により、大規模ツール群へのアクセスを維持したままトークン消費を 85% 削減できる。さらに大規模ツールライブラリ利用時の MCP 評価精度も大幅に向上する。
  - 出典: [Introducing advanced tool use on the Claude Developer Platform](https://www.anthropic.com/engineering/advanced-tool-use)
  - 引用: "This represents an 85% reduction in token usage while maintaining access to your full tool library. Internal testing showed significant accuracy improvements on MCP evaluations when working with large tool libraries."
  - 使い道: 多数の MCP サーバーを接続する際、ツール定義の遅延読み込み（Tool Search）を有効に保ち、毎ターンの cache write/read に乗る初期コンテキスト肥大化を防ぐ。

- **mcp_tool_search_default**(high): Claude Code の MCP Tool Search はセッション開始時にツール名とサーバー指示のみを読み込み、完全なツール定義は Claude が必要とするまで遅延読み込みすることでコンテキスト消費を低く抑える。
  - 出典: [Connect Claude Code to tools via MCP - Claude Code Docs](https://code.claude.com/docs/en/mcp)
  - 引用: "Tool search keeps MCP context usage low by deferring tool definitions until Claude needs them. Only tool names and server instructions load at session start, so adding more MCP servers has minimal impact on your context window."
  - 使い道: 実験的ベータ機能を無効化せずデフォルトの Tool Search を維持するとともに、不要な MCP サーバーや高コストな汎用サーバーは gh 等の CLI 呼び出しへ置き換えて初期プレフィックスを最小化する。

- **ptc_sandbox_filtering**(high): コード実行環境内でツールを呼び出し中間結果をフィルタリング・集計してから最終結果のみを返す Programmatic Tool Calling（PTC）により、複雑な調査タスクの平均トークン消費が 43,588 から 27,297 トークンへ 37% 削減される。
  - 出典: [Introducing advanced tool use on the Claude Developer Platform](https://www.anthropic.com/engineering/advanced-tool-use)
  - 引用: "By keeping intermediate results out of Claude's context, PTC dramatically reduces token consumption. Average usage dropped from 43,588 to 27,297 tokens, a 37% reduction on complex research tasks."
  - 使い道: 大量の生データを直接会話履歴に返させず、Python ワンライナーや jq・awk スクリプトを Bash で実行してフィルタリング・集計済みの最終出力だけをコンテキストに読み込ませるスキルを定義する。

- **context_editing_84pct**(high): 古いツール結果を閾値超過時に消去する Context Editing 機能により、100 ターンの Web 検索評価においてコンテキスト枯渇による失敗を防ぎつつトークン消費を 84% 削減できる。
  - 出典: [Managing context on the Claude Developer Platform](https://www.anthropic.com/news/context-management)
  - 引用: "In a 100-turn web search evaluation, context editing enabled agents to complete workflows that would otherwise fail due to context exhaustion—while reducing token consumption by 84%."
  - 使い道: 長期セッションで過去の大量のツール結果が毎ターンの cache read 費用を押し上げ続けるのを防ぐため、調査フェーズ完了時などの区切りで /compact や /clear を実行して古いツール出力を履歴から切り離す。

- **clear_at_least_cache_tradeoff**(high): サーバー側の古いツール結果消去（clear_tool_uses_20250919）はプロンプトキャッシュのプレフィックスを無効化するため、clear_at_least パラメータで1回あたりに消去する最小トークン数を保証し、キャッシュ破棄に見合う場合のみ発動させる仕組みとなっている。
  - 出典: [Context editing - Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/context-editing)
  - 引用: "Ensures a minimum number of tokens is cleared each time the strategy activates. If the API can't clear at least the specified amount, the strategy isn't applied. This helps determine whether context clearing is worth breaking your prompt cache."
  - 使い道: 1時間 TTL（単価2倍）の cache write 再発生コストを上回る削減効果を得るため、毎ターン細かく履歴を削るのではなく、コンテキストが一定量膨らんだ時点でまとめて履歴圧縮を行う運用とする。

- **observation_masking_complexity_trap**(high): SWE-bench Verified における比較実験で、古いツール出力（observation）を単純にプレースホルダーへ置換する Observation Masking は、無圧縮エージェント比でコストを半減させつつ、高コストな LLM 要約と同等以上の解決率を達成する。
  - 出典: [The Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent Context Management](https://arxiv.org/abs/2508.21433)
  - 引用: "We find that a simple environment observation masking strategy halves cost relative to the raw agent while matching, and sometimes slightly exceeding, the solve rate of LLM summarization."
  - 使い道: 追加の LLM 出力トークンを消費する要約だけに頼らず、ツール出力自体を最初から短く切り詰めるか一時ファイルへ退避して参照パスのみを履歴に残す hook を併用し、履歴トークンを半減させる。

- **hooks_log_filtering**(high): カスタム hook でツール出力を前処理し、10,000 行のログ全文を Claude に読ませる代わりに ERROR 行のみを grep して返すことで、コンテキスト消費を数万トークンから数百トークンへ削減できる。
  - 出典: [Manage costs effectively - Claude Code Docs](https://code.claude.com/docs/en/costs)
  - 引用: "Instead of Claude reading a 10,000-line log file to find errors, a hook can grep for ERROR and return only matching lines, reducing context from tens of thousands of tokens to hundreds."
  - 使い道: settings.json の PreToolUse hook でテスト実行やログ取得コマンドをラッパースクリプトへ書き換え、失敗したテストや ERROR 行だけを標準出力に返すように構成する。

- **subagent_verbose_isolation**(high): テスト実行・ドキュメント取得・ログ処理などの冗長な出力を伴う操作をサブエージェントに委譲することで、大量のツール出力をサブエージェントの独立コンテキストに隔離し、メイン会話には要約のみを返せる。
  - 出典: [Manage costs effectively - Claude Code Docs](https://code.claude.com/docs/en/costs)
  - 引用: "Running tests, fetching documentation, or processing log files can consume significant context. Delegate these to subagents so the verbose output stays in the subagent's context while only a summary returns to your main conversation."
  - 使い道: テスト実行やログ解析専用のカスタムサブエージェント（model: haiku 指定）を .claude/agents/ に定義し、メインセッションのキャッシュプレフィックスに巨大な生出力が混入するのを防ぐ。

- **subagent_token_distillation_ratio**(high): サブエージェントが数万トークン以上を消費して広範な探索を行っても、メインエージェントへは 1,000〜2,000 トークン程度に凝縮された要約のみを返すことで、メイン文脈の肥大化を抑えられる。
  - 出典: [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  - 引用: "Each subagent might explore extensively, using tens of thousands of tokens or more, but returns only a condensed, distilled summary of its work (often 1,000-2,000 tokens)."
  - 使い道: コードベース探索スキルに context: fork を設定してサブエージェント実行とし、返却フォーマットを該当ファイルパス・行番号・要点の 2,000 トークン以内に制限する。

- **just_in_time_lightweight_identifiers**(high): 関連データを事前にすべて前処理して読み込むのではなく、ファイルパスや保存済みクエリなどの軽量な識別子（参照）のみを保持し、実行時に必要なデータだけをツールで動的に遅延読み込み（Just-in-Time）することでコンテキストを節約できる。
  - 出典: [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  - 引用: "Rather than pre-processing all relevant data up front, agents built with the “just in time” approach maintain lightweight identifiers (file paths, stored queries, web links, etc.) and use these references to dynamically load data into context at runtime using tools."
  - 使い道: CLAUDE.md には長大な仕様書を展開せずファイルパスと1行索引のみを記載し、詳細なドキュメントや巨大なコマンド出力は必要になった時点で該当箇所だけを遅延参照させる。

- **code_intelligence_lsp_navigation**(high): 型付き言語向けのコードインテリジェンス（LSP）プラグインを導入すると、grep 検索後に複数の候補ファイルを読む代わりに1回の「定義へ移動（go to definition）」呼び出しで済むため、探索時の不要なファイル読み込みを削減できる。
  - 出典: [Manage costs effectively - Claude Code Docs](https://code.claude.com/docs/en/costs)
  - 引用: "Code intelligence plugins give Claude precise symbol navigation instead of text-based search, reducing unnecessary file reads when exploring unfamiliar code. A single “go to definition” call replaces what might otherwise be a grep followed by reading multiple candidate files."
  - 使い道: プロジェクトで使用する言語の code intelligence プラグインを有効化し、テキスト検索と複数候補ファイルの全文 Read による大量のツール出力や手動コンパイル出力を削減する。

- **aider_repomap_token_budget**(high): Aider のリポジトリマップは、コードベースの依存グラフから現在の対話状態に最も関連する箇所のみを特定・索引化し、--map-tokens（デフォルト 1k トークン）の予算内に収めて送信することで全文読み込みを代替する。
  - 出典: [Repository map | aider](https://aider.chat/docs/repomap.html)
  - 引用: "The optimization identifies and maps the portions of the code base which are most relevant to the current state of the chat. The token budget is influenced by the --map-tokens switch, which defaults to 1k tokens."
  - 使い道: ファイルの実装全文を Read する前に tree-sitter や ctags でクラス・関数シグネチャの索引だけを約 1,000 トークン以内で出力するスクリプトを用意し、必要なシンボルのみを行指定で読む運用にする。

## e. モデルの振り分けとカスケード

- **frugalgpt-cascade**(high): クエリごとに適切なLLMの組み合わせを学習して順次呼び出すLLMカスケード（FrugalGPT）により、最上位の単一モデル（GPT-4など）と同等の性能を維持しながら最大98%のコスト削減、または同一コストで最大4%の精度向上が達成できる。
  - 出典: [FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance](https://arxiv.org/abs/2305.05176)
  - 引用: "Our experiments show that FrugalGPT can match the performance of the best individual LLM (e.g. GPT-4) with up to 98% cost reduction or improve the accuracy over GPT-4 by 4% with the same cost."
  - 使い道: Claude Codeのスキルやhookでタスクをまず安価なHaikuやSonnetのサブエージェントに処理させ、失敗や確信度不足のときのみOpusへエスカレーションするカスケード運用に適用できる。

- **routellm-preference**(high): 選好データで学習した軽量ルーターモデル（RouteLLM）が推論時に強モデルと弱モデルを動的に選択することで、応答品質を損なうことなく推論コストを半分以下（2倍以上のコスト効率）に削減できる。
  - 出典: [RouteLLM: Learning to Route LLMs with Preference Data](https://arxiv.org/abs/2406.18665)
  - 引用: "To address this dilemma, we propose several efficient router models that dynamically select between a stronger and a weaker LLM during inference, aiming to optimize the balance between cost and response quality."
  - 使い道: UserPromptSubmit hookやLiteLLM等のプロキシでプロンプトの難易度を事前分類し、単純な依頼ではサブエージェントや小モデルへ自動誘導する仕組みとして導入できる。

- **automix-self-verification**(high): 小規模モデルの出力に対するfew-shot自己検証で信頼度を推定し大モデルへのルーティングを判断するAutoMixにより、同等の性能を保ちながら計算コストを50%以上削減できる。
  - 出典: [AutoMix: Automatically Mixing Language Models](https://arxiv.org/abs/2310.12963)
  - 引用: "Experiments across five language models and five challenging datasets show that Automix consistently surpasses strong baselines, reducing computational cost by over 50% for comparable performance."
  - 使い道: 軽量モデル（Haiku/Sonnet）のサブエージェントにコード生成とテスト・自己検証をセットで実行させ、検証を通過しなかった場合のみ親または上位モデルが介入するスキル設計に使える。

- **hybrid-llm-routing**(high): 予測されるクエリ難易度と要求品質レベルに基づいて小モデルと大モデルへ振り分けるHybrid LLMにより、応答品質を一切落とさずに大規模モデルへの呼び出し回数を最大40%削減できる。
  - 出典: [Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing](https://arxiv.org/abs/2404.14618)
  - 引用: "In experiments our approach allows us to make up to 40% fewer calls to the large model, with no drop in response quality."
  - 使い道: 長い文脈でのcache read（64%）とcache write（26%）の単価が高い上位モデルの呼び出し回数を減らすため、定型タスクを小モデルへ事前振り分けする運用ルールとして有効である。

- **moa-layered-agents**(high): 複数のオープンソースLLMを階層的に連携させるMixture-of-Agents（MoA）は、AlpacaEval 2.0において単一の高性能モデルGPT-4 Omni（57.5%）を上回る65.1%を達成し、小・中規模モデルの協調で高いコスト効率を実現する。
  - 出典: [Mixture-of-Agents Enhances Large Language Model Capabilities](https://arxiv.org/abs/2406.04692)
  - 引用: "For example, our MoA using only open-source LLMs is the leader of AlpacaEval 2.0 by a substantial gap, achieving a score of 65.1% compared to 57.5% by GPT-4 Omni."
  - 使い道: 巨大な単一文脈をOpusで維持し続ける代わりに、複数の安価なSonnet/Haikuサブエージェントに短い独立文脈で並列検討させ、要約結果のみを統合するワークフローに応用できる。

- **anthropic-multiagent-token-multiplier**(high): Anthropicの実測データでは、通常のチャット対話と比較して単一エージェントは約4倍、マルチエージェントシステムは約15倍のトークンを消費するため、無秩序なサブエージェント展開は急激なトークン消費を招く。
  - 出典: [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
  - 引用: "There is a downside: in practice, these architectures burn through tokens fast. In our data, agents typically use about 4× more tokens than chat interactions, and multi-agent systems use about 15× more tokens than chats."
  - 使い道: CLAUDE.mdやスキル定義に「単純な調査ではサブエージェントを乱立させない」「タスク規模に応じて並列数を制限する」というeffort-scalingルールを明記して15倍のトークン膨張を抑止できる。

- **anthropic-multiagent-opus-sonnet**(high): リードエージェントにClaude Opus 4、サブエージェントにClaude Sonnet 4を組み合わせたマルチエージェント構成は、単一のOpus 4エージェントを社内リサーチ評価で90.2%上回り、探索の並列化と文脈圧縮を両立した。
  - 出典: [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
  - 引用: "We found that a multi-agent system with Claude Opus 4 as the lead agent and Claude Sonnet 4 subagents outperformed single-agent Claude Opus 4 by 90.2% on our internal research eval."
  - 使い道: 親セッションに高能力モデルを使う場合でも、サブエージェントはSonnetやHaikuに固定して並列探索と要約圧縮を担当させることで、サブエージェント側の単価と親のcache read量を同時に削減できる。

- **claudecode-model-selection-cost**(high): 大半のコーディング作業はOpusより安価なSonnetで十分処理できるため、通常作業はSonnetを使い複雑な設計判断や多段階推論にのみOpusを限定するとともに、単純なサブエージェントにはHaikuを指定することで費用を抑えられる。
  - 出典: [Manage costs effectively](https://code.claude.com/docs/en/costs)
  - 引用: "Sonnet handles most coding tasks well and costs less than Opus. Reserve Opus for complex architectural decisions or multi-step reasoning. Use /model to switch models mid-session, or set a default in /config."
  - 使い道: デフォルトモデルをSonnetに設定し、親をOpusに切り替えた際にサブエージェントまでOpusを継承して高コスト化しないよう、各サブエージェント設定にmodel: haikuまたはsonnetを明示する。

- **claudecode-explore-haiku-override**(high): Claude Codeの組み込み探索サブエージェントであるExploreは同名のカスタム定義で上書きでき、model: haikuを指定することでコードベース検索やファイル調査をより低コストなモデルで実行できる。
  - 出典: [Create custom subagents](https://code.claude.com/docs/en/sub-agents)
  - 引用: "A user or project subagent named Explore overrides the built-in and keeps its own model field, so define one with model: haiku to run exploration on a lower-cost model."
  - 使い道: ~/.claude/agents/Explore.mdにmodel: haikuを定義するか環境変数CLAUDE_CODE_SUBAGENT_MODEL=haikuを設定し、高頻度で走るコード探索サブエージェントのトークン単価を引き下げる。

- **anthropic-advisor-executor-tool**(high): 高速・低コストなExecutorモデルと、生成途中の重要局面で戦略的ガイダンスを提供する高知能なAdvisorモデルを組み合わせることで、実作業の大半を安価なモデルで回しつつ上位モデル並みの判断品質を得られる。
  - 出典: [Advisor tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool)
  - 引用: "Pair a faster executor model with a higher-intelligence advisor model that provides strategic guidance mid-generation."
  - 使い道: 反復的なファイル読込・編集・ツール実行ループのcache read/write単価を安価なExecutor（Sonnet/Haiku）に抑え、方針決定やエラー打開時のみAdvisor（Opus）を呼ぶ分担で総コストを削減できる。

- **claudecode-advisor-command**(high): Claude Codeの/advisorコマンド（または--advisorフラグ・advisorModel設定）により、メインの実行モデルとは別にタスク中の重要な瞬間だけ助言を仰ぐセカンダリモデル（Opusなど）を有効化できる。
  - 出典: [Commands reference](https://code.claude.com/docs/en/commands)
  - 引用: "Enable or disable the advisor tool, which consults a second model for guidance at key moments during a task. Accepts fable, opus, sonnet, or a full model ID."
  - 使い道: メインモデルを/model sonnetに設定した上で/advisor opus（またはsettings.jsonのadvisorModel）を有効化し、全ターンの長い文脈をOpus単価で支払うことなく要所の設計・軌道修正だけOpusに委ねられる。

- **aider-architect-editor**(high): コーディング問題の解決方針を記述するArchitectモデルと、その方針から既存ファイルへの具体的な編集差分を生成するEditorモデルに役割を分離することで、推論能力と編集効率を最適化できる。
  - 出典: [Separating code reasoning and editing](https://aider.chat/2024/09/26/architect.html)
  - 引用: "An Architect model is asked to describe how to solve the coding problem. An Editor model is given the Architect's solution and asked to produce specific code editing instructions to apply those changes to existing source files."
  - 使い道: Claude Codeで設計・修正計画の策定のみ上位モデルで行い、実際のコード編集やビルド確認の反復ループは短い文脈を持つSonnet/Haikuサブエージェントに委任する二段階運用として活用できる。

## GitHub の issue・実装例

- **issue110535**(high): プラグインや hook からは、会話が使う prompt cache の TTL(5 分か 1 時間か)を知る手段がない。放置後の最初の呼び出しは文脈全体を書き直す。
  - 出典: [Let plugins read the session's prompt cache lifetime](https://github.com/anthropics/claude-code/issues/110535)
  - 引用: "A plugin that acts on an idle session has to act before the cache lapses: the first request after that writes the whole context to the cache again."
  - 使い道: ttl_guard は TTL を会話ログの cache_creation から推定する。

- **issue94177**(high): 別の利用者の 30 会話の分析でも、cache write の 68% が TTL 切れ・microcompact・resume の 36 回に集中していた。
  - 出典: [Prompt-cache forensics from 30 real sessions](https://github.com/anthropics/claude-code/issues/94177)
  - 引用: "68% of all cache-write tokens (14.8M of 21.7M) come from 36 events"
  - 使い道: cache write の原因の分類(report)と ttl_guard の根拠。

- **issue108511**(high): TTL 内でも、前の呼び出しに追記しただけの依頼が cache を外し、会話全体を書き直すことがある(Claude Code 側の問題)。
  - 出典: [Prompt cache misses mid-session within TTL](https://github.com/anthropics/claude-code/issues/108511)
  - 引用: "93 misses in ~8.5k main-thread requests (~1.1%), not clustered by time or session."
  - 使い道: report の「TTL 内の書き直し」として見えるようにした。利用者側では防げない。

- **issue99360**(high): サブエージェントの cache write は 5 分 TTL で、主会話は 1 時間 TTL。
  - 出典: [Subagents use the 5-minute prompt cache while the main session uses 1-hour](https://github.com/anthropics/claude-code/issues/99360)
  - 引用: "Every subagent cache write was `ephemeral_5m_input_tokens` (19.65M, 0 in the 1-hour class)."
  - 使い道: cache 切れの判定で、5 分 TTL の書き込みだけの呼び出しは 300 秒で切れるとみなす。

- **sparkjoy**(high): sparkjoy プラグインは、55 分放置した会話を 1 時間 TTL が切れる前に compact するかを判定する。
  - 出典: [max-sixty/sparkjoy](https://github.com/max-sixty/sparkjoy)
  - 引用: "After 55 minutes idle, it asks again before the one-hour prompt cache lapses."
  - 使い道: 比較用シナリオ「55 分放置で compact」の元。

## 作業者(Claude)が出典を読んで加えたもの

- **ttl1h_price**(high): 1 時間 TTL の cache write は、入力トークン単価の 2 倍。
  - 出典: [Prompt caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
  - 引用: "Cache write tokens with a 1-hour TTL are 2 times the base input tokens price."
  - 使い道: transcripts.py の WEIGHTS(cache_write 2.0)の根拠。cache read 0.1 倍との比は 20 倍。
