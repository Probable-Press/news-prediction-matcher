import assert from 'node:assert/strict';
import { test } from 'node:test';
import { articleDates, stripUpdatedLine, compareArticleDates } from '../src/lib/article-dates.mjs';

const slug = '2026-04-30-paypay-scam-digital-risk';
test('legacy article keeps its publication date', () => {
  assert.deepEqual(articleDates('# Title\n\nOld text', slug), { date: '2026-04-30', updatedDate: '', sortDate: '2026-04-30' });
});
test('a dedicated update marker changes sorting without changing publication date', () => {
  const raw = '# Title\n\n_更新：2026-10-08_\n\nContent';
  assert.deepEqual(articleDates(raw, slug), { date: '2026-04-30', updatedDate: '2026-10-08', sortDate: '2026-10-08' });
  assert.equal(stripUpdatedLine(raw, slug), '# Title\n\n\n\nContent');
});
test('invalid, earlier and incidental update dates are not accepted', () => {
  for (const marker of ['_更新：2026-02-30_', '_更新：2026-13-08_', '_更新：2025-10-08_', '本文の更新：2026-10-08', '_更新：2026-10-08_ extra']) {
    assert.equal(articleDates(marker, slug).updatedDate, '', marker);
    assert.equal(stripUpdatedLine(marker, slug), marker);
  }
});
test('ASCII colon and CRLF are supported', () => {
  assert.equal(articleDates('_更新: 2026-10-08_\r\n', slug).updatedDate, '2026-10-08');
});
test('refreshed articles appear first and equal-date ties remain stable', () => {
  const items = [
    { slug: '2026-06-05-z', ...articleDates('', '2026-06-05-z') },
    { slug, ...articleDates('_更新：2026-10-08_', slug) },
    { slug: '2026-06-05-a', ...articleDates('', '2026-06-05-a') },
  ].sort(compareArticleDates);
  assert.deepEqual(items.map(a => a.slug), [slug, '2026-06-05-z', '2026-06-05-a']);
});
