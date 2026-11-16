"""Detect explicitly spoken/transcribed Bible references (KJV) in text.

Handles forms like:
  "John 3:16", "John chapter three verse sixteen", "First Corinthians 13 verse 4",
  "Romans 8:28-30", "John 3:16 to 4:2", "Jude 3" (single-chapter books),
  "Psalm 119 verse 105", "Psalm one nineteen, one oh five", "the third chapter of
  John, the sixteenth verse", "Psalm 119 verses 9, 11 and 105", "The Lord's Prayer".
Only references that exist in the KJV database are returned.

Pipeline: normalize() rewrites the spoken text into a compact form
("john 3:16-18", "# " = the word "chapter" was said, "~" = two spoken numbers
that might be one number), KJV.find() resolves the ambiguous numbers against the
KJV, then matches book + numbers. Session adds memory for follow-ups
("next verse", "verse seventeen").
"""
import re
import sqlite3
from dataclasses import dataclass
from itertools import product
from pathlib import Path

DB_PATH = Path(__file__).with_name("kjv.sqlite")

# Books whose names are also everyday words. For these, number lists and long
# chapter ranges are treated as ordinary speech ("pick numbers 1 through 10").
COMMON_WORD_BOOKS = {"Numbers", "Mark", "Job", "Acts"}
MAX_CHAPTER_SPAN = 3  # longest chapter range/list accepted for COMMON_WORD_BOOKS

# Words Whisper has written for a spoken "verse". Only treated as "verse" when
# they sit between two numbers, e.g. "Genesis chapter 5 based 3".
VERSE_MISHEARINGS = ("best", "based", "vest", "burst", "birth", "verse's")

UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
ORDINALS = {"first": "1", "second": "2", "third": "3", "1st": "1", "2nd": "2", "3rd": "3"}
ORDINAL_WORDS = {
    "fourth": "four", "fifth": "five", "sixth": "six", "seventh": "seven", "eighth": "eight",
    "ninth": "nine", "tenth": "ten", "eleventh": "eleven", "twelfth": "twelve",
    "hundredth": "hundred",
}
_DIGIT_WORDS = ("zero", "oh", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")

_NUM_WORD = "(?:hundred|" + "|".join(list(UNITS) + list(TENS)) + ")"
_NUM_PHRASE = re.compile(rf"\b{_NUM_WORD}(?:[\s-]+(?:and[\s-]+)?{_NUM_WORD})*\b")

# Spoken alternates for book names (lowercase). Canonical KJV names and
# abbreviations from the source data are added automatically.
EXTRA_ALIASES = {
    # Whisper spellings of spoken names (confirmed by Julius)
    "jud": "Jude", "machu": "Matthew", "psalm of solomon": "Song of Solomon", "haggi": "Haggai",
    "psalm": "Psalms", "psalms": "Psalms", "ps": "Psalms", "psa": "Psalms",
    "song of songs": "Song of Solomon", "songs": "Song of Solomon",
    "canticles": "Song of Solomon", "revelations": "Revelation",
    "matt": "Matthew", "mt": "Matthew", "mk": "Mark", "lk": "Luke", "jn": "John",
    "phil": "Philippians", "philip": "Philippians", "heb": "Hebrews", "eph": "Ephesians",
    "rom": "Romans", "gen": "Genesis", "ex": "Exodus", "exod": "Exodus",
    "lev": "Leviticus", "num": "Numbers", "deut": "Deuteronomy", "josh": "Joshua",
    "judg": "Judges", "neh": "Nehemiah", "esth": "Esther", "prov": "Proverbs",
    "eccl": "Ecclesiastes", "isa": "Isaiah", "jer": "Jeremiah", "ezek": "Ezekiel",
    "dan": "Daniel", "hos": "Hosea", "obad": "Obadiah", "mic": "Micah",
    "nah": "Nahum", "hab": "Habakkuk", "zeph": "Zephaniah", "hag": "Haggai",
    "zech": "Zechariah", "mal": "Malachi", "phlm": "Philemon", "philem": "Philemon",
    "jas": "James", "pet": "1 Peter", "rev": "Revelation",
}
for _n, _base in (("1", "Samuel"), ("2", "Samuel"), ("1", "Kings"), ("2", "Kings"),
                  ("1", "Chronicles"), ("2", "Chronicles"), ("1", "Corinthians"),
                  ("2", "Corinthians"), ("1", "Thessalonians"), ("2", "Thessalonians"),
                  ("1", "Timothy"), ("2", "Timothy"), ("1", "Peter"), ("2", "Peter"),
                  ("1", "John"), ("2", "John"), ("3", "John")):
    EXTRA_ALIASES.setdefault(f"{_n} {_base[:3].lower()}", f"{_n} {_base}")
NUMBERED_BASES = ("john", "corinthians", "thessalonians", "timothy", "peter",
                  "kings", "samuel", "chronicles")

# Well-known passages people name without numbers. Replaced before parsing.
NAMED_PASSAGES = [
    (r"\bthe lord'?s prayer\b", "matthew 6:9-13"),
    (r"\bthe beatitudes\b", "matthew 5:3-12"),
    (r"\bthe love chapter\b", "1 corinthians 13"),
    (r"\bthe great commission\b", "matthew 28:18-20"),
    (r"\bthe ten commandments\b", "exodus 20:1-17"),
    (r"\bthe shepherd'?s? psalm\b", "psalms 23"),
    (r"\bthe faith chapter\b|\bthe hall of faith\b", "hebrews 11"),
    (r"\bthe (?:whole )?armou?r of god(?: passage)?\b", "ephesians 6:10-18"),
    (r"\bthe last verse (?:of|in) the bible\b", "revelation 22:21"),
    (r"\bthe first verse (?:of|in) the bible\b", "genesis 1:1"),
]

FILLERS = re.compile(r"\b(?:uh+|um+|erm|er|ah+|hmm+|eh)\b[,.]*")
# Words that mean "ignore the reference I just said".
CORRECTION = re.compile(r"\b(?:sorry|i mean|i meant|actually|correction|rather|no)\b")
RANGE_WORD = r"(?:to|through|thru|till|until|unto|up\s+to|down\s+to|dash|-)"


@dataclass(frozen=True)
class Reference:
    book: str
    chapter: int
    verse_start: int
    chapter_end: int
    verse_end: int
    spoken: str  # the text that matched, for logging

    def label(self) -> str:
        if self.chapter_end == self.chapter:
            if self.verse_end == self.verse_start:
                return f"{self.book} {self.chapter}:{self.verse_start}"
            return f"{self.book} {self.chapter}:{self.verse_start}-{self.verse_end}"
        return (f"{self.book} {self.chapter}:{self.verse_start}-"
                f"{self.chapter_end}:{self.verse_end}")

    def key(self):
        return (self.book, self.chapter, self.verse_start, self.chapter_end, self.verse_end)


def words_to_digits(text: str, joiner: str = " ") -> str:
    """Turn spoken numbers into digits. Adjacent numbers that don't form one
    number stay separate: 'three sixteen' -> '3 16', 'twenty three' -> '23'.
    `joiner` goes between such adjacent numbers ("~" marks them as possibly one
    number, e.g. "one nineteen" may be 119); a spoken "and" is kept."""
    def convert(match: re.Match) -> str:
        out = ""
        current = None  # number being built
        last = None     # kind of the previous word: unit, teen, tens, hundred
        saw_and = False
        for word in re.split(r"[\s-]+", match.group(0)):
            if not word:
                continue
            if word == "and":
                saw_and = True
                continue
            if word == "hundred":
                if current is not None and last == "unit" and current < 10:
                    current *= 100
                    last = "hundred"
                    saw_and = False
                    continue
                value, kind = 100, "hundred"   # bare "hundred"
            else:
                value = UNITS.get(word, TENS.get(word))
                kind = "tens" if word in TENS else ("unit" if value < 10 else "teen")
            continues = current is not None and (
                (last == "tens" and kind == "unit" and not saw_and)
                or (last == "hundred" and kind in ("unit", "teen", "tens"))
                or (last == "hundred_tens" and kind == "unit" and not saw_and)
            )
            if continues:
                current += value
                last = "hundred_tens" if (last == "hundred" and kind == "tens") else kind
            else:
                if current is not None:
                    out += f"{current}{' and ' if saw_and else joiner}"
                current = value
                last = kind
            saw_and = False
        return out + str(current)
    return _NUM_PHRASE.sub(convert, text)


def _join_digit_sequences(t: str) -> str:
    """'one oh five' -> '105', 'one-one-nine' -> '119' (digit-by-digit numbers)."""
    word = "|".join(_DIGIT_WORDS)
    digits = {w: str(i) for i, w in enumerate(_DIGIT_WORDS[1:], 0)}  # oh=0, one=1, ...
    digits["zero"] = "0"

    def join(m):
        parts = re.split(r"([\s-]+)", m.group(0))
        words, seps = parts[0::2], parts[1::2]
        has_zero = any(w in ("oh", "zero") for w in words[1:])
        hyphenated = len(words) >= 3 and all(s == "-" for s in seps)
        if words[0] in ("oh", "zero") or not (has_zero or hyphenated):
            return m.group(0)
        return "".join(digits[w] for w in words)
    return re.sub(rf"\b(?:{word})(?:[\s-]+(?:{word}))+\b", join, t)


def normalize(text: str) -> str:
    t = text.lower()
    t = t.replace("–", "-").replace("—", " - ").replace("…", "...").replace("’", "'")
    for pattern, ref in NAMED_PASSAGES:
        t = re.sub(pattern, f" {ref} ", t)
    # Whisper writes spoken "Ephesians six ten" as "Ephesians 6-10": straight
    # after a word (not after "3:"), a hyphen pair is chapter + verse.
    t = re.sub(r"\b([a-z]+)(\.?) (\d{1,3})-(\d{1,3})(?![\d:])",
               lambda m: m[0] if m[1] in ("verse", "verses", "chapter", "chapters", "vv", "v", "and", "to")
               else f"{m[1]}{m[2]} {m[3]}~{m[4]}", t)
    t = FILLERS.sub(" ", t)

    # --- numbers ---
    t = re.sub(r"\ba hundred\b", "one hundred", t)
    t = re.sub(r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[\s-]+(first|second|third)\b",
               lambda m: f"{m[1]} " + {"first": "one", "second": "two", "third": "three"}[m[2]], t)
    t = re.sub(r"\b(\w+?)teenth\b", r"\1teen", t)            # sixteenth -> sixteen
    t = re.sub(r"\b(twen|thir|for|fif|six|seven|eigh|nine)tieth\b", r"\1ty", t)
    t = re.sub(r"\b(" + "|".join(ORDINAL_WORDS) + r")\b", lambda m: ORDINAL_WORDS[m[1]], t)
    t = re.sub(r"\b(first|second|third|1st|2nd|3rd)\b", lambda m: ORDINALS[m[1]], t)
    t = _join_digit_sequences(t)
    t = words_to_digits(t, joiner="~")
    # Self-repair: "thirty... thirty-one" -> 31
    t = re.sub(r"(\d+)\s*\.{3,}\s*(\d+)",
               lambda m: m[2] if m[2].startswith(m[1][0]) and len(m[2]) >= len(m[1]) else f"{m[1]} {m[2]}", t)
    t = re.sub(r"\.{2,}", " ", t)
    t = re.sub(r",(?:\s*,)+", ",", t)

    # --- book name phrasing ---
    t = re.sub(r"\bpaul'?s\s+", "", t)
    # "First epistle of John" -> "1 john", but not "chapter 3 of John".
    t = re.sub(r"\b([123])\s+(?:(?:general\s+)?(?:epistle|letter|book)\s+)?(?:of|to)\s+"
               r"(?:the\s+)?(?:saint\s+|st\.?\s+)?(?=(?:" + "|".join(NUMBERED_BASES) + r")\b)",
               lambda m: m[0] if re.search(r"\b(?:chapters?|chap|verses?)\s*$", t[:m.start()])
               else f"{m[1]} ", t)
    t = re.sub(r"\bacts of the apostles\b", "acts", t)
    t = re.sub(r"\brevelation of (?:saint |st\.? )?(?:john|jesus christ)\b", "revelation", t)
    t = re.sub(r"\b(psalms?)\s+(?:of david|number)\b", r"\1", t)
    t = re.sub(r"\bthe\s+(\d+)(?:st|nd|rd|th)?\s+psalms?\b", r"psalms \1", t)   # "the 23rd psalm"

    # --- chapter / verse words ---
    t = re.sub(r"\b(chapters?|chap\.?)\b", " # ", t)     # "#" = the word "chapter" was said
    t = re.sub(r"\b(?:verses?|colon|vs|col)\b\.?", " : ", t)
    t = re.sub(r"\bthe\s+(\d+)(?:st|nd|rd|th)?\s+([#:])", r"\2 \1", t)  # "the 3 chapter" -> "# 3"
    t = re.sub(rf"(\d)\s*,?\s+(?:{'|'.join(VERSE_MISHEARINGS)}|dot|point)\s+(?=\d)", r"\1 : ", t)
    t = re.sub(r"(\d)\.(?=\d)", r"\1:", t)                # "3.16"
    t = re.sub(r":(?:\s*,?\s*:)+", ":", t)                 # "verse... verse 1"
    t = re.sub(r"#(?:\s*,?\s*#)+", "#", t)

    # --- open-ended and range phrasing ---
    t = re.sub(rf"(\d+)\s*,?\s*(?:from\s+)?the\s+beginning\s+{RANGE_WORD}\s*:?\s*(\d+)", r"\1:1-\2", t)
    t = re.sub(r"(\d+)\s*,?\s*(?:starting\s+)?from\s*:\s*(\d+)"
               r"(?!\s*(?:-|&|:|~|\d|to\b|through|thru|till|until|unto|down|up|and\b))",
               r"\1:\2 to the end", t)                    # "Philippians 4, from verse 6"
    # "chapter 1 and verse 2", "chapter 3, from verse 16" (not after a verse)
    t = re.sub(r"(?<![\d:])(?<!:\s)(\d+)\s*,?\s*(?:and|from|starting\s+(?:at|from))?\s*:", r"\1:", t)
    t = re.sub(r"(\d+)\s+(?:and\s+)?(?:the\s+)?following(?:\s+verses?)?\b", r"\1 to the end", t)
    t = re.sub(r"(\d+)\s+(?:and\s+)?onwards?\b", r"\1 to the end", t)
    t = re.sub(rf"(\d+)\s*{RANGE_WORD}\s*#\s*(\d+)\s*:\s*(\d+)", r"\1-\2:\3", t)  # "16 to chapter 4 verse 2"
    t = re.sub(rf"(\d+)\s*{RANGE_WORD}\s*[#:]?\s*(\d+)", r"\1-\2", t)
    # "and" between numbers: a list for chapters ("Matthew 1 and 3" = two
    # chapters); for verses, neighbours merge ("John 3:16 and 17" = 16-17).
    t = re.sub(r"(\d+)\s*,?\s*and\s*(?=\d)", r"\1&", t)
    return t


class KJV:
    def __init__(self, db_path: Path = DB_PATH):
        self.con = sqlite3.connect(db_path)
        self.books = {}  # canonical name -> {chapter: verse_count}
        for name, chapter, verse in self.con.execute(
            "SELECT book, chapter, MAX(verse) FROM verses GROUP BY book, chapter"
        ):
            self.books.setdefault(name, {})[chapter] = verse
        self.aliases = {}
        for name in self.books:
            self.aliases[name.lower()] = name
        for alias, name in EXTRA_ALIASES.items():
            if name in self.books:
                self.aliases[alias] = name
        # Longest first so "1 john" wins over "john".
        al = "|".join(re.escape(a) for a in sorted(self.aliases, key=len, reverse=True))
        single = "|".join(re.escape(a) for a in sorted(self.aliases, key=len, reverse=True)
                          if len(self.books[self.aliases[a]]) == 1)
        book = rf"(?<![a-z])({al})(?![a-z])"
        self._book_re = re.compile(
            book + r"\.?(?:\s*,?\s*(#\s*)|\s*)(\d{1,3})(?:(\s*:\s*|\s*,\s*|\s+)(\d{1,3})"
            r"(?:\s*-\s*(?:(\d{1,3})\s*:\s*)?(\d{1,3}))?)?"
        )
        # Alias-aware rewrites, applied in order before matching.
        self._rewrites = [
            # "From Matthew 5 to Matthew 7" -> "matthew 5-7"
            (re.compile(book + r"\s*#?\s*(\d{1,3})\s*(?:-|to|through|thru|till|until)\s+"
                        r"(?:the\s+book\s+of\s+)?\1(?![a-z])\s*#?\s*(\d{1,3})(?!\s*[:\d])"), r"\1 \2-\3"),
            # "the 16th verse of the 3rd chapter of John" -> "john 3:16"
            (re.compile(r":\s*(\d{1,3}(?:-\d{1,3})?)\s+of\s+(?:the\s+)?#\s*(\d{1,3})\s+of\s+"
                        r"(?:the\s+book\s+of\s+)?" + book), r"\3 \2:\1"),
            # "chapter 3 of John" -> "john # 3"
            (re.compile(r"#\s*(\d{1,3})\s+of\s+(?:the\s+book\s+of\s+)?" + book), r"\2 # \1"),
            # "verse 16 of John chapter 3", "verse 1 to verse 5 of Psalm 1"
            (re.compile(r":\s*(\d{1,3}(?:-\d{1,3})?)\s+of\s+(?:the\s+book\s+of\s+)?" + book
                        + r"\s*#?\s*(\d{1,3})(?!\s*[:\d])"), r"\2 \3:\1"),
            # "Jude verse 3" -> "jude 1:3" (one-chapter books)
            (re.compile(rf"(?<![a-z])({single})(?![a-z])\s*:\s*(?=\d)"), r"\1 1:"),
            # "Psalm 23 - actually just verse 4" -> "psalms 23:4"
            (re.compile(book + r"\s*#?\s*(\d{1,3})\s*[-,;.]?\s*(?:actually|i mean|sorry|rather|no)\s*,?\s+"
                        r"(?:just\s+|only\s+)*:\s*(\d{1,3})"), r"\1 \2:\3"),
            # tidy "john # 3, : 16" -> "john # 3: 16"
            (re.compile(r"(?<![\d:])(?<!:\s)(\d+)\s*,?\s*:"), r"\1:"),
        ]
        self._last_verse = re.compile(r"(?:the\s+)?last\s*:\s*(?:of|in)\s+(?:the\s+book\s+of\s+)?"
                                      + book + r"\s*#?\s*(\d{1,3})(?!\s*[:\d])")
        self._whole_book = re.compile(rf"\W*(?:the\s+(?:book|epistle|letter)\s+of\s+)?({single})\W*")
        self._bare_numbered = re.compile(r"(?<!\d)(?<!\d )\b(" + "|".join(NUMBERED_BASES[1:]) + r")\b(?=\s*#?\s*\d)")
        self._book_at_end = re.compile(book + r"\.?\s*#?\s*$")
        self._number_run = re.compile(r"(?<![\d~:])(\d+(?:~\d+)+|\d{2,4})(?![\d~:])")
        # A list continuing a verse reference: ", 17", "&105", ", then verse 8", ", 6 23".
        self._cont = re.compile(
            r"\s*(?:,|&|;|\.(?=\s*(?:and\s+)?(?:then|also)\b))\s*(?:and\s+)?(?:(?:then|also)\s+)?"
            r"(?:(:)\s*(\d{1,3})(?:\s*-\s*(\d{1,3}))?"
            r"|(\d{1,3})(?:\s*:\s*|\s+)(\d{1,3})(?:\s*-\s*(\d{1,3}))?"
            r"|(\d{1,3})(?:\s*-\s*(\d{1,3}))?)"
            rf"(?![\d:~])(?!\s+(?:{al})(?![a-z]))"
        )
        # After a loose "Numbers 3, 16": another number means a list ("numbers 1, 2, 3").
        self._more_numbers = re.compile(r"[\s,]*\d")
        self._chapter_range = re.compile(r"\s*-\s*(\d{1,3})")
        self._chapter_list = re.compile(r"(?:\s*&\s*\d{1,3})+")
        self._to_end = re.compile(
            r"\s*,?\s*(?:to|till|til|until|unto|through|thru|-)\s+(?:the\s+)?end\b(?:\s+of\s+the\s+#)?"
        )
        # After a chapter-only match ("Matthew 2"): a counting word means
        # ordinary speech, not a chapter.
        self._not_a_chapter = re.compile(
            r"\s*(?:-|%|'|o'clock|(?:am|pm|st|nd|rd|th)\b)|\s+(?:"
            r"people|persons?|men|women|children|kids|guys|members|souls|"
            r"weeks?|days?|months?|years?|hours?|minutes?|seconds?|"
            r"times|o'clock|percent|dollars?|pounds?|cents?|naira|"
            r"more|or|others|out|in a row|things|ways|points|steps|keys|books"
            r")\b"
        )

    # ------------------------------------------------------------------ public
    def find(self, text: str) -> list:
        """References in `text`, in order of most recent mention (show the last)."""
        t = self._prepare(text)
        whole = self._whole_book.fullmatch(t)
        if whole:  # "Jude" on its own: the whole one-chapter book
            book = self.aliases[whole[1]]
            return [Reference(book, 1, 1, 1, self.books[book][1], whole[1])]
        bare = self._bare_numbered.search(t)
        if bare:
            # "Corinthians 13:4" with no number: offer both, 1 Corinthians shown.
            second = [r for r, _, _ in self._core(self._bare_numbered.sub(r"2 \1", t))]
            first = [r for r, _, _ in self._core(self._bare_numbered.sub(r"1 \1", t))]
            keys = {r.key() for r in first}
            return [r for r in second if r.key() not in keys] + first
        return [r for r, _, _ in self._core(t)]

    def find_detailed(self, text: str) -> list:
        """Like find(), but returns (Reference, words_after) pairs. `words_after`
        is how many words were spoken after the reference: 0 means it is still
        at the end of what was heard, so more ("...verse 16") may be coming."""
        t = self._prepare(text)
        if self._whole_book.fullmatch(t) or self._bare_numbered.search(t):
            return [(r, 0) for r in self.find(text)]
        return [(r, len(re.findall(r"[a-z0-9]+", t[e:]))) for r, _, e in self._core(t)]

    def is_whole_chapter(self, ref: Reference) -> bool:
        chapters = self.books[ref.book]
        return len(chapters) > 1 and ref.verse_start == 1 and ref.verse_end == chapters[ref.chapter_end]

    def verse_texts(self, ref: Reference) -> list:
        rows = self.con.execute(
            "SELECT chapter, verse, text FROM verses WHERE book = ? AND "
            "(chapter > ? OR (chapter = ? AND verse >= ?)) AND "
            "(chapter < ? OR (chapter = ? AND verse <= ?)) ORDER BY chapter, verse",
            (ref.book, ref.chapter, ref.chapter, ref.verse_start,
             ref.chapter_end, ref.chapter_end, ref.verse_end),
        ).fetchall()
        return rows

    def valid(self, ref: Reference) -> bool:
        chapters = self.books.get(ref.book)
        return bool(chapters) and self._valid(chapters, ref.chapter, ref.verse_start,
                                              ref.chapter_end, ref.verse_end)

    # ---------------------------------------------------------------- internals
    def _prepare(self, text: str) -> str:
        t = normalize(text)
        t = self._last_verse.sub(self._last_verse_sub, t)
        for pattern, repl in self._rewrites:
            t = pattern.sub(repl, t)
        return self._resolve_number_runs(t, set(re.findall(r"\d+", text)))

    def _last_verse_sub(self, m):
        chapters = self.books[self.aliases[m[1]]]
        ch = int(m[2])
        return f"{m[1]} {ch}:{chapters[ch]}" if ch in chapters else m[0]

    def _resolve_number_runs(self, t: str, written_digits=frozenset()) -> str:
        """Decide what runs like "1~19" (spoken "one nineteen") or "828" mean by
        trying each grouping and keeping the one that makes a valid reference:
        "Psalm 1~19" -> 119, "John 1~19" -> 1 19, "Romans 828" -> 8 28.
        Plain numbers are only split if they were written as digits in the
        transcript (Whisper merging "eight twenty-eight"), never ones spoken
        as words ("Genesis fifty-one" stays 51 and is rejected)."""
        pos = 0
        while True:
            m = self._number_run.search(t, pos)
            if not m:
                return t
            run = m[1]
            tokens, default_join = (run.split("~"), False) if "~" in run else (list(run), True)
            best = None
            # A merged number ("Romans 828", "Amos 33") is only split straight
            # after a book name, and never for Psalms (100+ chapters).
            if default_join and run not in written_digits:
                pos = m.end()
                continue
            if default_join:
                before = self._book_at_end.search(t[:m.start()])
                book = self.aliases.get(before[1]) if before else None
                if not book or book == "Psalms":
                    pos = m.end()
                    continue
            if len(tokens) <= 6:
                ws, we = max(0, m.start() - 60), min(len(t), m.end() + 40)
                for joins in product((False, True), repeat=len(tokens) - 1):
                    groups, cur = [], tokens[0]
                    for tok, j in zip(tokens[1:], joins):
                        if j:
                            cur += tok
                        else:
                            groups.append(cur)
                            cur = tok
                    groups.append(cur)
                    if any(len(g) > 3 or g[0] == "0" for g in groups):
                        continue
                    cand = " ".join(groups)
                    cost = sum(j != default_join for j in joins)
                    window = (t[ws:m.start()] + cand + t[m.end():we]).replace("~", " ")
                    lo, hi = m.start() - ws, m.start() - ws + len(cand)
                    hits = self._core(window)
                    covered = len({i for _, s, e in hits for i in range(max(s, lo), min(e, hi))})
                    # Prefer the reading whose numbers all end up in a
                    # reference, then the one closest to what was written.
                    score = (round(covered / len(cand), 3), -cost)
                    if best is None or score > best[0]:
                        best = (score, cand)
            cand = best[1] if best else run.replace("~", " ")
            t = t[:m.start()] + cand + t[m.end():]
            pos = m.start() + len(cand)

    def _core(self, t: str) -> list:
        """Match book + numbers. Returns [(Reference, start, end)] in order of
        most recent mention; a repeat moves to the end."""
        found = []  # (ref, start, end, match_index)
        prev_end = None
        for idx, m in enumerate(self._book_re.finditer(t)):
            alias, said_chapter, a, sep, v1, ch2, v2 = m.groups()
            book = self.aliases[alias]
            chapters = self.books[book]
            if self._impossible_number_prefix(t, m.start(), alias):
                continue  # "Fourth John"
            if (sep is not None and ":" not in sep and book in COMMON_WORD_BOOKS
                    and self._more_numbers.match(t, m.end())):
                continue  # "write the numbers 1, 2, 3"
            if v1 is None:
                spans, end = self._chapter_spans(t, m.end(), int(a), chapters, said_chapter, book)
            else:
                spans, end = self._verse_spans(t, m, int(a), int(v1), ch2, v2, chapters)
            spans = [s for s in spans if self._valid(chapters, *s)]
            if not spans:
                continue
            # "John 3:16, sorry, John 4:24": the correction replaces the earlier one.
            if found and prev_end is not None and 0 <= m.start() - prev_end <= 40 \
                    and CORRECTION.search(t, prev_end, m.start()):
                last_idx = found[-1][3]
                found = [f for f in found if f[3] != last_idx]
            for span in spans:
                ref = Reference(book, *span, t[m.start():end].strip())
                found = [f for f in found if f[0].key() != ref.key()]
                found.append((ref, m.start(), end, idx))
            prev_end = end
        return [(r, s, e) for r, s, e, _ in found]

    def _impossible_number_prefix(self, t, start, alias) -> bool:
        """'4 john' after a word ("the fourth John"): no such book."""
        if alias not in NUMBERED_BASES:
            return False
        m = re.search(r"(?:^|[a-z])\s*\b([4-9])\s+$", t[:start])
        return bool(m)

    def _verse_spans(self, t, m, chapter, verse, ch2, v2, chapters):
        chapter_end = int(ch2) if ch2 else chapter
        verse_end = int(v2) if v2 else verse
        end = m.end()
        if not v2:
            te = self._to_end.match(t, end)
            if te:  # "Psalm 119 verse 1 to the end"
                verse_end = chapters.get(chapter, verse)
                end = te.end()
        items = [(chapter, verse, chapter_end, verse_end)]
        while True:  # ", 17", " and 105", ", then verse 8", ", 6 23"
            c = self._cont.match(t, end)
            if not c or self._not_a_chapter.match(t, c.end()):
                break
            kw, kv, kve, pc, pv, pve, bv, bve = c.groups()
            if pc:
                items.append((int(pc), int(pv), int(pc), int(pve or pv)))
            else:
                ch = items[-1][2]
                v_ = int(kv or bv)
                items.append((ch, v_, ch, int(kve or bve or v_)))
            end = c.end()
        merged = [items[0]]
        for it in items[1:]:  # neighbours merge: "5, 6 and 9" -> 5-6, 9
            last = merged[-1]
            if it[0] == last[2] == it[2] and it[1] == last[3] + 1:
                merged[-1] = (last[0], last[1], it[2], it[3])
            else:
                merged.append(it)
        return merged, end

    def _chapter_spans(self, t, pos, first, chapters, said_chapter, book):
        """A book + number with no verse: "Matthew 2", "Genesis 1 to 3",
        "Matthew 1 and 3". Returns ([(chapter, verse_start, chapter_end,
        verse_end)], end) or ([], pos) if it reads like ordinary counting."""
        rng = self._chapter_range.match(t, pos)
        lst = None if rng else self._chapter_list.match(t, pos)
        end = (rng or lst).end() if (rng or lst) else pos
        # Skip counting ("Acts 2 weeks ago") unless "chapter" was said.
        if not said_chapter and self._not_a_chapter.match(t, end):
            return [], pos
        listed = [first] + ([int(n) for n in re.findall(r"\d+", lst.group(0))] if lst else [])
        cap = MAX_CHAPTER_SPAN if book in COMMON_WORD_BOOKS else 150

        if len(chapters) == 1:
            if said_chapter and not (rng or lst):
                # "Jude chapter 1" = the whole book; "Obadiah chapter 2" doesn't exist.
                return ([(1, 1, 1, chapters[1])] if first == 1 else []), end
            last = int(rng.group(1)) if rng else listed[-1]
            return [(1, first, 1, last)], end              # "Jude 3", "Jude 3 and 4": verses

        if rng:                                            # "Genesis 1 to 3": one passage
            last = int(rng.group(1))
            if last - first + 1 > cap or last not in chapters:
                return [], pos                             # "numbers 1 through 10" is counting
            return [(first, 1, last, chapters[last])], end
        if len(listed) > cap:
            return [], pos
        return [(c, 1, c, chapters[c]) for c in listed if c in chapters], end

    @staticmethod
    def _valid(chapters, ch, v1, ch2, v2) -> bool:
        if ch not in chapters or ch2 not in chapters:
            return False
        if ch2 < ch or (ch2 == ch and v2 < v1):
            return False
        if v1 < 1 or v1 > chapters[ch]:
            return False
        if v2 < 1 or v2 > chapters[ch2]:
            return False
        return True


class Session:
    """Detection across a sermon: remembers the last reference shown so that
    follow-ups ("next verse", "verse seventeen", "read it again") work."""

    def __init__(self, kjv: KJV):
        self.kjv = kjv
        self.last = None  # last Reference put on screen

    def hear(self, text: str) -> list:
        refs = self.kjv.find(text)
        if not refs and self.last is not None:
            refs = self._follow_up(text)
        if refs:
            self.last = refs[-1]
        return refs

    def _follow_up(self, text: str) -> list:
        t = normalize(text).replace("~", " ")
        last = self.last
        book, chapters = last.book, self.kjv.books[last.book]

        def ref(ch, v1=None, v2=None):
            if v1 is None:  # whole chapter
                r = Reference(book, ch, 1, ch, chapters.get(ch, 0), text)
            else:
                r = Reference(book, ch, v1, ch, v2 if v2 is not None else v1, text)
            return [r] if self.kjv.valid(r) else []

        if re.search(r"\bnext\s*:", t):
            ch, v = last.chapter_end, last.verse_end + 1
            return ref(ch, v) if v <= chapters[ch] else ref(ch + 1, 1)
        if re.search(r"\b(?:previous|preceding)\s*:", t):
            ch, v = last.chapter, last.verse_start - 1
            return ref(ch, v) if v >= 1 else ref(ch - 1, chapters.get(ch - 1, 0))
        if re.search(r"\bnext\s*#", t):
            return ref(last.chapter_end + 1)
        if re.search(r"\b(?:previous|last)\s*#", t):
            return ref(last.chapter - 1)
        if re.search(r"\b(?:read|say|show)\s+(?:it|that)\s+again\b|\bagain\b|\brepeat\b", t):
            return [last]
        m = re.search(r"\bcontinue\s+(?:to|till|until|up to|through)\s*:\s*(\d+)", t)
        if m:
            return ref(last.chapter, last.verse_start, int(m[1]))
        m = re.search(r"#\s*(\d+)(?:\s*:\s*(\d+)(?:\s*-\s*(\d+))?)?", t)
        if m:  # "chapter four verse one": same book
            ch = int(m[1])
            return ref(ch) if not m[2] else ref(ch, int(m[2]), int(m[3] or m[2]))
        m = re.search(r":\s*(\d+)(?:\s*-\s*(\d+))?", t)
        if m:  # "verse seventeen", "same chapter, verse ten"
            return ref(last.chapter_end, int(m[1]), int(m[2] or m[1]))
        m = re.fullmatch(r"\W*(\d+)\s*[\s,:]\s*(\d+)\W*", t)
        if m:  # "three sixteen" on its own: same book
            return ref(int(m[1]), int(m[2]))
        return []
