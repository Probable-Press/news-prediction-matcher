# Probable Press Article Automation Main

## 目的

Probable Press向けに、最新ニュースと予測関連データを参考にしながら、重複の少ないSEO記事を1〜2本作成する。

このMDは全体の司令塔です。調査、構成・執筆、読みやすさ確認を分けて実行し、最後にcommitとPR作成まで進めます。

## 参照するサブMD

- `prompts/article-automation/research.md`
- `prompts/article-automation/writer.md`
- `prompts/article-automation/readability_check.md`

## 実行順

1. `main` を最新化する
2. `research.md` に従って `data/` の最新JSONと必要なニュースソースを読む
3. `articles/` の直近10本を確認し、テーマ・カテゴリ・タイトルの重複を避ける
4. 直近7記事で同カテゴリが3本以上続かないテーマを選ぶ
5. `writer.md` に従ってSEO向け記事を1〜2本作成する
6. PC用SVGとスマホ用SVGを `web/public/images/articles/` に保存する
7. 最新記事のアイキャッチSVGも必要に応じて作成し、同じディレクトリに保存する
8. 記事内に `<picture>` でPC/スマホ切り替えを入れる
9. `readability_check.md` に従って文章、表示、リンク、投資助言リスクを確認する
10. 可能なら `web` でビルド確認を行う
11. 変更ファイルだけをcommitし、branchをpushしてdraft PRを作る

## 絶対ルール

- Polymarket/Metaculusは主役にしない
- 投資助言は禁止
- 参照リンクはトップページではなく個別URLにする
- 高校生でも読める文体にする
- PNGではなくSVG図解を使う
- PC用SVGとスマホ用SVGを作る
- 記事内は `<picture>` で切り替える
- タイトル重複を出さない
- スマホで横スクロールを出さない
- 直近記事と同じテーマを安易に繰り返さない

## テーマ選定の優先順位

1. 生活者の行動や家計に関係するニュース
2. 企業や学校、自治体の実務に影響するニュース
3. すでに直近記事で多いカテゴリを避けられるニュース
4. 参照リンクが個別URLで用意できるニュース
5. 予測市場を補助情報として使えるが、主役にしなくても成立するニュース

## PR本文に入れること

- 追加した記事テーマ
- なぜそのテーマを選んだか
- 直近記事との重複回避
- 追加したSVG画像
- 実行した検証
- 投資助言ではないこと

