import type { Ref } from "@/lib/detector";
import type { ScrollAction, ScrollStatus } from "@/lib/display";
import { displayLabel as display } from "@/lib/format";

type Props = {
  history: Ref[];
  shown: number;
  hidden: boolean;
  typedMiss: boolean;
  onPick: (i: number) => void;
  onToggleHidden: () => void;
  onOpenDisplay: () => void;
  onStep: (dir: 1 | -1) => void;
  scroll: ScrollStatus | null;          // the display window's auto-scroll, if open
  onScroll: (action: ScrollAction) => void;
  onReport: () => void;
};

export function Screen({ history, shown, hidden, typedMiss, onPick, onToggleHidden, onOpenDisplay, onStep, scroll, onScroll, onReport }: Props) {
  const ref = shown >= 0 ? history[shown] : null;
  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-bold text-muted">On screen</h2>
        <div className="flex flex-wrap justify-end gap-2">
        <ArrowButton dir={-1} disabled={!ref} onClick={() => onStep(-1)} />
        <ArrowButton dir={1} disabled={!ref} onClick={() => onStep(1)} />
        <button
          type="button"
          onClick={onOpenDisplay}
          title="Show only the verse in its own window, for a projector or second screen"
          className="flex items-center gap-2 rounded-xl border border-navy px-4 py-2 hover:bg-slate-50"
        >
          <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="2" y="4" width="20" height="13" rx="2" /><path d="M8 21h8M12 17v4" />
          </svg>
          Open display
        </button>
        <button
          type="button"
          onClick={onToggleHidden}
          disabled={!ref}
          title="Shortcut: H or Esc"
          className="flex items-center gap-2 rounded-xl border border-navy px-4 py-2 hover:bg-slate-50 disabled:border-line disabled:text-muted"
        >
          {hidden ? "Show verse" : "Hide verse"}
          <kbd className="rounded border border-current px-1.5 text-xs leading-5">H</kbd>
        </button>
        </div>
      </div>

      {scroll?.active && ref && !hidden && (
        <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-slate-50 px-4 py-3 text-sm" aria-label="Display auto-scroll">
          <span className="mr-1 font-semibold">
            Display is {scroll.done ? "at the end" : scroll.paused ? "paused" : "scrolling"}
            <span className="ml-1 font-normal text-muted">· speed {scroll.speed}×</span>
          </span>
          <div className="ml-auto flex flex-wrap gap-2">
            {!scroll.done && (
              <ScrollButton onClick={() => onScroll("toggle")} keyHint="P">{scroll.paused ? "Resume" : "Pause"}</ScrollButton>
            )}
            <ScrollButton onClick={() => onScroll("slower")} keyHint="−">Slower</ScrollButton>
            <ScrollButton onClick={() => onScroll("faster")} keyHint="+">Faster</ScrollButton>
            <ScrollButton onClick={() => onScroll("restart")}>Restart</ScrollButton>
          </div>
        </div>
      )}

      {history.length > 1 && (
        <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label="Recent references">
          <span className="mr-1 text-sm text-muted">Recent</span>
          {history.map((r, i) => (
            <button
              key={r.label}
              type="button"
              role="radio"
              aria-checked={i === shown}
              onClick={() => onPick(i)}
              className={[
                "flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm",
                i === shown ? "border-brand bg-brand text-white" : "border-line hover:border-navy",
              ].join(" ")}
            >
              <kbd className="rounded border border-current px-1 text-[11px] leading-4 opacity-80">{i + 1}</kbd>
              {display(r.label)}
            </button>
          ))}
        </div>
      )}

      <div className="max-h-[70vh] min-h-[220px] overflow-y-auto rounded-3xl bg-navy px-7 py-10 text-white sm:px-12 sm:py-14">
        {!ref ? (
          <p className="text-lg text-white/60">
            {typedMiss ? "No verse found in that. The screen would stay as it was." : "Verses you say will appear here."}
          </p>
        ) : hidden ? (
          <p className="text-lg text-white/50">Verse hidden. Press H to show it again.</p>
        ) : (
          <>
            <div className="space-y-4 font-serif text-[26px] leading-[1.5] sm:text-[32px]">
              {ref.verses.map(([ch, v, text]) => (
                <p key={`${ch}:${v}`}>
                  {ref.verses.length > 1 && (
                    <sup className="mr-1.5 font-sans text-sm font-bold text-brand">{v}</sup>
                  )}
                  {text}
                </p>
              ))}
            </div>
            <p className="mt-8 font-bold text-brand sm:text-lg">{display(ref.label)} · KJV</p>
          </>
        )}
      </div>
      {ref && !hidden && (
        <button
          type="button"
          onClick={onReport}
          className="flex items-center gap-1.5 self-end text-sm font-semibold text-muted underline-offset-4 hover:text-brand hover:underline"
        >
          <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 22V4a1 1 0 0 1 1-1h11l-2 4 2 4H5" />
          </svg>
          Wrong verse? Tell us
        </button>
      )}
    </section>
  );
}

function ScrollButton({ onClick, keyHint, children }: { onClick: () => void; keyHint?: string; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-1.5 hover:border-navy">
      {children}
      {keyHint && <kbd className="rounded border border-current px-1 text-[11px] leading-4 text-muted">{keyHint}</kbd>}
    </button>
  );
}

function ArrowButton({ dir, disabled, onClick }: { dir: 1 | -1; disabled: boolean; onClick: () => void }) {
  const label = dir > 0 ? "Next verse" : "Previous verse";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={`${label} (${dir > 0 ? "→" : "←"} key)`}
      className="grid size-[42px] place-items-center rounded-xl border border-navy hover:bg-slate-50 disabled:border-line disabled:text-muted"
    >
      <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {dir > 0 ? <path d="M5 12h14M13 6l6 6-6 6" /> : <path d="M19 12H5M11 6l-6 6 6 6" />}
      </svg>
    </button>
  );
}
