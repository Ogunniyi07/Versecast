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
import { loadDetector, type Detector, type Ref } from "./detector";

const HISTORY_MAX = 9;
const WAIT_VERSE_MS = 350;
const WAIT_CHAPTER_MS = 1200;

/* eslint-disable @typescript-eslint/no-explicit-any */
type SpeechRecognitionLike = any;

export type Status = "loading" | "ready" | "unsupported" | "error";

export type Take = { text: string; mode: "spoken" | "typed" };

export function useVerseCast() {
  const [status, setStatus] = useState<Status>("loading");
  const [statusNote, setStatusNote] = useState("Loading…");
  const [listening, setListening] = useState(false);
  const [hearing, setHearing] = useState({ final: "", interim: "" });
  const [history, setHistory] = useState<Ref[]>([]);
  const [shown, setShown] = useState<number>(-1);
  const [hidden, setHidden] = useState(false);
  const [take, setTake] = useState<Take | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [typedMiss, setTypedMiss] = useState(false);

  const detector = useRef<Detector | null>(null);
  const rec = useRef<SpeechRecognitionLike>(null);
  const listeningRef = useRef(false);
  const utterRefs = useRef<string[]>([]); // labels the current sentence put in the history
  const waitTimer = useRef<ReturnType<typeof setTimeout>>();
  const historyRef = useRef<Ref[]>([]);
  historyRef.current = history;

  // loading
  useEffect(() => {
    let cancelled = false;
    loadDetector((note) => !cancelled && setStatusNote(note))
      .then((d) => {
        if (cancelled) return;
        detector.current = d;
        const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        setStatus(SR ? "ready" : "unsupported");
      })
      .catch((e) => {
        console.error(e);
        if (!cancelled) {
          setStatus("error");
          setStatusNote(`${e.message || e}. Check your connection and reload the page.`);
        }
      });
    return () => { cancelled = true; };
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
  }, []);

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

  //listening
  const stop = useCallback(() => {
    listeningRef.current = false;
    setListening(false);
    clearTimeout(waitTimer.current);
    try { rec.current?.stop(); } catch { /* already stopped */ }
    rec.current = null;
  }, []);

  const start = useCallback(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR || !detector.current) return;
    const r = new SR();
    r.continuous = true;
    r.interimResults = true;
    r.lang = "en-US";
    r.maxAlternatives = 1;
    r.onresult = (e: any) => {
      let finals = "", interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) {
          finals += res[0].transcript;
          onSpeech(res[0].transcript, true);
        } else {
          interim += res[0].transcript;
        }
      }
      setHearing({ final: finals.trim(), interim: interim.trim() });
      if (interim.trim()) onSpeech(interim, false);
    };
    r.onerror = (e: any) => {
      if (e.error === "no-speech" || e.error === "aborted") return;
      if (/not-allowed|service-not-allowed/.test(e.error)) {
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
      if (listeningRef.current && rec.current === r) {
        try { r.start(); } catch { /* restarting too fast */ }
      }
    };
    rec.current = r;
    listeningRef.current = true;
    utterRefs.current = [];
    setNotice(null);
    setHearing({ final: "", interim: "" });
    setListening(true);
    try {
      r.start();
    } catch (e: any) {
      stop();
      setNotice(`Couldn't start listening: ${e.message || e}`);
    }
  }, [onSpeech, stop]);

  const toggleListening = useCallback(() => (listeningRef.current ? stop() : start()), [start, stop]);

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
    }
  }, [present]);

  // The operator picked a reference: show it, and make follow-ups relative to it.
  const pick = useCallback((index: number) => {
    const ref = historyRef.current[index];
    if (!ref) return;
    setShown(index);
    setHidden(false);
    detector.current?.focus(ref.label);
  }, []);

  const toggleHidden = useCallback(() => setHidden((h) => !h), []);

  return {
    status, statusNote, listening, hearing, history, shown, hidden, take, notice, typedMiss,
    toggleListening, check, pick, toggleHidden,
    current: shown >= 0 ? history[shown] : null,
    onSpeech, // exposed for automated tests
  };
}
