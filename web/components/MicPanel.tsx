import { ACCENTS } from "@/lib/accents";
import type { Status } from "@/lib/useVerseCast";

type Props = {
  status: Status;
  statusNote: string;
  listening: boolean;
  hearing: { final: string; interim: string };
  notice: string | null;
  onToggle: () => void;
  accent: string;
  onAccent: (code: string) => void;
};

export function MicPanel({ status, statusNote, listening, hearing, notice, onToggle, accent, onAccent }: Props) {
  const ready = status === "ready";
  const label =
    status === "loading" ? statusNote
    : status === "error" ? "Couldn't load"
    : status === "unsupported" ? "Listening isn't available here"
    : listening ? "Listening… tap to stop" : "Start listening";
  const sub =
    status === "error" ? statusNote
    : status === "unsupported" ? "Open this page in Chrome, Edge or Safari to speak. You can still type below."
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
            className={[
              "grid size-20 shrink-0 place-items-center rounded-full text-white transition sm:size-24",
              "focus-visible:outline focus-visible:outline-4 focus-visible:outline-offset-4 focus-visible:outline-brand/40",
              ready ? "bg-brand hover:bg-brand-dark active:scale-95" : "bg-brand/40 cursor-default",
              listening ? "animate-[ring_1.4s_ease-out_infinite]" : "",
            ].join(" ")}
          >
            {listening ? (
              <svg viewBox="0 0 24 24" className="size-8" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" className="size-9" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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
      {listening && (
        <p className="min-h-[1.5em] rounded-xl bg-slate-50 px-4 py-3 text-navy" aria-live="polite">
          <span className="mr-2 text-xs font-bold uppercase tracking-wider text-muted">Hearing</span>
          {hearing.final} <span className="text-muted">{hearing.interim}</span>
          {!hearing.final && !hearing.interim && <span className="text-muted">…</span>}
        </p>
      )}
      {notice && <p className="rounded-xl bg-orange-50 px-4 py-3 text-sm text-brand-dark" role="alert">{notice}</p>}
    </section>
  );
}
