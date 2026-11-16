"""Build kjv.sqlite from the public-domain KJV JSON (thiagobodruk/bible, en_kjv.json).

Usage: python3 -I build_kjv_db.py <path/to/en_kjv.json> <output.sqlite>
       python3 -I build_kjv_db.py --clean kjv.sqlite   # fix spacing in an existing DB
"""
import json
import re
import sqlite3
import sys


def clean_text(text: str) -> str:
    """Fix spacing quirks in the source data, e.g. 'the LORD .' -> 'the LORD.'"""
    text = re.sub(r"\s+([.,;:?!)])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def clean_existing(db: str) -> int:
    """Apply clean_text to an already-built database. Returns rows changed."""
    con = sqlite3.connect(db)
    rows = con.execute("SELECT rowid, text FROM verses").fetchall()
    changed = [(clean_text(t), rid) for rid, t in rows if clean_text(t) != t]
    con.executemany("UPDATE verses SET text = ? WHERE rowid = ?", changed)
    con.commit()
    con.close()
    return len(changed)


def main(src: str, dst: str) -> None:
    with open(src, encoding="utf-8-sig") as f:
        books = json.load(f)

    con = sqlite3.connect(dst)
    con.execute("DROP TABLE IF EXISTS verses")
    con.execute(
        "CREATE TABLE verses (book_index INTEGER, book TEXT, chapter INTEGER, "
        "verse INTEGER, text TEXT, PRIMARY KEY (book_index, chapter, verse))"
    )
    rows = []
    for book_index, book in enumerate(books, start=1):
        for c_idx, chapter in enumerate(book["chapters"], start=1):
            for v_idx, text in enumerate(chapter, start=1):
                rows.append((book_index, book["name"], c_idx, v_idx, clean_text(text)))
    con.executemany("INSERT INTO verses VALUES (?, ?, ?, ?, ?)", rows)
    con.commit()
    con.close()
    print(f"Wrote {len(rows)} verses from {len(books)} books to {dst}")


if __name__ == "__main__":
    if sys.argv[1] == "--clean":
        print(f"Cleaned {clean_existing(sys.argv[2])} verses in {sys.argv[2]}")
    else:
        main(sys.argv[1], sys.argv[2])
