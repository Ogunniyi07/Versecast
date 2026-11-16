import type { Ref } from "@/lib/detector";

type Props = {
  history: Ref[];
  shown: number;
  hidden: boolean;
  typedMiss: boolean;
  onPick: (i: number) => void;
  onToggleHidden: () => void;
};

// "Psalms 23:1-6" -> "Psalm 23:1-6" for display (KJV book name is Psalms).
const display = (label: string) => label.replace(/^Psalms (\d+)(?!.*-\d+:)/, "Psalm $1");

export function Screen({ history, shown, hidden, typedMiss, onPick, onToggleHidden }: Props) {
  const ref = shown >= 0 ? history[shown] : null;
  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-bold text-muted">On screen</h2>
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
    </section>
  );
}
