const BENGALI_RE = /[ঀ-৿]/;

export type Script = 'bengali' | 'latin';

/** Returns "bengali" when the text contains any Bengali-script character (U+0980–U+09FF). */
export function detectScript(text: string): Script {
  return BENGALI_RE.test(text) ? 'bengali' : 'latin';
}

/** `lang` attribute for rendered text so the Bengali font stack is applied. */
export function langFor(text: string): 'bn' | undefined {
  return detectScript(text) === 'bengali' ? 'bn' : undefined;
}
