/**
 * Whether Kalshi's side label says anything the leg's title does not. Seen
 * live 2026-09-30: "Philadelphia wins (Philadelphia)" and "Atlanta wins the
 * game by over 1.5 points (Atlanta wins by over 1.5 points)" on every leg of
 * every game-script card. The label stays whenever it carries a word the
 * title lacks, so a bare "Total goals" title keeps its "Over 4.5".
 *
 * Pinned by `tests/test_side_label_is_not_repeated.py`.
 */
function wordsOf(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^\p{L}\p{N}+.]+/u)
    .map((w) => w.replace(/\.+$/, ""))
    .filter(Boolean);
}

export function sideLabelAddsWords(title: string, label: string): boolean {
  const inTitle = new Set(wordsOf(title));
  return wordsOf(label).some((w) => !inTitle.has(w));
}
