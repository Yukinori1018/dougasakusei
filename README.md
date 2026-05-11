# dougasakusei — 半自動 YouTube 動画生成パイプライン

中小企業オーナー向け「AI × 税務・補助金」ジャンルに最適化された、
半自動で長尺＋ショート動画を組み立てるパイプライン。
最終仕上げ（カット微調整・タイトル決定・公開判断）は人間が行う前提です。

> **ゴール**: 1 本あたり自動 20-35 分 + 録音 15-25 分 で「投稿直前」まで持っていく。

## 主な機能

| 工程 | 出力 |
| --- | --- |
| トピック選定 | `research/topic.json` |
| 一次ソースリサーチ | `research/sources.json`, `research/brief.json` |
| 構造化台本生成 + 口語化 | `script/script.{json,md}`, `script/teleprompter.html` |
| 事実検証 | `compliance/factcheck.json`, `compliance/citations.md` |
| 音声（AI + 自分の声プレースホルダ） | `audio/ai_segments/*`, `audio/user_segments/RECORD_ME.json` |
| B-roll 候補収集 | `visuals/broll/{candidates.json,gallery.html}` |
| サムネ 3 案 | `visuals/thumbnails/thumb_{A,B,C}.png` |
| 字幕 SRT（用語辞書適用済み） | `subtitles/ja.srt` |
| ローカル BGM 選曲 | `bgm/selection.json` |
| メタデータ（タイトル 10 案・概要・タグ・SEO） | `metadata/{metadata.json,description.md,tags.txt,seo_report.md}` |
| コンプラ最終レポート（AI 開示チェック含む） | `compliance/final_report.md` |
| タイムライン（OTIO / FCPXML / EDL） | `timeline/project.{otio,fcpxml,edl}` |
| プレビュー mp4 生成スクリプト | `render_preview.sh` |
| ショート候補 5 件 | `output/shorts/{candidates.json,PICK_ME.md}` |

## クイックスタート

### 1. インストール

```bash
# uv 推奨 (https://github.com/astral-sh/uv)
uv venv
uv pip install -e .
# 字幕の forced alignment を使う場合
uv pip install -e ".[audio]"
```

### 2. API キー設定

```bash
cp .env.example .env
# エディタで開いて最低限 ANTHROPIC_API_KEY を入れる
# 他キーは未設定でも `PIPELINE_MODE=mock` で動作確認可能
```

### 3. 1 本生成

```bash
uv run pipeline generate --topic "インボイス経過措置がもうすぐ終了。今やるべき5つの対策"
```

成果物は `projects/<日付>_<slug>/` 配下に揃います。

### 4. ショート候補を見る

```bash
uv run pipeline shorts --project 2026-05-11_invoice-keiakasochi-2026
```

### 5. コンプラレポート確認

```bash
uv run pipeline report --project 2026-05-11_invoice-keiakasochi-2026
```

### 6. 自分の声を録音 → 差し替え

1. ブラウザで `projects/<slug>/script/teleprompter.html` を開く
2. `audio/user_segments/seg_NNN_RECORD_ME.wav` と同名で録音 → `seg_NNN.wav` にリネーム
3. 必要に応じてプレビュー生成: `bash projects/<slug>/render_preview.sh`

### 7. NLE で開く

`projects/<slug>/timeline/project.otio`（または `.fcpxml`, `.edl`）を
DaVinci Resolve / Premiere Pro / Final Cut Pro で開いて微調整。

## API キー取得方法

| サービス | 用途 | 取得 URL |
| --- | --- | --- |
| Anthropic | 全 LLM 呼び出し（必須） | https://console.anthropic.com/ |
| ElevenLabs | AI 音声（推奨） | https://elevenlabs.io/ |
| OpenAI | AI 音声フォールバック | https://platform.openai.com/ |
| Gemini | AI 音声代替 | https://ai.google.dev/ |
| Pexels | B-roll 動画素材（主） | https://www.pexels.com/api/ |
| Pixabay | B-roll 動画素材（副） | https://pixabay.com/api/docs/ |
| fal.ai | Flux 画像生成（サムネ強化、任意） | https://fal.ai/ |
| YouTube Data API v3 | SEO 競合確認（任意） | https://console.cloud.google.com/ |

最低限 `ANTHROPIC_API_KEY` があれば全工程動きます（他は欠けても安全にフォールバック）。

## 設定のカスタマイズ

`config.toml` を編集:

- `[long_form].target_duration_sec` — 長尺の目標秒数
- `[shorts].candidates_per_long` — ショート抽出候補数
- `[voice].user_segment_strategy` — ユーザー録音箇所の方針
- `[models]` — 各ノードでどの LLM tier を使うか（`haiku` / `sonnet` / `opus`）

## コンプラチェック項目

`compliance/final_report.md` が以下を確認:

- **事実誤認 (hallucination)**: 出典 URL が一次ソース（nta.go.jp 等）か？
- **税理士法・金商法**: 個別の税務判断/断定的判断の提供がないか？
- **著作権**: 第三者素材の無断引用がないか？
- **Inauthentic Content**: 自分の声セグメントが合計 60 秒以上 / 全体の 10% 以上含まれているか？
- **AI 開示**: YouTube Studio で『合成・改変メディア』の AI 使用開示にチェックを入れたか？

ブロッキング項目があれば `blocking=true` でレポートされます。

## ディレクトリ構成

```
src/pipeline/
  cli.py, graph.py, schemas.py, settings.py
  nodes/{topic,research,script,factcheck,voice,visual,subtitle,bgm,metadata,compliance,timeline,shorts}.py
  utils/{logging,llm,paths,io}.py
projects/<日付>_<slug>/   # 動画ごとの全成果物
assets/
  bgm/library.json        # ローカル BGM ライブラリ
  fonts/                  # NotoSansJP 等
  dictionary/tax_terms.json  # 字幕後処理用辞書
  recording/template.html # 録音 SOP
config.toml               # チャンネル全体設定
.env.example              # API キー雛形
```

## 制約と注意事項

- **税理士法**: 本パイプラインの出力は一般情報提供であり、個別の税務助言ではありません。投稿前に税理士監修を推奨。
- **金商法**: 投資商品の断定的判断の提供はコンプラチェッカーがブロックしますが、最終判断は人間が行ってください。
- **YouTube Inauthentic Content ポリシー (2025-07-15 改定)**: 自分の声・体験談を必ず含める運用が前提です。
- **BGM ライセンス**: `assets/bgm/library.json` の `license` 欄を必ず購入実体に合わせて更新してください。

## ライセンス

社内利用想定。コードの再配布はオーナーに確認してください。
