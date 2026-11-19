"use client";

// Listening + display state for VerseCast.
// Speech comes from the browser's SpeechRecognition (Chrome, Edge, Safari),
// which streams words while the speaker is still talking. Each update is run
// through the detector; a reference goes on screen as soon as it is safe:
//  - words already follow it            -> show now
//  - it's the last thing said (verse)   -> wait 350 ms in case it grows
//  - it's the last thing said (chapter) -> wait 1.2 s ("John 3" ... "verse 16")
// When a sentence ends it is committed, so follow-ups ("next verse") resolve.

import { useCallback, useEffect, useRef, useState } from "react";
import { accentLabel, DEFAULT_ACCENT, FALLBACK_ACCENT } from "./accents";
import { VOICE_UNSUPPORTED, isIOSNonSafari, micPrompting, voiceTip } from "./browser";
import { loadDetector, type Detector, type Ref } from "./detector";
import { track } from "./analytics";
import { type Entry, loadTranscript, saveTranscript, verseEntry } from "./transcript";

const HISTORY_MAX = 9;
const WAIT_VERSE_MS = 350;
const WAIT_CHAPTER_MS = 1200;
const ALTERNATIVES = 5; // the speech service's other guesses for a finished sentence

/* eslint-disable @typescript-eslint/no-explicit-any */
type SpeechRecognitionLike = any;

export const LOAD_EXPECTED_MS = 7000;

export type Status = "loading" | "ready" | "unsupported" | "error";

export type Take = { text: string; mode: "spoken" | "typed" | "arrows" };

export function useVerseCast() {
  const [status, setStatus] = useState<Status>("loading");
  const [statusNote, setStatusNote] = useState("Loading…");
  const [loadDone, setLoadDone] = useState(0);
  const [listening, setListening] = useState(false);
  const [starting, setStarting] = useState(false);
  const [tip, setTip] = useState<string | null>(null);
  const [slowLoad, setSlowLoad] = useState(false);
  const startTimer = useRef<ReturnType<typeof setTimeout>>();
  const [hearing, setHearing] = useState({ final: "", interim: "" });
  const [history, setHistory] = useState<Ref[]>([]);
  const [shown, setShown] = useState<number>(-1);
  const [hidden, setHidden] = useState(false);
  const [take, setTake] = useState<Take | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [accent, setAccentState] = useState(DEFAULT_ACCENT);
  const accentRef = useRef(DEFAULT_ACCENT);
  const [typedMiss, setTypedMiss] = useState(false);
  const [transcript, setTranscript] = useState<Entry[]>([]);
  const transcriptRef = useRef<Entry[]>([]);
  const pendingVerses = useRef<Entry[]>([]); 
  const pendingInterim = useRef("");

  const detector = useRef<Detector | null>(null);
  const rec = useRef<SpeechRecognitionLike>(null);
  const listeningRef = useRef(false);
  const utterRefs = useRef<string[]>([]); // labels the current sentence put in the history
  const waitTimer = useRef<ReturnType<typeof setTimeout>>();
  const historyRef = useRef<Ref[]>([]);
  historyRef.current = history;
  const shownRef = useRef(-1);
  const lastCounted = useRef(""); // so a verse previewed then committed counts once
  shownRef.current = shown;

  // transcript
  const addEntries = useCallback((...entries: Entry[]) => {
    if (!entries.length) return;
    const next = transcriptRef.current.concat(entries);
    transcriptRef.current = next;
    setTranscript(next);
    saveTranscript(next);
  }, []);

  // A finished sentence, followed by any verse it put on screen.
  const addSpeech = useCallback((text: string) => {
    const t = Date.now();
    const pending = pendingVerses.current.map((e) => ({ ...e, t }));
    pendingVerses.current = [];
    addEntries(...(text.trim() ? [{ t, kind: "speech" as const, text: text.trim() }] : []), ...pending);
  }, [addEntries]);

  const clearTranscript = useCallback(() => {
    transcriptRef.current = [];
    pendingVerses.current = [];
    setTranscript([]);
    saveTranscript([]);
  }, []);

  // loading
  useEffect(() => {
    const saved = loadTranscript();
    transcriptRef.current = saved;
    setTranscript(saved);
    try {
      const saved = localStorage.getItem("vb-accent");
      if (saved) { accentRef.current = saved; setAccentState(saved); }
    } catch { /* storage blocked */ }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const slow = setTimeout(() => !cancelled && setSlowLoad(true), LOAD_EXPECTED_MS + 3000);
    loadDetector((note, done) => { if (!cancelled) { setStatusNote(note); setLoadDone(done); } })
      .then((d) => {
        if (cancelled) return;
        clearTimeout(slow);
        setSlowLoad(false);
        setLoadDone(1);
        detector.current = d;
        const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        setStatus(SR ? "ready" : "unsupported");
        setTip(voiceTip());
      })
      .catch((e) => {
        console.error(e);
        if (!cancelled) {
          setStatus("error");
          setStatusNote(`${e.message || e}. Check your connection and reload the page.`);
        }
      });
    return () => { cancelled = true; clearTimeout(slow); };
  }, []);

  // Display - Put a sentence's references into the history; the newest goes on screen.
  const present = useCallback((refs: Ref[], text: string, mode: Take["mode"]) => {
    const labels = refs.map((r) => r.label);
    const next = historyRef.current
      .filter((h) => !utterRefs.current.includes(h.label) && !labels.includes(h.label))
      .concat(refs)
      .slice(-HISTORY_MAX);
    utterRefs.current = labels;
    historyRef.current = next;
    setHistory(next);
    setShown(next.length - 1);
    setHidden(false);
    setTypedMiss(false);
    setTake({ text, mode });
    const newest = labels[labels.length - 1];
    if (newest !== lastCounted.current) {
      lastCounted.current = newest;
      track(mode === "typed" ? "verse-shown-typed" : "verse-shown-spoken");
      const entry = verseEntry(refs[refs.length - 1]);
      if (mode === "spoken") pendingVerses.current.push(entry);
      else addEntries(entry);
    }
  }, [addEntries]);

  const onSpeech = useCallback((text: string, final: boolean) => {
    clearTimeout(waitTimer.current);
    const d = detector.current;
    if (!d || !text.trim()) return;
    if (final) {
      const refs = d.commit(text);
      if (refs.length) present(refs, text, "spoken");
      utterRefs.current = [];
      return;
    }
    const refs = d.preview(text);
    if (!refs.length) return;
    const last = refs[refs.length - 1];
    if (last.after >= 1) return present(refs, text, "spoken");
    waitTimer.current = setTimeout(() => present(refs, text, "spoken"),
      last.whole ? WAIT_CHAPTER_MS : WAIT_VERSE_MS);
  }, [present]);

  // A sentence from the speech service: finished, or still being spoken.
  const heard = useCallback((text: string, final: boolean) => {
    if (final) {
      pendingInterim.current = "";
      onSpeech(text, true);
      addSpeech(text);
    } else if (text.trim()) {
      pendingInterim.current = text.trim();
      onSpeech(text, false);
    }
  }, [onSpeech, addSpeech]);

  //listening
  const stop = useCallback(() => {
    listeningRef.current = false;
    setListening(false);
    setStarting(false);
    clearTimeout(waitTimer.current);
    clearTimeout(startTimer.current);
    try { rec.current?.stop(); } catch { /* already stopped */ }
    rec.current = null;
  }, []);

  const start = useCallback(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR || !detector.current) return;
    const r = new SR();
    r.continuous = true;
    r.interimResults = true;
    r.lang = accentRef.current;
    r.maxAlternatives = ALTERNATIVES;
    r.onresult = (e: any) => {
      let finals = "", interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) {
          // Of the service's guesses, use the first that contains a Bible
          // reference; otherwise its top guess.
          let best = res[0].transcript;
          for (let j = 0; j < res.length; j++) {
            if (detector.current?.preview(res[j].transcript).length) { best = res[j].transcript; break; }
          }
          finals += best;
          heard(best, true);
        } else {
          interim += res[0].transcript;
        }
      }
      setHearing({ final: finals.trim(), interim: interim.trim() });
      heard(interim, false);
    };
    r.onerror = (e: any) => {
      if (e.error === "no-speech" || e.error === "aborted") return;
      if (e.error === "language-not-supported" && r.lang !== FALLBACK_ACCENT) {
        // e.g. Safari without Nigerian English: carry on in American English.
        setNotice(`${accentLabel(r.lang)} isn't available in this browser, so VerseCast switched to ${accentLabel(FALLBACK_ACCENT)}. Chrome supports more accents.`);
        r.lang = FALLBACK_ACCENT;
        accentRef.current = FALLBACK_ACCENT;
        setAccentState(FALLBACK_ACCENT);
        return; // onend restarts recognition with the new accent
      }
      track(`error-${e.error}`);
      if (e.error === "service-not-allowed" && isIOSNonSafari()) {
        setNotice(VOICE_UNSUPPORTED);
      } else if (/not-allowed|service-not-allowed/.test(e.error)) {
        setNotice("Microphone blocked. Allow mic access in the address bar, or type a reference below.");
      } else if (e.error === "network") {
        setNotice("Listening needs an internet connection. Check your connection and try again.");
      } else {
        setNotice(`Listening stopped (${e.error}).`);
      }
      if (/not-allowed|service-not-allowed|network/.test(e.error)) stop();
    };
    // Browsers end recognition after a pause; keep listening until Stop.
    r.onend = () => {
      const unfinished = pendingInterim.current;
      pendingInterim.current = "";
      if (unfinished) heard(unfinished, true);
      if (listeningRef.current && rec.current === r) {
        try { r.start(); } catch { /* restarting too fast */ }
      } else if (!listeningRef.current) {
        addSpeech(""); // a verse shown mid-sentence
        setHearing({ final: "", interim: "" });
        addEntries({ t: Date.now(), kind: "stop" });
      }
    };
    // If the speech engine hasn't started within about 3 s, it isn't going to.
    const started = () => { clearTimeout(startTimer.current); if (rec.current === r) setStarting(false); };
    r.onstart = started;
    r.onaudiostart = started;
    const check = async () => {
      if (rec.current !== r || !listeningRef.current) return;
      if (await micPrompting()) { startTimer.current = setTimeout(check, 3000); return; }
      if (rec.current !== r) return;
      track("error-no-start");
      stop();
      setNotice(VOICE_UNSUPPORTED);
    };
    clearTimeout(startTimer.current);
    startTimer.current = setTimeout(check, 3000);
    setStarting(true);
    rec.current = r;
    listeningRef.current = true;
    utterRefs.current = [];
    setNotice(null);
    setHearing({ final: "", interim: "" });
    setListening(true);
    pendingInterim.current = "";
    addEntries({ t: Date.now(), kind: "start" });
    track(`listen-start-${accentRef.current}`);
    try {
      r.start();
    } catch (e: any) {
      stop();
      setNotice(`Couldn't start listening: ${e.message || e}`);
    }
  }, [heard, stop, addSpeech, addEntries]);

  const toggleListening = useCallback(() => (listeningRef.current ? stop() : start()), [start, stop]);

  // Change accent; if listening, restart recognition so it takes effect now.
  const setAccent = useCallback((code: string) => {
    accentRef.current = code;
    setAccentState(code);
    try { localStorage.setItem("vb-accent", code); } catch { /* storage blocked */ }
    track(`accent-${code}`);
    if (listeningRef.current) {
      stop();
      setTimeout(start, 300);
    }
  }, [start, stop]);

  useEffect(() => () => stop(), [stop]);

  // other input
  const check = useCallback((text: string) => {
    const d = detector.current;
    if (!d || !text.trim()) return;
    const refs = d.commit(text);
    utterRefs.current = [];
    if (refs.length) {
      present(refs, text, "typed");
      utterRefs.current = []; // a typed check is its own complete sentence
    } else {
      setTake({ text, mode: "typed" });
      setTypedMiss(true);
      track("typed-not-found");
    }
  }, [present]);

  // The operator picked a reference: show it, and make follow-ups relative to it.
  const pick = useCallback((index: number, record = true) => {
    const ref = historyRef.current[index];
    if (!ref) return;
    setShown(index);
    setHidden(false);
    detector.current?.focus(ref.label);
    if (record) addEntries(verseEntry(ref));
  }, [addEntries]);

  // A verse pill in the transcript was clicked: show that verse again (back in
  // "Recent" if it dropped out). Not written to the transcript a second time.
  const showVerse = useCallback((label: string) => {
    track("transcript-verse-click");
    const index = historyRef.current.findIndex((h) => h.label === label);
    if (index >= 0) return pick(index, false);
    const d = detector.current;
    const ref = d?.preview(label).find((r) => r.label === label);
    if (!d || !ref) return;
    const next = historyRef.current.concat([ref]).slice(-HISTORY_MAX);
    historyRef.current = next;
    utterRefs.current = [];
    setHistory(next);
    setShown(next.length - 1);
    setHidden(false);
    setTypedMiss(false);
    d.focus(label);
  }, [pick]);

  const toggleHidden = useCallback(() => setHidden((h) => !h), []);

  // Arrow buttons / keys: the verse after or before what's on screen
  // ("next" after John 3:36 is John 4:1; after Romans 8:28-39 it is 9:1).
  const step = useCallback((dir: 1 | -1) => {
    const d = detector.current;
    const ref = historyRef.current[shownRef.current];
    if (!d || !ref) return;
    d.focus(ref.label);
    const [next] = d.commit(dir > 0 ? "next verse" : "previous verse");
    if (!next) return; // e.g. "previous" at Genesis 1:1
    // Replace the shown entry instead of adding one, so stepping through
    // verses doesn't push the preacher's references out of "Recent".
    const list = historyRef.current.slice();
    const existing = list.findIndex((h) => h.label === next.label);
    let index = shownRef.current;
    if (existing >= 0 && existing !== index) index = existing;
    else list[index] = next;
    historyRef.current = list;
    utterRefs.current = [];
    setHistory(list);
    setShown(index);
    setHidden(false);
    setTake({ text: dir > 0 ? "Next verse" : "Previous verse", mode: "arrows" });
    addEntries(verseEntry(next));
  }, [addEntries]);

  return {
    status, statusNote, loadDone, slowLoad, listening, starting, tip, hearing, history, shown, hidden, take, notice, typedMiss,
    toggleListening, check, pick, toggleHidden, step, accent, setAccent,
    transcript, clearTranscript, showVerse,
    current: shown >= 0 ? history[shown] : null,
    onSpeech: heard, // exposed for automated tests
  };
}
