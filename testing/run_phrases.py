"""Run every phrase in test_phrases.csv through the detector and grade it.

    python3 testing/run_phrases.py            # text mode: phrase -> detector
    .venv/bin/python testing/run_phrases.py --voice   # macOS `say` -> Whisper -> detector
                                                      # (needs the archived speech_to_text.py)

Writes testing/results_<mode>.csv (the sheet with Result + Notes filled in)
and prints a summary per category.

Grades:
  PASS     exactly what the sheet expects
  PICKER   the expected reference is on screen (shown last); other detected
           references are only offered in the operator's picker
  FAIL     wrong, missing, or a false alarm
  REVIEW   the sheet marks it ambiguous; a person should judge the behaviour
  MANUAL   needs a real speaker / room (delivery conditions)
"""
import argparse
import csv
import re
import subprocess
import sys
from collections import Counter, OrderedDict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from scripture_refs import KJV, Session  # noqa: E402

SHEET = HERE / "test_phrases.csv"
AUDIO = HERE / "audio"
CONTEXT = "John 3:16"  # the sheet: follow-ups are said after John 3:16

# Follow-up rows: what the sheet's description means after John 3:16.
# Rows where Julius has decided differently from the sheet.
OVERRIDES = {
    58: (["Genesis 1", "Genesis 2"], "Julius decided 'and' between chapters = separate chapters (picker)"),
}

CONTEXT_EXPECTED = {
    166: ["John 3:17"], 167: ["John 3:15"], 168: ["John 3:17"], 169: ["John 3:16-20"],
    170: ["John 3:10"], 171: ["John 4"], 172: ["John 3:1"], 173: ["John 3:16"],
    174: ["John 4:1"], 234: ["John 3:16"], 235: ["John 3:16"],
}


def canonical(kjv, ref):
    """'Psalms 23' for a whole chapter, 'Genesis 1-3' for whole chapters, else the label."""
    chapters = kjv.books[ref.book]
    whole = ref.verse_start == 1 and ref.verse_end == chapters[ref.chapter_end]
    if whole and len(chapters) > 1:
        if ref.chapter == ref.chapter_end:
            return f"{ref.book} {ref.chapter}"
        return f"{ref.book} {ref.chapter}-{ref.chapter_end}"
    return ref.label()


def parse_expected(kjv, row_id, text):
    """Returns (kind, list_of_alternatives). Each alternative is a list of refs."""
    if row_id in CONTEXT_EXPECTED:
        return "context", [CONTEXT_EXPECTED[row_id]]
    if text.startswith(("Error", "No reference")):
        return "none", [[]]
    if text.startswith("Ambiguous"):
        return "review", []
    if text == "Genesis 1 or prompt for chapter":
        return "refs", [["Genesis 1"], []]
    t = re.sub(r"\s*\((whole chapter|whole book|first part|end)\)", "", text)
    t = re.sub(r"\bPsalm\b", "Psalms", t)
    refs, book, chapter = [], None, None
    for part in re.split(r"\s*\+\s*|,\s*", t):
        onward = part.endswith(" onward")
        part = part.replace(" onward", "")
        m = re.match(r"^(?:(\d? ?[A-Z][A-Za-z ]+?) )?(\d+)(?::(\d+))?(?:-(\d+)(?::(\d+))?)?$", part)
        if not m:
            raise ValueError(f"row {row_id}: can't parse expected {text!r}")
        b, a, v, x, y = m.groups()
        if b:
            book = b
        if v is None and b is None and chapter is not None and not x:
            v, a = a, chapter  # "Psalm 119:9, 11" -> bare 11 is a verse
        chapter = int(a)
        if book not in kjv.books:
            raise ValueError(f"row {row_id}: unknown book {book!r}")
        if v is None:
            refs.append(f"{book} {a}" + (f"-{x}" if x else ""))
            if len(kjv.books[book]) == 1:
                refs[-1] = f"{book} 1"  # Jude 1 (whole book)
        elif onward:
            refs.append(f"{book} {a}:{v}-{kjv.books[book][int(a)]}")
        elif y:
            refs.append(f"{book} {a}:{v}-{x}:{y}")
        elif x:
            refs.append(f"{book} {a}:{v}-{x}")
        else:
            refs.append(f"{book} {a}:{v}")
    # "Jude 1" for a one-chapter book is how canonical() prints the whole book.
    return "refs", [refs]


def span(kjv, s):
    """'Psalms 23' / 'Genesis 1-3' / 'John 3:16-4:2' -> (book, ch, v1, ch2, v2)."""
    m = re.match(r"^(.+?) (\d+)(?::(\d+))?(?:-(\d+)(?::(\d+))?)?$", s)
    book, a, v, x, y = m.groups()
    chapters = kjv.books[book]
    a = int(a)
    if v is None:  # whole chapter(s)
        b = int(x) if x else a
        return (book, a, 1, b, chapters.get(b, 0))
    v = int(v)
    if y:
        return (book, a, v, int(x), int(y))
    return (book, a, v, a, int(x) if x else v)


def grade(kind, alternatives, got, kjv=None):
    if kind == "review":
        return "REVIEW"
    got = [span(kjv, g) for g in got]
    alternatives = [[span(kjv, e) for e in exp] for exp in alternatives]
    for exp in alternatives:
        if got == exp or (len(exp) > 1 and sorted(got) == sorted(exp)):
            return "PASS"
    for exp in alternatives:
        if len(exp) == 1 and got and got[-1] == exp[0]:
            return "PICKER"
    return "FAIL"


def speak(row_id, text):
    """Synthesize a phrase with macOS `say` (cached)."""
    AUDIO.mkdir(exist_ok=True)
    path = AUDIO / f"{row_id:03d}.wav"
    if not path.exists():
        spoken = text.replace("—", ",").replace("...", ",")
        for _attempt in range(3):  # macOS speech service occasionally hangs
            try:
                subprocess.run(["say", "-o", str(path), "--data-format=LEI16@16000", spoken],
                               check=True, timeout=30)
                break
            except subprocess.TimeoutExpired:
                path.unlink(missing_ok=True)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", action="store_true", help="speak each phrase and transcribe it")
    ap.add_argument("--model", default="base.en")
    ap.add_argument("--only", help="comma-separated row IDs")
    args = ap.parse_args()

    kjv = KJV()
    stt = None
    if args.voice:
        try:
            from speech_to_text import Transcriber
        except ImportError:
            sys.exit("--voice needs speech_to_text.py (the offline Whisper module), which is "
                     "archived outside this repo for now. Text mode works without it.")
        stt = Transcriber(args.model)

    only = {int(x) for x in args.only.split(",")} if args.only else None
    per_cat, out_rows = evaluate(kjv, stt, only)

    mode = f"voice_{args.model}" if args.voice else "text"
    out = HERE / f"results_{mode}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ID", "Say this", "Expected result", "Category", "Result", "Notes"])
        w.writeheader()
        w.writerows(out_rows)

    total = Counter()
    print(f"{'Category':48} PASS PICK FAIL REVW MANL")
    for cat, c in per_cat.items():
        total.update(c)
        print(f"{cat[:48]:48} {c['PASS']:4} {c['PICKER']:4} {c['FAIL']:4} {c['REVIEW']:4} {c['MANUAL']:4}")
    print(f"{'TOTAL':48} {total['PASS']:4} {total['PICKER']:4} {total['FAIL']:4} {total['REVIEW']:4} {total['MANUAL']:4}")
    print(f"wrote {out.relative_to(HERE.parent)}")


def evaluate(kjv, stt=None, only=None):
    """Grade every sheet row. Returns (per-category Counter, rows with Result/Notes)."""
    rows = list(csv.DictReader(open(SHEET, encoding="utf-8-sig")))
    per_cat = OrderedDict()
    out_rows = []
    for row in rows:
        row["ID"] = row.pop("\ufeffID", row.get("ID"))
        rid = int(row["ID"])
        if only and rid not in only:
            continue
        cat = row["Category"]
        per_cat.setdefault(cat, Counter())
        if cat.startswith("20."):
            row["Result"], row["Notes"] = "MANUAL", "Needs a real speaker / room. " + row["Notes"]
            per_cat[cat]["MANUAL"] += 1
            out_rows.append(row)
            continue
        kind, alternatives = parse_expected(kjv, rid, row["Expected result"])
        override_note = ""
        if rid in OVERRIDES:
            alternatives, override_note = [OVERRIDES[rid][0]], OVERRIDES[rid][1]
        heard = row["Say this"]
        if stt:
            heard = stt.transcribe_text(str(speak(rid, row["Say this"])))
        session = Session(kjv)
        if kind == "context":
            session.hear(CONTEXT)
        got = [canonical(kjv, r) for r in session.hear(heard)]
        result = grade(kind, alternatives, got, kjv)
        per_cat[cat][result] += 1
        note = f"got: {'; '.join(got) or '(nothing)'}"
        if stt:
            note = f"heard: {heard!r} | " + note
        if result in ("FAIL", "PICKER", "REVIEW"):
            note += f" | expected: {' or '.join('; '.join(a) or '(nothing)' for a in alternatives) or 'judge manually'}"
        if override_note:
            note += f" | {override_note}"
        row["Result"], row["Notes"] = result, note + (f" | sheet note: {row['Notes']}" if row["Notes"] else "")
        out_rows.append(row)
    return per_cat, out_rows


if __name__ == "__main__":
    main()
