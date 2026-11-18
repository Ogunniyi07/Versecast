// The running transcript of a session: every sentence heard, every verse put
// on screen, and when listening started and stopped. It stays in this browser
// (saved in localStorage so a reload doesn't lose a sermon) until downloaded.

import type { Ref } from "./detector";
import { displayLabel } from "./format";

export type Entry =
  | { t: number; kind: "speech"; text: string }
  | { t: number; kind: "verse"; label: string; text: string }
  | { t: number; kind: "start" | "stop" };

const STORE_KEY = "vb-transcript";

export function loadTranscript(): Entry[] {
  try {
    const saved = localStorage.getItem(STORE_KEY);
    return saved ? (JSON.parse(saved) as Entry[]) : [];
  } catch {
    return [];
  }
}

export function saveTranscript(entries: Entry[]) {
  try {
    if (entries.length) localStorage.setItem(STORE_KEY, JSON.stringify(entries));
    else localStorage.removeItem(STORE_KEY);
  } catch { /* storage full or blocked: the transcript still lives in the page */ }
}

export function verseEntry(ref: Ref): Entry {
  return { t: Date.now(), kind: "verse", label: ref.label, text: ref.verses.map(([, , text]) => text).join(" ") };
}

// Speech recognition gives bare words ("god so loved the world"). Each finished sentence is shown as one: capital first letter, full stop at the end, and some words always capitalized (God, Jesus, Christ, Holy Spirit, Bible, Amen, Hallelujah, Satan, Lord).
const ALWAYS_CAPITAL: [RegExp, string][] = [
  [/\bi('m|'ll|'ve|'d)?\b/g, "I$1"],
  [/\bgod('s)?\b/g, "God$1"],
  [/\bjesus\b/g, "Jesus"],
  [/\bchrist('s)?\b/g, "Christ$1"],
  [/\bholy spirit\b/gi, "Holy Spirit"],
  [/\bholy ghost\b/gi, "Holy Ghost"],
  [/\bbible\b/g, "Bible"],
  [/\bamen\b/g, "Amen"],
  [/\bhallelujah\b/g, "Hallelujah"],
  [/\bsatan\b/g, "Satan"],
  [/\blord('s)?\b/g, "Lord$1"],
];

// Sentences that start like a question: "is there anybody here", "who is like our God".
const QUESTION = new RegExp(
  "^(?:(?:who|what|where|when|which|whose|how)\\s+(?:is|are|was|were|do|does|did|can|could|will|would|should|shall|has|have|many|much|long)" +
  "|(?:is|are|was|were|do|does|did|can|could|will|would|should|shall|has|have|isn't|aren't|don't|doesn't|didn't|can't|won't)" +
  "\\s+(?:you|we|they|he|she|it|there|anybody|anyone|somebody|someone|everybody|everyone|god|jesus|this|that|i)" +
  "|why)\\b", "i");

export function punctuate(text: string): string {
  let t = text.trim().replace(/\s+/g, " ");
  if (!t) return t;
  for (const [re, to] of ALWAYS_CAPITAL) t = t.replace(re, to);
  t = t[0].toUpperCase() + t.slice(1);
  if (/[.!?…,;:"')]$/.test(t)) return t;
  return QUESTION.test(t) ? `${t}?` : `${t}.`;
}

const time = (t: number, seconds = true) =>
  new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", ...(seconds ? { second: "2-digit" } : {}) });

/** The transcript as a plain-text file: what was said, then the verses shown. */
export function transcriptText(entries: Entry[]): string {
  if (!entries.length) return "";
  const first = entries[0].t;
  const last = entries[entries.length - 1].t;
  const date = new Date(first).toLocaleDateString([], { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const lines = [
    "VerseCast transcript",
    date,
    `${time(first, false)} to ${time(last, false)}`,
    "",
    "Made by the browser's speech recognition, so expect some misheard words.",
    "",
    "",
  ];
  for (const e of entries) {
    if (e.kind === "speech") lines.push(`[${time(e.t)}] ${punctuate(e.text)}`);
    else if (e.kind === "verse") lines.push("", `[${time(e.t)}] >> ON SCREEN: ${displayLabel(e.label)}`, "");
    else lines.push("", `[${time(e.t)}] --- Listening ${e.kind === "start" ? "started" : "stopped"} ---`, "");
  }
  const verses = entries.filter((e): e is Extract<Entry, { kind: "verse" }> => e.kind === "verse");
  lines.push("", "", `VERSES SHOWN (${verses.length})`, "");
  if (!verses.length) lines.push("None.");
  for (const v of verses) lines.push(`${time(v.t, false)}  ${displayLabel(v.label)} (KJV)`, `  ${v.text}`, "");
  return lines.join("\n").replace(/\n{3,}/g, "\n\n") + "\n";
}

export function downloadTranscript(entries: Entry[]) {
  const d = new Date(entries[0]?.t ?? Date.now());
  const pad = (n: number) => String(n).padStart(2, "0");
  const name = `versecast-transcript-${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}.txt`;
  const url = URL.createObjectURL(new Blob([transcriptText(entries)], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
