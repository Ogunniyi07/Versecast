"""Browser glue: runs the real scripture_refs.py inside Pyodide.

preview(text)  -> live, stateless look at what's being said (called many times
                  per sentence while the speaker is still talking).
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


def _out(ref, words_after=0):
    return {
        "label": ref.label(),
        "spoken": ref.spoken,
        "after": words_after,
        "whole": _kjv.is_whole_chapter(ref),
        "verses": [[c, v, t] for c, v, t in _kjv.verse_texts(ref)],
    }


def preview(text: str) -> str:
    return json.dumps([_out(r, n) for r, n in _kjv.find_detailed(text)])


def commit(text: str) -> str:
    return json.dumps([_out(r) for r in _session.hear(text)])


def focus(label: str) -> str:
    refs = _kjv.find(label)
    if refs:
        _session.last = refs[-1]
    return json.dumps(bool(refs))


def detect(text: str) -> str:  # older name, kept for compatibility
    return commit(text)
