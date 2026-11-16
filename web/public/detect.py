"""Browser glue: runs the real scripture_refs.py inside Pyodide.

preview(text)  -> live look at what's being said (called many times per
                  sentence while the speaker is still talking). Falls back to a
                  quoted verse ("for God so loved the world...").
commit(text)   -> a finished sentence; goes through the Session, so follow-ups
                  ("next verse", "verse seventeen") resolve against the last
                  reference.
focus(label)   -> the operator picked a reference; follow-ups are relative to it.
All return JSON.
"""
import json

import scripture_refs

_kjv = scripture_refs.KJV()
_session = scripture_refs.Session(_kjv)
_kjv.find_quote("")  # build the quote index now, while the page is loading


def _out(ref, words_after=0):
    return {
        "label": ref.label(),
        "spoken": ref.spoken,
        "after": words_after,
        "whole": _kjv.is_whole_chapter(ref),
        "verses": [[c, v, t] for c, v, t in _kjv.verse_texts(ref)],
    }


def preview(text: str) -> str:
    found = _kjv.find_detailed(text)
    quote = _session.quote(text)
    # A clear reading of a verse is shown at once (after=1), also when a
    # (probably misheard) reference in the same words doesn't cover it. A reading
    # of what's already on screen changes nothing.
    refs = scripture_refs.reconcile([r for r, _ in found], quote, _session.last)
    if len(refs) > len(found):
        found = found + [(refs[-1], 1)]
    return json.dumps([_out(r, n) for r, n in found])


def commit(text: str) -> str:
    return json.dumps([_out(r) for r in _session.hear(text)])


def focus(label: str) -> str:
    refs = _kjv.find(label)
    if refs:
        _session.last = refs[-1]
    return json.dumps(bool(refs))
