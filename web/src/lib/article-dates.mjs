const UPDATED_LINE = /^_更新[：:]\s*(\d{4}-\d{2}-\d{2})_[\t ]*\r?$/m;

function validDate(value) {
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

// Keep stable, filename-derived publication dates when an article is refreshed.
export function articleDates(raw, slug) {
  const date = slug.match(/^(\d{4}-\d{2}-\d{2})/)?.[1] ?? '';
  const candidate = raw.match(UPDATED_LINE)?.[1] ?? '';
  const updatedDate = candidate && validDate(candidate) && candidate >= date ? candidate : '';
  return { date, updatedDate, sortDate: updatedDate || date };
}

export function stripUpdatedLine(raw, slug) {
  return articleDates(raw, slug).updatedDate ? raw.replace(UPDATED_LINE, '') : raw;
}

export function compareArticleDates(a, b) {
  return b.sortDate.localeCompare(a.sortDate) || b.slug.localeCompare(a.slug);
}
