import { useEffect, useRef } from "react";
import { displayLabel } from "@/lib/format";
import { downloadTranscript, punctuate, type Entry } from "@/lib/transcript";
import { track } from "@/lib/analytics";

const SHOW_MAX = 400; // lines on the page; the download has everything

type Props = {
  entries: Entry[];
  interim: string;      // words still being spoken
  listening: boolean;
  onClear: () => void;
  onShowVerse: (label: string) => void;
  current: string | null; // label on screen
};

export function Transcript({ entries, interim, listening, onClear, onShowVerse, current }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true); // follow new words unless the reader scrolled up

  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [entries, interim]);

  if (!listening && !entries.length) return null;
  const shown = entries.slice(-SHOW_MAX);
  const verses = entries.filter((e) => e.kind === "verse").length;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-bold uppercase tracking-wider text-muted">
          {listening ? "Hearing" : "Transcript"}
        </span>
        {!listening && entries.length > 0 && (
          <div className="flex items-center gap-4 text-sm font-semibold">
            <button
              type="button"
              onClick={() => {
                if (window.confirm("Clear the transcript? Download it first if you want to keep it.")) onClear();
              }}
              className="text-muted underline-offset-4 hover:text-navy hover:underline"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={() => { track("transcript-download"); downloadTranscript(entries); }}
              className="flex items-center gap-1.5 rounded-lg border border-navy px-3 py-1.5 text-navy hover:bg-slate-50"
            >
              <svg viewBox="0 0 24 24" className="size-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 3v12M7 10l5 5 5-5M5 21h14" />
              </svg>
              Download transcript
            </button>
          </div>
        )}
      </div>
      <div
        ref={box}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
        className="max-h-56 overflow-y-auto rounded-xl bg-slate-50 px-4 py-3 leading-relaxed text-navy"
        aria-live="polite"
        aria-label="Transcript"
      >
        {entries.length > SHOW_MAX && (
          <p className="mb-2 text-sm text-muted">Earlier lines are in the download.</p>
        )}
        {shown.map((e, i) =>
          e.kind === "speech" ? (
            <span key={i}>{punctuate(e.text)} </span>
          ) : e.kind === "verse" ? (
            <span key={i}>
              <button
                type="button"
                onClick={() => onShowVerse(e.label)}
                title={`Show ${displayLabel(e.label)} on screen`}
                aria-pressed={e.label === current}
                className={[
                  "inline-block rounded-full px-2 py-px align-[1px] text-xs font-bold transition",
                  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
                  e.label === current
                    ? "bg-brand text-white ring-2 ring-navy ring-offset-1"
                    : "bg-brand text-white hover:bg-brand-dark",
                ].join(" ")}
              >
                {displayLabel(e.label)}
              </button>{" "}
            </span>
          ) : i > 0 ? (
            <span key={i} className="my-1 block text-xs text-muted">
              {e.kind === "start" ? "Listening again" : "Stopped"}
            </span>
          ) : null,
        )}
        {interim && <span className="text-muted">{interim}</span>}
        {listening && !interim && !shown.some((e) => e.kind === "speech") && <span className="text-muted">…</span>}
      </div>
      {!listening && entries.length > 0 && (
        <p className="text-sm text-muted">
          {verses} {verses === 1 ? "verse" : "verses"} shown. The transcript stays in this browser until you clear it.
        </p>
      )}
    </div>
  );
}
