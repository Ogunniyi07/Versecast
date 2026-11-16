"use client";

import { useEffect, useState } from "react";
import { FeedbackDialog } from "@/components/FeedbackDialog";
import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { MicPanel } from "@/components/MicPanel";
import { Screen } from "@/components/Screen";
import { TypeForm } from "@/components/TypeForm";
import { useVerseCast } from "@/lib/useVerseCast";

export default function Home() {
  const vc = useVerseCast();
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const { toggleHidden, pick } = vc;

  // H / Esc hides the verse; 1-9 picks a recent reference.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input, textarea, dialog")) return;
      if (e.key === "h" || e.key === "H" || e.key === "Escape") toggleHidden();
      else if (/^[1-9]$/.test(e.key)) pick(Number(e.key) - 1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [toggleHidden, pick]);

  // Hook for automated tests (simulates speech events).
  useEffect(() => {
    (window as unknown as { __vbTest: unknown }).__vbTest = { onSpeech: vc.onSpeech };
  }, [vc.onSpeech]);

  return (
    <main className="mx-auto flex min-h-screen max-w-[960px] flex-col gap-10 px-4 py-8 sm:gap-12 sm:px-8 sm:py-10">
      <Header />

      <section>
        <h1 className="text-[34px] font-bold leading-[1.15] tracking-tight sm:text-5xl">
          Say a Bible reference.<br />The verse appears on screen.
        </h1>
        <p className="mt-4 text-lg text-muted">Verses show as soon as they are spoken.</p>
      </section>

      <MicPanel
        status={vc.status}
        statusNote={vc.statusNote}
        listening={vc.listening}
        hearing={vc.hearing}
        notice={vc.notice}
        onToggle={vc.toggleListening}
      />

      <TypeForm disabled={vc.status === "loading" || vc.status === "error"} onCheck={vc.check} />

      <Screen
        history={vc.history}
        shown={vc.shown}
        hidden={vc.hidden}
        typedMiss={vc.typedMiss}
        onPick={vc.pick}
        onToggleHidden={vc.toggleHidden}
      />

      <div className="mt-auto">
        <Footer onFeedback={() => setFeedbackOpen(true)} />
      </div>

      <FeedbackDialog
        open={feedbackOpen}
        onClose={() => setFeedbackOpen(false)}
        take={vc.take}
        history={vc.history}
        shown={vc.shown}
      />
    </main>
  );
}
