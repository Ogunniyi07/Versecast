# VerseCast

VerseCast listens to a sermon and puts the Bible verse on screen as soon as the preacher mentions it. It runs in the web browser, uses the King James Version (public domain), and shows verses automatically, with no operator confirmation step.

> **Status: early testing.** VerseCast is a web app that anyone can open from a link. It needs an internet connection, because listening uses the browser's speech recognition. An offline desktop version is planned for later.

## Using it

1. Open the site in **Chrome, Edge or Safari**. Firefox has no built-in speech recognition, but you can still type a sentence there.
2. Tap **Start listening** and allow microphone access.
3. Keep talking. Each verse appears as soon as you say it.

Other controls:

- When several references come up, the newest is shown. Click an earlier one, or press its number key (1–9), to show it instead.
- Use the **←** and **→** buttons (or arrow keys) to step to the previous or next verse.
- Press **H** or **Esc** to hide the verse instantly, and again to bring it back.
- **Open display** opens a window that shows only the verse, for a projector or second screen. It follows the main page live. Press **F** in it for full screen. In Chrome and Edge it can open straight onto a connected second screen after you allow it once. Passages too long for the screen scroll slowly on their own; pause, slow down or speed up from the main page (or press **P**, **−**, **+**).
- **Send feedback** (bottom of the page) tells us what went right or wrong.

## What it recognises

The detector turns what was said into a KJV reference and checks that the reference exists. Some examples:

| Said | Shown |
|---|---|
| "John three sixteen", "John chapter 3, verse 16", "John 3:16" | John 3:16 |
| "Psalm 23", "the twenty-third Psalm" | Psalm 23 (whole chapter) |
| "Romans 8 verse 28 to the end" | Romans 8:28–39 |
| "Matthew 1 and 3" | Matthew 1 and Matthew 3 (operator picks) |
| "Genesis chapters one to three" | Genesis 1–3 |
| "Psalm 119 verses 9, 11 and 105" | Psalm 119:9, 119:11, 119:105 |
| "Psalm one nineteen, one oh five" | Psalm 119:105 |
| "the sixteenth verse of the third chapter of John" | John 3:16 |
| "First epistle of John, chapter one, verse nine" | 1 John 1:9 |
| "John 3:16, sorry, John 4:24" | John 4:24 |
| "next verse" / "verse seventeen" / "read it again" (each said right after John 3:16) | John 3:17 / John 3:17 / John 3:16 |
| "The Lord's Prayer" | Matthew 6:9–13 |

Ordinary speech is ignored: "Mark my words, I'll be there at two thirty" and "we have three services on Sunday" show nothing. References that don't exist, such as "Psalm 151", are rejected.

## How it works

```
microphone ──► browser speech recognition ──► reference detector ──► KJV lookup ──► screen
               (Chrome / Edge / Safari)        scripture_refs.py     kjv.sqlite
```

- **Speech recognition:** the browser's built-in service. Words arrive while you are still speaking, so a verse can be shown before you finish the sentence. The audio is processed by Google in Chrome, Microsoft in Edge, or Apple in Safari.
- **`scripture_refs.py`** finds references in the transcript. It handles spoken numbers, "chapter"/"verse" wording, ranges, lists, ordinals, corrections and follow-ups. It is plain Python (standard library only) and runs inside the browser through [Pyodide](https://pyodide.org).
- **The interface** is a [Next.js](https://nextjs.org) app styled with [Tailwind CSS](https://tailwindcss.com), exported as a static site, so it needs no server.
- **`kjv.sqlite`** holds the 31,102 KJV verses, built by `build_kjv_db.py` from [thiagobodruk/bible](https://github.com/thiagobodruk/bible).

## Running it locally

Requires Python 3.9+ and Node.js 18+.

```bash
python3 build_web.py      # copies the detector and database into web/public/
cd web
npm install
npm run dev               # then open http://localhost:3000
```

Run `python3 build_web.py` again whenever `scripture_refs.py` changes. To build the static site, run `npm run build`; the result is in `web/out/`.

## Deploying

The repo deploys to [Netlify](https://www.netlify.com) as-is. `netlify.toml` runs `build_web.py`, builds the Next.js app and publishes `web/out/`. Feedback is collected by Netlify Forms (the form is declared in `web/public/__forms.html`); turn on form detection in the site settings.

To deploy manually:

```bash
python3 build_web.py && (cd web && npm run build) && npx netlify-cli deploy --prod --dir web/out
```

## Tests

```bash
python3 -m unittest -v test_scripture_refs test_phrase_sheet
```

- `test_scripture_refs.py` covers the detector rules.
- `test_phrase_sheet.py` runs all 250 scenarios in `testing/test_phrases.csv` (accents and noisy rooms excepted) and fails if any phrase regresses.

To grade the whole sheet and see the results per category:

```bash
python3 testing/run_phrases.py        # writes testing/results_text.csv
```

## Project layout

```
scripture_refs.py      reference detector (KJV, Session for follow-ups)
build_kjv_db.py        builds kjv.sqlite from the KJV JSON
kjv.sqlite             KJV verse database
build_web.py           copies the detector and database into web/public/
web/                   the web app (Next.js + Tailwind CSS)
  app/                 page and layout
  components/          header, mic, type box, verse screen, feedback dialog
  lib/                 detector loader (Pyodide) and listening logic
  public/detect.py     glue between the page and scripture_refs.py
testing/               250-phrase test sheet and grader
test_*.py              unit tests
netlify.toml           Netlify build settings
```

## Roadmap

1. Collect tester feedback and improve recognition
2. Test on recorded sermons and measure false positives
3. Offline desktop version for churches with poor internet (Windows)
4. Recognise passages read aloud without a spoken reference
