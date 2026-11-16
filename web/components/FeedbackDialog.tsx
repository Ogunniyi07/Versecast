"use client";
import { useEffect, useRef, useState } from "react";
import type { Ref } from "@/lib/detector";
import type { Take } from "@/lib/useVerseCast";


const VERDICTS: [string, string][] = [
  ["correct", "✓ Right verse"],
  ["wrong-verse", "✗ Wrong verse"],
  ["missed", "Missed it"],
  ["false-alarm", "Showed something I didn't say"],
  ["misheard", "Misheard my words"],
  ["other", "Something else"],
];

type Props = { open: boolean; onClose: () => void; take: Take | null; history: Ref[]; shown: number; accent: string };

export function FeedbackDialog({ open, onClose, take, history, shown, accent }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) { setState("idle"); d.showModal(); }
    if (!open && d.open) d.close();
  }, [open]);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const body = new URLSearchParams({
      "form-name": "feedback",
      tester: String(f.get("tester") || "").trim(),
      verdict: String(f.get("verdict") || ""),
      heard: take?.text || "",
      detected: history.map((r, i) => (i === shown ? `[${r.label}]` : r.label)).join("; ") || "(none)",
      expected: String(f.get("expected") || "").trim(),
      comment: String(f.get("comment") || "").trim(),
      input_mode: take?.mode || "",
      accent,
      browser: navigator.userAgent,
    });
    try { localStorage.setItem("vb-tester", body.get("tester") || ""); } catch { /* storage blocked */ }
    setState("sending");
    try {
      const res = await fetch("/__forms.html", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setState("sent");
    } catch (err) {
      setError((err as Error).message);
      setState("error");
    }
  }

  let savedName = "";
  try { savedName = typeof window !== "undefined" ? localStorage.getItem("vb-tester") || "" : ""; } catch { /* storage blocked */ }

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className="w-[min(560px,calc(100vw-32px))] rounded-3xl p-0 text-navy backdrop:bg-navy/40"
    >
      {state === "sent" ? (
        <div className="p-8">
          <h2 className="text-2xl font-bold">Thank you!</h2>
          <p className="mt-2 text-muted">Your feedback was sent.</p>
          <button onClick={onClose} className="mt-6 h-12 rounded-xl bg-navy px-8 font-semibold text-white">Close</button>
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-5 p-8">
          <div>
            <h2 className="text-2xl font-bold">Send feedback</h2>
            <p className="mt-1 text-sm text-muted">
              {take ? <>About: <span className="text-navy">“{take.text}”</span></> : "Tell us how VerseCast is working for you."}
            </p>
          </div>
          <fieldset className="flex flex-wrap gap-2">
            <legend className="mb-2 font-semibold">How did it do?</legend>
            {VERDICTS.map(([value, label], i) => (
              <label key={value} className="cursor-pointer">
                <input type="radio" name="verdict" value={value} required={i === 0} className="peer sr-only" />
                <span className="inline-block rounded-full border border-line px-4 py-1.5 text-sm peer-checked:border-brand peer-checked:bg-brand peer-checked:text-white peer-focus-visible:ring-2 peer-focus-visible:ring-brand/40">
                  {label}
                </span>
              </label>
            ))}
          </fieldset>
          <label className="flex flex-col gap-1.5 text-sm font-semibold">
            What did you say, or what should it have shown?
            <input name="expected" placeholder="e.g. I said Psalm 91 verse 1" className="h-12 rounded-xl border border-line px-4 font-normal focus:border-navy focus:outline-none" />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-semibold">
            <span>Anything else? <span className="font-normal text-muted">(optional)</span></span>
            <textarea name="comment" rows={3} className="rounded-xl border border-line px-4 py-3 font-normal focus:border-navy focus:outline-none" />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-semibold">
            <span>Your name <span className="font-normal text-muted">(optional)</span></span>
            <input name="tester" defaultValue={savedName} autoComplete="name" className="h-12 rounded-xl border border-line px-4 font-normal focus:border-navy focus:outline-none" />
          </label>
          {state === "error" && <p className="text-sm text-brand-dark" role="alert">Couldn&apos;t send ({error}). Please try again.</p>}
          <div className="flex justify-end gap-3">
            <button type="button" onClick={onClose} className="h-12 rounded-xl border border-line px-6">Cancel</button>
            <button type="submit" disabled={state === "sending"} className="h-12 rounded-xl bg-navy px-8 font-semibold text-white disabled:opacity-60">
              {state === "sending" ? "Sending…" : "Send"}
            </button>
          </div>
        </form>
      )}
    </dialog>
  );
}
