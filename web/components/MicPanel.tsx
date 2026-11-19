import { useEffect, useRef, useState } from "react";
import { ACCENTS } from "@/lib/accents";
import { VOICE_UNSUPPORTED, canListen } from "@/lib/browser";
import type { Status } from "@/lib/useVerseCast";
import type { Entry } from "@/lib/transcript";
import { Transcript } from "./Transcript";

type Props = {
  status: Status;
  statusNote: string;
  loadDone: number;
  slowLoad: boolean;
  listening: boolean;
  starting: boolean;
  tip: string | null;
  hearing: { final: string; interim: string };
  notice: string | null;
  onToggle: () => void;
  accent: string;
  onAccent: (code: string) => void;
  transcript: Entry[];
  onClearTranscript: () => void;
  onShowVerse: (label: string) => void;
  current: string | null;
};

export function MicPanel({ status, statusNote, loadDone, slowLoad, listening, starting, tip, hearing, notice, onToggle, accent, onAccent, transcript, onClearTranscript, onShowVerse, current }: Props) {
  const ready = status === "ready";
  const water = useWater(loadDone, status === "loading");
  const label =
    status === "loading" && slowLoad ? (canListen() ? "Taking longer than usual" : "Voice isn't supported here")
    : status === "loading" ? statusNote
    : status === "error" ? "Couldn't load"
    : status === "unsupported" ? "Listening isn't available here"
    : starting ? "Starting…"
    : listening ? "Listening… tap to stop" : "Start listening";
  const sub =
    status === "loading" && slowLoad ? (canListen() ? "Your connection may be slow. VerseCast will be ready as soon as it finishes loading." : VOICE_UNSUPPORTED)
    : status === "error" ? statusNote
    : status === "unsupported" ? VOICE_UNSUPPORTED
    : starting ? "Waiting for the speech engine."
    : listening ? "Say a Bible reference." : "Tap once, then keep speaking.";

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between sm:gap-8">
        <div className="flex items-center gap-6 sm:gap-8">
          <button
            type="button"
            onClick={onToggle}
            disabled={!ready}
            aria-label={listening ? "Stop listening" : "Start listening"}
            aria-pressed={listening}
            aria-busy={status === "loading"}
            className={[
              "grid size-20 shrink-0 place-items-center rounded-full text-white transition sm:size-24",
              "focus-visible:outline focus-visible:outline-4 focus-visible:outline-offset-4 focus-visible:outline-brand/40",
              ready ? "bg-brand hover:bg-brand-dark active:scale-95" : "bg-brand/40 cursor-default",
              listening ? "animate-[ring_1.4s_ease-out_infinite]" : "",
              water.show ? "relative overflow-hidden" : "",
            ].join(" ")}
          >
            {water.show && <Water level={water.level} />}
            {listening ? (
              <svg viewBox="0 0 24 24" className="relative size-8" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" className="relative size-9" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
              </svg>
            )}
          </button>
          <div className="min-w-0">
            <p className="text-xl font-bold sm:text-2xl">{label}</p>
            <p className="mt-1 text-muted sm:text-lg">{sub}</p>
            {status !== "unsupported" && status !== "error" && (
              <p className="mt-1 text-sm text-muted">Works best in Chrome, with the mic close to the speaker.</p>
            )}
          </div>
        </div>
        {status !== "unsupported" && (
          <label className="flex shrink-0 flex-col gap-1.5 sm:w-60">
            <span className="text-sm font-semibold text-navy">Speaker&apos;s accent</span>
            <span className="relative">
              <select
                value={accent}
                onChange={(e) => onAccent(e.target.value)}
                className="h-12 w-full appearance-none rounded-xl border border-line bg-white pl-4 pr-11 text-navy focus:border-navy focus:outline-none"
              >
                {ACCENTS.map((a) => <option key={a.code} value={a.code}>{a.label}</option>)}
              </select>
              <svg viewBox="0 0 24 24" className="pointer-events-none absolute right-4 top-1/2 size-4 -translate-y-1/2 text-navy" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="m6 9 6 6 6-6" />
              </svg>
            </span>
          </label>
        )}
      </div>
      <Transcript entries={transcript} interim={hearing.interim} listening={listening} onClear={onClearTranscript}
        onShowVerse={onShowVerse} current={current} />
      {tip && !notice && <p className="rounded-xl bg-orange-50 px-4 py-3 text-sm text-brand-dark">{tip}</p>}
      {notice && <p className="rounded-xl bg-orange-50 px-4 py-3 text-sm text-brand-dark" role="alert">{notice}</p>}
    </section>
  );
}

// Orange water that rises inside the mic button as the app loads.
function Water({ level }: { level: number }) {
  return (
    <span aria-hidden="true" className="absolute inset-x-0 bottom-0 bg-brand transition-[height] duration-700 ease-out"
      style={{ height: `${Math.round(level * 100)}%` }}>
      <svg viewBox="0 0 200 10" preserveAspectRatio="none"
        className="absolute bottom-full left-0 h-2 w-[200%] animate-[wave_1.6s_linear_infinite] fill-brand motion-reduce:animate-none">
        <path d="M0 5 Q25 0 50 5 T100 5 T150 5 T200 5 V10 H0 Z" />
      </svg>
    </span>
  );
}

function useWater(done: number, loading: boolean) {
  const [level, setLevel] = useState(0);
  const [show, setShow] = useState(loading);
  const start = useRef(0);
  useEffect(() => {
    if (!loading) {
      setLevel(1);
      const id = setTimeout(() => setShow(false), 600);
      return () => clearTimeout(id);
    }
    setShow(true);
    start.current ||= Date.now();
    const tick = () => setLevel((l) => Math.max(l, done, 0.95 * (1 - Math.exp(-(Date.now() - start.current) / 4500))));
    tick();
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [done, loading]);
  return { level, show };
}
