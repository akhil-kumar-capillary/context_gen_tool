/**
 * Shared text utilities — truncation, HTML stripping, etc.
 */

/** Strip HTML tags from a string. */
export function stripHtml(text: string): string {
  return text.replace(/<[^>]+>/g, "");
}

/** Truncate plain text to a maximum length. */
export function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "...";
}

/** Strip HTML then truncate to a maximum length. */
export function truncateHtml(html: string, maxLen: number): string {
  const clean = stripHtml(html);
  if (clean.length <= maxLen) return clean;
  return clean.slice(0, maxLen) + "...";
}
