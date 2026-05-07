# Probable Press Article Automation Main

## Goal

Probable Press向けに、最新データから重複の少ないSEO記事を1〜2本作り、画像・表示確認・commit・draft PR作成まで完了する。

このMDは司令塔です。細かい文章テンプレに従うより、目的、禁止事項、完成条件を守りながら、記事ごとに自然な構成を選んでください。

## Sub-Agent Prompts

- `prompts/article-automation/research.md`
- `prompts/article-automation/writer.md`
- `prompts/article-automation/readability_check.md`

## Must

- `main` を最新化してから作業する
- `data/` の最新JSONを読む
- `articles/` の直近10本を確認し、テーマ・カテゴリ・タイトルの重複を避ける
- 直近7記事で同カテゴリが3本以上続かないようにする
- 生活者、企業、学校、自治体など、読者に近い影響を説明する
- 高校生でも読める文体にする
- 参照リンクはトップページではなく個別URLにする
- 本文内の説明図はPC用SVGとスマホ用SVGを作る
- 記事内の画像切り替えは `<picture>` を使う
- アイキャッチはSVGまたはPNGで作り、トップ記事カードとOG画像で使えるようにする
- スマホで横スクロールを出さない
- 個別記事ページでタイトルを重複表示しない
- 可能なら `web` でビルド確認する
- 変更ファイルだけをcommitする
- branchをpushし、draft PRを作る

## Must Not

- Polymarket/Metaculusを主役にしない
- 投資助言にしない
- 市場価格や予測市場の数字を将来の保証として扱わない
- 予測市場や株式市場と関係ない記事に、市場セクションを無理に入れない
- 固定テンプレの見出しを機械的に入れない
- 事件や事故を過度に煽らない
- 著作権のあるロゴ、写真、キャラクターを画像に使わない
- `web/dist/`、`web/node_modules/`、`web/.astro/`、`web/package-lock.json` などの検証生成物をcommitしない
- unrelatedな既存変更を巻き込まない

## Operating Notes

- 記事の保存先: `articles/YYYY-MM-DD-topic-slug.md`
- 画像の保存先: `web/public/images/articles/`
- 本文内SVG:
  - `YYYY-MM-DD-topic-slug.svg`
  - `YYYY-MM-DD-topic-slug-mobile.svg`
- アイキャッチ:
  - `YYYY-MM-DD-topic-slug-eyecatch.svg` または `YYYY-MM-DD-topic-slug-eyecatch.png`
- PNG画像生成は使ってよい。ただし、本文理解に必要な情報は本文またはSVG図解で補う
- 同じ日付の記事が複数ある場合も、トップの最新記事表示が不自然にならないか確認する

## Done

- 調査内容からテーマを選んだ理由を説明できる
- 記事が1〜2本追加されている
- PC用、スマホ用、アイキャッチ画像が追加されている
- `<picture>` が記事内に入っている
- 参考リンクが個別URLになっている
- 投資助言に見える表現がない
- スマホ横スクロールがない
- タイトル重複がない
- ビルド確認結果をPR本文に書いている
- draft PRが作成されている

## PR Body Should Include

- 追加した記事テーマ
- なぜそのテーマを選んだか
- 直近記事との重複回避
- 追加した画像
- 実行した検証
- 残る注意点

