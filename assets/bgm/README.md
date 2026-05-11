# ローカル BGM ライブラリ

このディレクトリにライセンス購入済みの BGM を配置し、`library.json` にメタ情報を登録してください。

## 推奨入手元
- DOVA-SYNDROME（フリー BGM、商用利用可、要規約確認）
- 甘茶の音楽工房
- Artlist / Epidemic Sound（個人サブスク購入 → mp3 で書き出して配置）
- Audiostock（買い切り、商用 OK）

## 登録ルール
1. ファイルを `assets/bgm/` に配置（mp3/wav）
2. `library.json` の `tracks` に追記:
   - `id`: 一意な英数字 ID
   - `file`: リポジトリルートからの相対パス
   - `title`: 表示用
   - `license`: ライセンス URL またはサブスク名+購入日
   - `duration_sec`: 尺
   - `tags`: 雰囲気タグ（LLM 選曲のヒント）

## タグ語彙の参考
- 雰囲気: `calm`, `uplifting`, `tense`, `focus`, `corporate`, `cinematic`
- 強度: `low-energy`, `mid-energy`, `high-energy`
- 用途: `intro`, `body`, `conclusion`, `explainer`, `documentary`

`.gitignore` で実ファイル（mp3/wav/flac）はリポジトリに含めない設定です。
