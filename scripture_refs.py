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
import math
import time
import re
import sqlite3
from array import array
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
    # Whisper spellings of spoken names
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

# Bible stories by name ("David and Goliath", "the story of Joseph"): shown
# from where the story starts. Specific episodes come before the person's
# story in general ("Daniel in the lions' den" before "the story of Daniel").
# Spellings speech recognition produces for the names are included.
SHADRACH = r"(?:shadrach|shadrack|shadrak|shedrach|shedrack|shedrak|sadrach)"
MESHACH = r"(?:meshach|meshack|meshak|mishach|mishak|mechash|meshac)"
ABEDNEGO = r"(?:abednego|abed[- ]nego|abednigo|abenego|abednago|abed nigo)"
STORY_EPISODES = [
    # Genesis
    (r"the creation story|the story of (?:the )?creation", "genesis 1"),
    (r"the garden of eden", "genesis 2"),
    (r"adam and eve|the fall of man", "genesis 3"),
    (r"cain and abel", "genesis 4:1-16"),
    (r"noah'?s ark|noah and the (?:ark|flood)|the great flood", "genesis 6"),
    (r"the tower of babel", "genesis 11:1-9"),
    (r"the call of abra(?:ha)?m", "genesis 12"),
    (r"sodom and gomorr?ah", "genesis 19"),
    (r"abraham and isaac|the sacrifice of isaac|abraham sacrific(?:ed|es|ing) isaac", "genesis 22:1-19"),
    (r"jacob and esau", "genesis 25:19-34"),
    (r"jacob'?s ladder", "genesis 28:10-22"),
    (r"jacob wrestl(?:ed|es|ing) with (?:the angel|god|a man)", "genesis 32:22-32"),
    (r"joseph and (?:his brothers|the coat of many colou?rs)|joseph'?s coat|coat of many colou?rs|joseph the dreamer", "genesis 37"),
    (r"joseph and potiphar'?s? wife|potiphar'?s wife", "genesis 39"),
    # Exodus to Ruth
    (r"baby moses|moses in the (?:basket|bulrushes)|the birth of moses", "exodus 2:1-10"),
    (r"the burning bush", "exodus 3"),
    (r"the (?:ten )?plagues of egypt|the ten plagues", "exodus 7"),
    (r"the passover story|the first passover", "exodus 12"),
    (r"(?:the )?(?:parting|crossing|dividing) of the red sea|cross(?:ed|ing) the red sea|(?:part|parted|parting|divided) the red sea", "exodus 14"),
    (r"manna from heaven", "exodus 16"),
    (r"the golden calf", "exodus 32"),
    (r"rahab and the spies", "joshua 2"),
    (r"the (?:walls|battle|fall) of jericho", "joshua 6"),
    (r"gideon'?s fleece|gideon and the fleece|gideon'?s army", "judges 6"),
    (r"samson and delilah", "judges 16"),
    (r"ruth and naomi", "ruth 1"),
    # Samuel, Kings
    (r"hannah'?s prayer", "1 samuel 1"),
    (r"the call(?:ing)? of samuel", "1 samuel 3"),
    (r"the anointing of david|david (?:was |is )?anointed", "1 samuel 16"),
    (r"david and goliath", "1 samuel 17"),
    (r"david and jonathan", "1 samuel 20"),
    (r"david and bathsheba", "2 samuel 11"),
    (r"solomon and the two (?:women|mothers|harlots)|solomon'?s (?:wisdom|judge?ment)|the wisdom of solomon", "1 kings 3:16-28"),
    (r"elijah and the widow(?: of zarephath)?", "1 kings 17:8-24"),
    (r"elijah (?:and the prophets of baal|on mount carmel)|the prophets of baal", "1 kings 18"),
    (r"chariots? of fire|elijah (?:was )?taken up", "2 kings 2:1-14"),
    (r"elisha and the shunamm?ite(?: woman)?", "2 kings 4:8-37"),
    (r"naaman the leper|naaman (?:was )?healed", "2 kings 5"),
    # Prophets
    (r"the valley of dry bones|the dry bones", "ezekiel 37:1-14"),
    (r"nebuchadnezzar'?s dream", "daniel 2"),
    (rf"{SHADRACH}|{MESHACH}|{ABEDNEGO}|the fiery furnace|the three hebrew (?:boys|men|children)", "daniel 3"),
    (r"the (?:hand)?writing on the wall|belshazzar'?s feast", "daniel 5"),
    (r"daniel in the lions'? den|daniel and the lions|the lions'? den|the lion'?s den", "daniel 6"),
    (r"jonah and the (?:whale|big fish|great fish|fish)", "jonah 1"),
    # Gospels
    (r"the christmas story|the nativity(?: story)?|the birth of (?:jesus|christ)", "luke 2:1-20"),
    (r"the three wise men|the wise men from the east|the magi", "matthew 2:1-12"),
    (r"the baptism of jesus|jesus'?s? baptism|jesus (?:was )?baptized", "matthew 3:13-17"),
    (r"the temptation of (?:jesus|christ)|jesus (?:was )?tempted", "matthew 4:1-11"),
    (r"the sermon on the mount", "matthew 5"),
    (r"(?:turn(?:ed|ing|s)? )?water into wine|the wedding (?:at|in) cana", "john 2:1-11"),
    (r"jesus and nicodemus|the story of nicodemus", "john 3:1-21"),
    (r"the woman at the well|the samaritan woman", "john 4:1-42"),
    (r"(?:the )?feeding of the (?:five thousand|5,?000)|five loaves and two fish(?:es)?|5 loaves and 2 fish(?:es)?", "john 6:1-14"),
    (r"(?:jesus|peter) walk(?:ed|s|ing)? on (?:the )?water|walking on water", "matthew 14:22-33"),
    (r"jesus calm(?:ed|s|ing)? the storm|the calming of the storm", "mark 4:35-41"),
    (r"the (?:parable of the )?good samaritan", "luke 10:25-37"),
    (r"the (?:parable of the )?prodigal son", "luke 15:11-32"),
    (r"the parable of the lost sheep", "luke 15:3-7"),
    (r"the parable of the sower", "matthew 13:1-23"),
    (r"the parable of the talents", "matthew 25:14-30"),
    (r"the (?:parable of the )?(?:ten|wise and foolish) virgins", "matthew 25:1-13"),
    (r"the rich man and lazarus", "luke 16:19-31"),
    (r"the raising of lazarus|jesus raised lazarus|lazarus,? come forth", "john 11:1-44"),
    (r"(?:blind )?bartimaeus|(?:blind )?bartimeus", "mark 10:46-52"),
    (r"zacch?a?e?us|zach?eus|zakeus", "luke 19:1-10"),
    (r"the last supper", "matthew 26:17-30"),
    (r"the garden of gethsemane|gethsemane", "matthew 26:36-46"),
    (r"the crucifixion of (?:jesus|christ)|the (?:story of the )?crucifixion story|the story of the crucifixion", "luke 23:26-49"),
    (r"the empty tomb|the resurrection story|the story of the resurrection", "matthew 28:1-10"),
    (r"the road to emmaus", "luke 24:13-35"),
    (r"doubting thomas", "john 20:24-29"),
    # Acts
    (r"the day of pentecost|the pentecost story", "acts 2"),
    (r"ananias and sapphira", "acts 5:1-11"),
    (r"the stoning of stephen|stephen (?:was )?stoned", "acts 7:54-60"),
    (r"philip and the ethiopian(?: eunuch)?", "acts 8:26-40"),
    (r"(?:saul|paul)'?s conversion|the conversion of (?:saul|paul)|the (?:road to damascus|damascus road)", "acts 9:1-19"),
    (r"paul and silas(?: in prison)?", "acts 16:16-40"),
    (r"the fruit of the spirit", "galatians 5:22-23"),
]
# "The story of X", "X's story", "the life of X": where X's story begins.
STORY_PEOPLE = [
    ("abraham", "genesis 12"), ("jacob", "genesis 25:19-34"), ("joseph", "genesis 37"),
    ("noah", "genesis 6"), ("moses", "exodus 2"), ("joshua", "joshua 1"), ("gideon", "judges 6"),
    ("samson", "judges 13"), ("ruth", "ruth 1"), ("hannah", "1 samuel 1"), ("samuel", "1 samuel 1"),
    ("david", "1 samuel 16"), ("solomon", "1 kings 3"), ("elijah", "1 kings 17"), ("elisha", "2 kings 2"),
    ("nehemiah", "nehemiah 1"), ("esther", "esther 1"), ("job", "job 1"), ("daniel", "daniel 1"),
    ("jonah", "jonah 1"), ("lazarus", "john 11:1-44"), ("nicodemus", "john 3:1-21"),
]
_STORY_OF = r"(?:the )?(?:bible )?(?:story|life) of (?:the )?(?:prophet |king |queen )?"
# Not when numbers follow ("the story of Daniel chapter 3"): the spoken reference wins.
_NO_NUMBER = r"(?!,?\s+(?:chapter|chapters|verse|verses|\d|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b)"
NAMED_PASSAGES += [(rf"\b(?:{p}){_NO_NUMBER}", ref) for p, ref in STORY_EPISODES]
NAMED_PASSAGES += [(rf"\b(?:{_STORY_OF}{name}\b|{name}'?s? (?:life )?story\b){_NO_NUMBER}", ref)
                   for name, ref in STORY_PEOPLE]

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

    def find_quote(self, text: str, near=None):
        """The verse quoted in `text` without a reference, or None. `near` is the
        Reference on screen, which gives context. The word index is built on
        first use (about a second)."""
        if getattr(self, "_quotes", None) is None:
            self._quotes = QuoteFinder(self.con)
        ctx = (near.book, near.chapter, near.chapter_end) if near is not None else None
        hit = self._quotes.find(text, ctx)
        if not hit:
            return None
        book, ch, v1, v2 = hit
        return Reference(book, ch, v1, ch, v2, text.strip())

    def find_story(self, text: str):
        """The chapter whose story is being retold in `text`, as a Reference, or None."""
        if getattr(self, "_stories", None) is None:
            self.find_quote("")  # builds the shared word index
            self._stories = StoryFinder(self._quotes, self.con)
        hit = self._stories.find(text)
        if not hit:
            return None
        book, ch = hit
        return Reference(book, ch, 1, ch, self.books[book][ch], text.strip())

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


# Quotations
# Spoken words that should match their KJV form (speech recognition and
# preachers often modernise: "you" for "thee", "has" for "hath").
QUOTE_EQUIV = {
    "thee": "you", "thou": "you", "ye": "you", "thy": "your", "thine": "your",
    "hath": "has", "doth": "does", "saith": "says", "shalt": "shall", "wilt": "will",
    "art": "are", "unto": "to", "upon": "on", "hast": "have", "didst": "did",
    "which": "that", "who": "that", "whom": "that", "sycamore": "sycomore",
}
# Very common words: matched for the order check, but worth almost nothing.
QUOTE_STOP = frozenset("""
a an and are as at be but by for from has have he her him his i if in is it its
me my not o of on or our shall she so that the their them then there these they
this to us was we were what when which who will with you your all no do did does
""".split())
QUOTE_MIN_WORDS = 5       # words matched in order
QUOTE_MIN_CONTENT = 3     # of which not in QUOTE_STOP
QUOTE_MIN_SCORE = 13.0    # summed rarity (IDF) of the matched words
QUOTE_SKIP_COST = 1.5     # extra score needed per word skipped
QUOTE_NEAR_WORDS = 4      # near the passage on screen: words matched ...
QUOTE_NEAR_SCORE = 7.0    # ... and score needed
QUOTE_MOVE_COVERAGE = 0.3 # moving to another verse of the chapter on screen needs this share of
                          # that verse ("and the earth was without form and void"), not a phrase
                          # from a retelling ("the den of lions ... the king")
QUOTE_MIN_RUN_SCORE = 8.0 # the same, when the words are exactly the verse's, unbroken
QUOTE_GAP = 0.4          # cost of each word skipped inside a match
QUOTE_SHORTLIST = 400     # verses considered per search ...
QUOTE_ALIGN = 25          # ... of which this many are aligned word by word
QUOTE_RECENT_SECONDS = 15 # a quote may run across pauses: sentences heard this recently count too
QUOTE_WINDOW = 40         # only the last N words heard are searched
QUOTE_MARGIN = 1.25       # best verse must beat the runner-up by this factor
QUOTE_CLOSE = 0.85        # ... and any tight runner-up scoring this close makes it ambiguous


def _stem(w: str) -> str:
    """Drop word endings so speech slips and KJV forms still match:
    created/create, strengthens/strengtheneth, heavens/heaven."""
    if w in QUOTE_STOP:
        return w
    for suf in ("eth", "est", "ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3 and not (suf == "s" and w.endswith("ss")):
            w = w[:-len(suf)]
            break
    if len(w) > 3 and w.endswith("e"):
        w = w[:-1]
    return w


class _WordForms(dict):
    """Spoken/KJV word -> its matching form, worked out once per distinct word."""
    def __missing__(self, w):
        f = self[w] = _stem(QUOTE_EQUIV.get(w, w))
        return f


_WORD_FORMS = _WordForms()


def _quote_words(text: str) -> list:
    forms = _WORD_FORMS
    return [forms[w] for w in re.findall(r"[a-z]+", text.lower().replace("'", ""))]


def contains(outer, inner) -> bool:
    """True if Reference `inner` lies within Reference `outer`."""
    return (outer is not None and outer.book == inner.book
            and (outer.chapter, outer.verse_start) <= (inner.chapter, inner.verse_start)
            and (inner.chapter_end, inner.verse_end) <= (outer.chapter_end, outer.verse_end))


class QuoteFinder:
    """Recognises a verse quoted without its reference ("for God so loved the
    world, that he gave his only begotten son" -> John 3:16).

    Rare words in what was heard pick candidate verses; each candidate is then
    lined up word by word, in order. A verse is returned only when the match is
    long, made of distinctive words, tight (few words skipped), and clearly
    better than any other verse, so ordinary speech and stock phrases that occur
    in many verses ("and the Lord said unto Moses") are ignored."""

    def __init__(self, con):
        self.rows = con.execute(
            "SELECT book, chapter, verse FROM verses ORDER BY book_index, chapter, verse").fetchall()
        texts = [t for (t,) in con.execute("SELECT text FROM verses ORDER BY book_index, chapter, verse")]
        self.words = [tuple(_quote_words(t)) for t in texts]
        index = {}
        for i, ws in enumerate(self.words):
            for w in set(ws):
                index.setdefault(w, []).append(i)
        n = len(self.words)
        self.index = {w: array("H", ids) for w, ids in index.items()}
        self.idf = {w: math.log(n / len(ids)) for w, ids in index.items()}
        self.chapter_rows = {}  # (book, chapter) -> first and last row
        for i, (book, ch, _) in enumerate(self.rows):
            first, _ = self.chapter_rows.get((book, ch), (i, i))
            self.chapter_rows[(book, ch)] = (first, i)

    def _weight(self, w: str) -> float:
        return 0.3 if w in QUOTE_STOP else self.idf.get(w, 0.0)

    def _align(self, q: list, v: tuple):
        """Best compact match of q against verse v (local alignment: each
        matched word adds its weight, each skipped word costs QUOTE_GAP).
        Returns (score, words, content_words, q_first, q_last, v_first, v_last)."""
        empty = (0.0, 0, 0, -1, -1)
        best = (0.0, 0, 0, -1, -1, -1, -1)
        prev = [empty] * (len(v) + 1)
        for i, qw in enumerate(q):
            cur = [empty] * (len(v) + 1)
            wq = self._weight(qw)
            content = qw not in QUOTE_STOP
            for j, vw in enumerate(v, 1):
                d = prev[j - 1]
                if vw == qw:
                    cell = ((d[0] + wq, d[1] + 1, d[2] + content, d[3], d[4]) if d[0] > 0
                            else (wq, 1, content, i, j - 1))
                else:
                    cell = (d[0] - 2 * QUOTE_GAP,) + d[1:]
                up, left = prev[j], cur[j - 1]
                if up[0] - QUOTE_GAP > cell[0]:
                    cell = (up[0] - QUOTE_GAP,) + up[1:]
                if left[0] - QUOTE_GAP > cell[0]:
                    cell = (left[0] - QUOTE_GAP,) + left[1:]
                if cell[0] <= 0:
                    cell = empty
                cur[j] = cell
                if vw == qw and cell[0] > best[0]:
                    best = (cell[0], cell[1], cell[2], cell[3], i, cell[4], j - 1)
            prev = cur
        return best

    @staticmethod
    def _tight(a) -> bool:
        """Few words skipped on either side."""
        s, k, c, qf, ql, vf, vl = a
        return k > 0 and ql - qf + 1 <= k * 1.5 + 1 and vl - vf + 1 <= k * 1.5 + 1

    def _good(self, a, verse_len: int) -> bool:
        s, k, c, qf, ql, vf, vl = a
        if not self._tight(a):
            return False
        unbroken = ql - qf + 1 == k == vl - vf + 1
        skipped = (ql - qf + 1 - k) + (vl - vf + 1 - k)
        if (k >= QUOTE_MIN_WORDS and c >= QUOTE_MIN_CONTENT
                and s >= QUOTE_MIN_SCORE + QUOTE_SKIP_COST * skipped):
            return True  # a loose quote must be more distinctive
        if (k >= QUOTE_MIN_WORDS and ql - qf + 1 - k <= 1 and vl - vf + 1 - k <= 1
                and s >= QUOTE_MIN_RUN_SCORE):
            return True  # "the Lord is my shepherd": the verse's words, in order
        return unbroken and k == verse_len and k >= 2 and s >= QUOTE_MIN_RUN_SCORE
        # ^ a short verse said in full: "Jesus wept", "Pray without ceasing"

    def _near_rows(self, near) -> set:
        """Rows of the passage on screen and its chapter(s), plus the next chapter:
        where the preacher is most likely reading from."""
        if near is None:
            return set()
        book, ch1, ch2 = near
        rows = set()
        for ch in range(ch1, ch2 + 2):
            span = self.chapter_rows.get((book, ch))
            if span:
                rows.update(range(span[0], span[1] + 1))
        return rows

    def _good_near(self, a) -> bool:
        s, k, c, *_ = a
        return self._tight(a) and k >= QUOTE_NEAR_WORDS and c >= 2 and s >= QUOTE_NEAR_SCORE

    def find(self, text: str, near=None):
        """(book, chapter, verse_start, verse_end) of the quoted verse(s), or None.
        `near` = (book, first_chapter, last_chapter) of the passage on screen:
        verses there need a little less to match, and win ties."""
        q = _quote_words(text)[-QUOTE_WINDOW:]
        near_rows = self._near_rows(near)
        content = sorted({w for w in q if w not in QUOTE_STOP and w in self.index},
                         key=lambda w: len(self.index[w]))
        if not content:
            return None
        # Candidates: verses sharing the most (rarity-weighted) content words.
        votes = {}
        for w in content[:8]:
            if len(self.index[w]) > 3000:
                break  # too common to narrow anything down
            for i in self.index[w]:
                votes[i] = votes.get(i, 0.0) + self.idf[w]
        if not votes and not near_rows:
            return None
        # Shortlist, then re-rank by shared word pairs (cheap) before the full
        # alignment, so quotes made of common words still find their verse.
        pairs = set(zip(q, q[1:]))
        shortlist = sorted(votes, key=votes.get, reverse=True)[:QUOTE_SHORTLIST]
        cands = sorted(shortlist, reverse=True, key=lambda i: (
            len(pairs.intersection(zip(self.words[i], self.words[i][1:]))), votes[i]))[:QUOTE_ALIGN]
        if near_rows:  # verses on screen / nearby that share at least two key words
            key = set(content)
            near_rows = {i for i in near_rows if len(key.intersection(self.words[i])) >= 2}
            cands = list(dict.fromkeys(cands + sorted(near_rows)))
        scored = sorted(((self._align(q, self.words[i]), i) for i in cands), reverse=True,
                        key=lambda x: (self._good(x[0], len(self.words[x[1]])), x[0][0]))
        hit = self._pick_near(scored, near_rows)
        if hit is None:
            best, i = scored[0]
            if not self._good(best, len(self.words[i])):
                return None
            for a, j in scored[1:]:
                close = (a[0] >= best[0] * QUOTE_CLOSE and self._tight(a)) or (
                    a[0] * QUOTE_MARGIN > best[0] and self._good(a, len(self.words[j])))
                if close and not self._neighbours(i, j):
                    return None  # another verse fits about as well: ambiguous
        else:
            best, i = hit
        book, ch, v = self.rows[i]
        start = end = v
        self.coverage = best[1] / max(1, len(self.words[i]))
        self.span = (best[3], best[4], len(q))
        # The quote runs on into the next verse(s), or began in the previous one:
        # only words the best verse did not already account for count.
        for step, part in ((1, q[best[4] + 1:]), (-1, q[:best[3]])):
            j = i + step
            while part and 0 <= j < len(self.rows) and self.rows[j][:2] == (book, ch):
                a = self._align(part, self.words[j])
                if a[1] < 3 or a[2] < 2 or not self._tight(a):
                    break
                start, end = min(start, self.rows[j][2]), max(end, self.rows[j][2])
                part = part[a[4] + 1:] if step == 1 else part[:a[3]]
                j += step
        return book, ch, start, end

    def _pick_near(self, scored, near_rows):
        """The best match inside the passage on screen, if it is clear there and
        nothing elsewhere is much better. Returns (alignment, row) or None."""
        near = [(a, i) for a, i in scored if i in near_rows and self._good_near(a)]
        if not near:
            return None
        near.sort(key=lambda x: x[0][0], reverse=True)
        best, i = near[0]
        for a, j in near[1:]:
            if a[0] * QUOTE_MARGIN > best[0] and not self._neighbours(i, j):
                return None  # "and God saw that it was good": several verses here
        for a, j in scored:
            if j not in near_rows and self._good(a, len(self.words[j])) and a[0] > best[0] * 1.5:
                return None  # clearly a different passage
        return best, i

    def _neighbours(self, i: int, j: int) -> bool:
        return abs(i - j) <= 2 and self.rows[i][:2] == self.rows[j][:2]


# Retellings
STORY_MAX_DF = 150       # a word counts only if it is in at most this many chapters (of 1,189)
STORY_MIN_WORDS = 3      # distinctive words from the same chapter ...
STORY_MIN_SCORE = 16.0   # ... adding up to at least this much
STORY_MARGIN = 1.3       # and the chapter must beat every other chapter (with 2+ such words) by this factor
STORY_WINDOW = 80        # words of recent speech considered
# Without a biblical name (Darius, Gath, Nineveh) the evidence must be tighter:
# a retelling packs the story's words close together ("an ark of gopher wood ...
# a flood"), while sermon imagery spreads them over several sentences.
STORY_NO_NAME_WORDS = 4  # rare words from the chapter ...
STORY_NO_NAME_SPAN = 25  # ... within this many words of each other,
STORY_SIGNATURE_DF = 10  # ... one of them a signature word, in at most this many chapters (gopher, husks)
STORY_KNOWN_BONUS = 1.15 # chapters where a well-known story starts
# Chapters that retell a story told earlier: counted as the original.
STORY_RETOLD = {("Acts", 22): ("Acts", 9), ("Acts", 26): ("Acts", 9)}
# Rare in the KJV but common in sermons: no evidence of any one story.
STORY_IGNORE = frozenset(_stem(w) for w in """
amen hallelujah alleluia praise church pastor brethren beloved saints congregation
""".split())


class StoryFinder:
    """Recognises a Bible story told in the preacher's own words ("Darius couldn't
    sleep, worried about Daniel and the lions") from distinctive words that come
    from the same chapter: names, places and rare words. Uses only the KJV text,
    so it covers every chapter."""

    def __init__(self, quotes: "QuoteFinder", con):
        self.chapters = []          # (book, chapter)
        tf = {}                     # word -> {chapter id: count}
        cid = {}
        for (book, ch, _), words in zip(quotes.rows, quotes.words):
            key = (book, ch)
            if key not in cid:
                cid[key] = len(self.chapters)
                self.chapters.append(key)
            c = cid[key]
            for w in words:
                if w in QUOTE_STOP:
                    continue
                d = tf.setdefault(w, {})
                d[c] = d.get(c, 0) + 1
        n = len(self.chapters)
        self.postings = {w: d for w, d in tf.items() if len(d) <= STORY_MAX_DF and w not in STORY_IGNORE}
        self.alias = {cid[a]: cid[b] for a, b in STORY_RETOLD.items()}
        # Names: words the KJV capitalises (almost) everywhere, sentence starts aside.
        cap, total = {}, {}
        for (text,) in con.execute("SELECT text FROM verses"):
            for m in re.finditer(r"(?<![.?!:;] )(?<!^)\b([A-Za-z]+)\b", text):
                w = m[1].lower()
                total[w] = total.get(w, 0) + 1
                if m[1][0].isupper():
                    cap[w] = cap.get(w, 0) + 1
        self.names = {_WORD_FORMS[w] for w, n in total.items() if cap.get(w, 0) >= 0.9 * n}
        known = {(m[1], int(m[2])) for _, ref in STORY_EPISODES + STORY_PEOPLE
                 for m in [re.match(r"((?:\d )?[a-z ]+?) (\d+)", ref)]}
        self.bonus = {i: STORY_KNOWN_BONUS for i, (book, ch) in enumerate(self.chapters)
                      if (book.lower(), ch) in known}
        self.idf = {w: math.log(n / len(d)) for w, d in self.postings.items()}

    def find(self, text: str):
        """(book, chapter) of the story being told, or None."""
        heard = _quote_words(text)[-STORY_WINDOW:]
        words = {w for w in heard if w not in QUOTE_STOP}
        score, hits, named = {}, {}, {}
        for w in words:
            seen = set()
            for c, count in self.postings.get(w, {}).items():
                c = self.alias.get(c, c)
                if c in seen:
                    continue
                seen.add(c)
                score[c] = score.get(c, 0.0) + self.idf[w] * min(1 + math.log(count), 2.5)
                hits[c] = hits.get(c, 0) + 1
                if w in self.names:
                    named[c] = True
        if not score:
            return None
        for c in score:
            score[c] *= self.bonus.get(c, 1.0)
        ranked = sorted(score, key=score.get, reverse=True)
        best = ranked[0]
        if hits[best] < STORY_MIN_WORDS or score[best] < STORY_MIN_SCORE:
            return None
        if not named.get(best) and not self._dense(heard, best):
            return None
        for c in ranked[1:]:
            if score[c] * STORY_MARGIN <= score[best]:
                break
            if hits[c] >= 2:
                return None  # another chapter fits nearly as well
        return self.chapters[best]

    def _dense(self, heard: list, c: int) -> bool:
        """STORY_NO_NAME_WORDS different words of chapter c within STORY_NO_NAME_SPAN words."""
        first = {}
        for i, w in enumerate(heard):
            if w not in first and w not in QUOTE_STOP:
                d = self.postings.get(w)
                if d and any(self.alias.get(x, x) == c for x in d):
                    first[w] = i
        if not any(len(self.postings[w]) <= STORY_SIGNATURE_DF for w in first):
            return False
        pos = sorted(first.values())
        n = STORY_NO_NAME_WORDS
        return any(pos[j + n - 1] - pos[j] < STORY_NO_NAME_SPAN for j in range(len(pos) - n + 1))


def reconcile(refs: list, quote, last) -> list:
    """Add a quoted verse to the references found in the same words, as the newest
    one, unless one of them (or the passage on screen) already covers it."""
    if quote is None or quote is last or any(contains(r, quote) for r in refs):
        return refs
    return refs + [quote]


class Session:
    """Detection across a sermon: remembers the last reference shown so that
    follow-ups ("next verse", "verse seventeen", "read it again") work."""

    def __init__(self, kjv: KJV):
        self.kjv = kjv
        self.last = None  # last Reference put on screen
        self._story_text = []     # sentences heard since the screen last changed
        self._story_for = None    # ... i.e. since self.last became this
        self._recent = []         # (time, sentence) heard lately, for quotes said with pauses
        self._recent_for = None

    def with_recent(self, text: str, now: float = None) -> str:
        """`text` after the sentences heard in the last QUOTE_RECENT_SECONDS
        since the screen last changed, so a quote said with pauses adds up."""
        now = time.time() if now is None else now
        if self.last is not self._recent_for:
            self._recent, self._recent_for = [], self.last
        self._recent = [(t, s) for t, s in self._recent if now - t <= QUOTE_RECENT_SECONDS]
        return " ".join([s for _, s in self._recent] + [text])

    def quote_heard(self, text: str, now: float = None):
        """The verse quoted in `text`, or else in `text` with what was heard just
        before it."""
        quote = self.quote(text)
        if quote is None:
            joined = self.with_recent(text, now)
            if joined != text:
                quote = self.quote(joined)
                # It must be one quote running across the pause: started before
                # the new words and still going in them.
                if quote is not None:
                    first, last, heard = self.kjv._quotes.span
                    new = heard - len(_quote_words(text))
                    if not first < new <= last:
                        quote = None
        return quote

    def hear(self, text: str, now: float = None) -> list:
        now = time.time() if now is None else now
        refs = self._hear(text, now)
        self.with_recent("", now)  # drops the sentences if the screen changed
        self._recent.append((now, text))
        return refs

    def _hear(self, text: str, now: float) -> list:
        refs = self.kjv.find(text)
        quote = self.quote_heard(text, now)
        if refs:
            # The words read aloud beat a reference that doesn't cover them: the
            # reference was probably misheard ("Genesis eleven" + Genesis 1:1 read).
            # It stays in the list, so the operator can still pick it.
            refs = reconcile(refs, quote, self.last)
        elif quote is not None:
            if quote is self.last:
                self.story(text)  # keep the retelling's sentences, but leave the screen as it is
                return []
            # A loose quote inside a story being retold: show the story's chapter.
            story = self.story(text) if self.kjv._quotes.coverage < QUOTE_MOVE_COVERAGE else None
            if story is not None and (story.book, story.chapter) == (quote.book, quote.chapter):
                quote = story
            return [self._remember(quote)]
        if not refs and self.last is not None:
            refs = self._follow_up(text)
        if not refs:
            story = self.story(text)
            if story is not None:
                refs = [story]
        if refs:
            self.last = refs[-1]
        return refs

    def story(self, text: str):
        """A Bible story retold in the preacher's own words over the last few
        sentences, or None. Nothing if it is the chapter already on screen."""
        if self.last is not self._story_for:  # the screen changed: start afresh
            self._story_text, self._story_for = [], self.last
        self._story_text.append(text)
        ref = self.kjv.find_story(" ".join(self._story_text))
        last = self.last
        if ref is None or (last is not None and last.book == ref.book
                           and last.chapter <= ref.chapter <= last.chapter_end):
            return None
        return ref

    def quote(self, text: str):
        """The verse quoted in `text`, or None. A quote from the passage already
        on screen (the preacher reading it aloud) returns self.last unchanged."""
        ref = self.kjv.find_quote(text, self.last)
        if ref is None:
            return None
        last = self.last
        if contains(last, ref):
            return last
        reading_on = (last is not None and ref.book == last.book and ref.chapter == last.chapter_end
                      and last.verse_end < ref.verse_start <= last.verse_end + 2) or (
                      last is not None and ref.book == last.book and ref.chapter == last.chapter
                      and last.verse_start - 2 <= ref.verse_end < last.verse_start)
        if (last is not None and ref.book == last.book and last.chapter <= ref.chapter <= last.chapter_end
                and self.kjv._quotes.coverage < QUOTE_MOVE_COVERAGE and not reading_on):
            return None  # a phrase of the chapter on screen, not a reading of another verse
        return ref

    def _remember(self, ref):
        self.last = ref
        return ref

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
