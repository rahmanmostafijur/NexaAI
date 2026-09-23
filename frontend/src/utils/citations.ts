/** Matches citation markers such as [S1], [S12], [DB1]. */
export const CITATION_RE = /\[((?:S|DB)\d+)\]/g;

export function stripCitations(content: string): string {
  return content
    .replace(CITATION_RE, '')
    .replace(/[ \t]+([.,;:!?।])/g, '$1')
    .replace(/[ \t]{2,}/g, ' ')
    .trim();
}

export function sourceAnchorId(messageId: string, sourceId: string): string {
  return `src-${messageId}-${sourceId}`.replace(/[^A-Za-z0-9_-]/g, '_');
}
