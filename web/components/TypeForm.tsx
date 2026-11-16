"use client";
import { useState } from "react";

const EXAMPLES = ["John 3:16", "Psalm 23", "Next verse", "Romans 8:28 to the end", "The Lord's Prayer"];

export function TypeForm({ disabled, onCheck }: { disabled: boolean; onCheck: (text: string) => void }) {
  const [text, setText] = useState("");
  return (
    <section className="flex flex-col gap-4">
      <form
        className="flex flex-col gap-3 sm:flex-row"
        onSubmit={(e) => { e.preventDefault(); onCheck(text); }}
      >
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={disabled}
          placeholder="Or type a reference, e.g. John 3:16"
          aria-label="Type a reference"
          autoComplete="off"
          className="h-14 w-full min-w-0 rounded-xl sm:flex-1 border border-line px-5 text-lg text-navy placeholder:text-muted/80 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/15 disabled:bg-slate-50"
        />
        <button
          type="submit"
          disabled={disabled}
          className="h-14 rounded-xl bg-navy px-10 text-lg font-semibold text-white hover:bg-navy-soft disabled:opacity-50"
        >
          Check
        </button>
      </form>
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="mr-1 text-muted">Try</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            disabled={disabled}
            onClick={() => { setText(ex); onCheck(ex); }}
            className="rounded-full border border-line px-5 py-2 text-[15px] hover:border-navy disabled:opacity-50"
          >
            {ex}
          </button>
        ))}
      </div>
    </section>
  );
}
