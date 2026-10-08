import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

const slug = '2026-04-30-paypay-scam-digital-risk';
const home = await readFile(new URL('../dist/index.html', import.meta.url), 'utf8');
const article = await readFile(new URL(`../dist/articles/${slug}/index.html`, import.meta.url), 'utf8');

test('refreshed article is the first card with stable URL and both dates', () => {
  const first = home.match(/<a href="(\/articles\/[^\"]+)" class="article-card"/);
  assert.equal(first?.[1], `/articles/${slug}`);
  assert.match(home, /更新：2026-10-08 \/ 公開：2026-04-30/);
});
test('detail has one title, update date, useful description and no raw metadata marker', () => {
  assert.equal((article.match(/<h1\b/g) ?? []).length, 1);
  assert.match(article, /更新：2026-10-08 \/ 公開：2026-04-30/);
  assert.doesNotMatch(article, /_更新：|<em>更新：/);
  assert.match(article, /name="description" content="「未払い料金を払って/);
  assert.doesNotMatch(article, /正しいとは限らない。_</);
});
test('responsive diagram and eyecatch are wired to built assets', async () => {
  assert.match(article, /media="\(max-width: 640px\)"/);
  assert.match(article, new RegExp(`${slug}-mobile\\.svg`));
  assert.match(article, new RegExp(`property="og:image" content="https://news-prediction-matcher\\.pages\\.dev/images/articles/${slug}-eyecatch\\.svg`));
  for (const suffix of ['', '-mobile', '-eyecatch']) {
    const svg = await readFile(new URL(`../dist/images/articles/${slug}${suffix}.svg`, import.meta.url), 'utf8');
    assert.match(svg, /<svg/);
    assert.doesNotMatch(svg, /<script|https?:\/\/[^w]/);
  }
});
test('legacy article keeps its original date without an invented update', async () => {
  const legacy = await readFile(new URL('../dist/articles/2026-06-05-tax-food-consumption-cut-impact/index.html', import.meta.url), 'utf8');
  assert.match(legacy, /class="article-date"[^>]*>2026-06-05</);
  assert.doesNotMatch(legacy, /更新：2026-10-08/);
});
