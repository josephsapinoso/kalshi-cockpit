/**
 * Names in a card's `drop_if`, found so each can be a news-search link (#284).
 * Pure and dependency-free: `tests/test_game_script_card_face.py` runs it in
 * Node.
 */

/** Words that start a sentence or sit in a capitalised phrase without being a
 * person or a team; never made into a search link. */
const NOT_A_NAME = new Set([
  "A", "An", "The", "If", "Or", "And", "Any", "Drop", "Skip", "Should", "That",
  "This", "His", "Her", "Their", "He", "She", "It", "Is", "Are", "When", "Then",
  "News", "Out", "Ruled", "Both", "Either", "Neither", "Not", "No", "Yes",
  "Over", "Under",
]);

type DropIfPart = { text: string; name: string | null };

/**
 * `drop_if` split into plain text and names (#284). A name is a run of one to
 * three capitalised words that is not a sentence's first word on its own and
 * not an ordinary capitalised word; each name becomes a news-search link so
 * the check "has this changed?" is one tap. **Links only: nothing is looked
 * up, read or scored here**, and a phrase the heuristic misses simply stays
 * text. Pure, so it is safe to call during render.
 */
export function splitDropIf(text: string): DropIfPart[] {
  const parts: DropIfPart[] = [];
  const pattern = /[A-Z][A-Za-z.'’-]*(?:\s+[A-Z][A-Za-z.'’-]*){0,2}/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    const words = match[0].split(/\s+/).filter((w) => !NOT_A_NAME.has(w));
    const sentenceStart = start === 0 || /[.!?]\s+$/.test(text.slice(0, start));
    const found = words.length ? match[0].indexOf(words[0]) : 0;
    // A lone capitalised word that merely opens a sentence is not a name.
    if (words.length === 0 || (words.length === 1 && sentenceStart && found === 0))
      continue;
    const name = words.join(" ").replace(/[.'’-]+$/, "");
    const from = start + found;
    const to = start + match[0].length;
    if (from > last) parts.push({ text: text.slice(last, from), name: null });
    parts.push({ text: text.slice(from, to), name });
    last = to;
  }
  if (last < text.length) parts.push({ text: text.slice(last), name: null });
  return parts;
}
