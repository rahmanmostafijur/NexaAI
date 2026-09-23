import type { Nodes, Parent, PhrasingContent, Root, Text } from 'mdast';

const MARKER_RE = /\[((?:S|DB)\d+)\]/g;

/** Tag name used for citation elements in the rendered tree. */
export const CITATION_TAG = 'cite';

function splitText(node: Text): PhrasingContent[] {
  const parts: PhrasingContent[] = [];
  let last = 0;
  for (const match of node.value.matchAll(MARKER_RE)) {
    const index = match.index;
    const id = match[1];
    if (id === undefined) continue;
    if (index > last) parts.push({ type: 'text', value: node.value.slice(last, index) });
    // An `emphasis` node re-targeted via hName renders as <cite data-source-id="S1">.
    parts.push({
      type: 'emphasis',
      children: [{ type: 'text', value: id }],
      data: { hName: CITATION_TAG, hProperties: { dataSourceId: id } },
    });
    last = index + match[0].length;
  }
  if (parts.length === 0) return [node];
  if (last < node.value.length) parts.push({ type: 'text', value: node.value.slice(last) });
  return parts;
}

function isParent(node: Nodes): node is Nodes & Parent {
  return 'children' in node && Array.isArray(node.children);
}

function transform(node: Nodes): void {
  if (!isParent(node)) return;
  const next: Nodes[] = [];
  for (const child of node.children as Nodes[]) {
    if (child.type === 'text') next.push(...splitText(child));
    else {
      transform(child);
      next.push(child);
    }
  }
  (node as Parent).children = next as Parent['children'];
}

/** Remark plugin turning `[S1]` / `[DB1]` markers in text into citation elements. */
export function remarkCitations() {
  return (tree: Root) => transform(tree);
}
