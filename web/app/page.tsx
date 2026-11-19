"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FeedbackDialog, type FeedbackSnapshot } from "@/components/FeedbackDialog";
import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { MicPanel } from "@/components/MicPanel";
import { Screen } from "@/components/Screen";
import { TypeForm } from "@/components/TypeForm";
import { track } from "@/lib/analytics";
import { openChannel, openDisplayWindow, type DisplayMessage, type ScrollAction, type ScrollStatus } from "@/lib/display";
import { useVerseCast } from "@/lib/useVerseCast";

export default function Home() {
  const vc = useVerseCast();
  // What the feedback dialog is about, frozen when it opens (listening carries on).
  const [feedback, setFeedback] = useState<FeedbackSnapshot | null>(null);
  const openFeedback = (kind: FeedbackSnapshot["kind"]) => {
    if (kind === "wrong-verse") track("wrong-verse-open");
    setFeedback({ kind, take: vc.take, history: [...vc.history], shown: vc.shown });
  };
  const { toggleHidden, pick, step, current, hidden } = vc;
  // Channel to the presentation window (/display/).
  const channel = useRef<BroadcastChannel | null>(null);
  const sendScroll = useCallback((action: ScrollAction) =>
    channel.current?.postMessage({ type: "scroll", action } satisfies DisplayMessage), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input, textarea, dialog")) return;
      if (e.key === "h" || e.key === "H" || e.key === "Escape") toggleHidden();
      else if (/^[1-9]$/.test(e.key)) pick(Number(e.key) - 1);
      else if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
      else if (e.key === "p" || e.key === "P") sendScroll("toggle");
      else if (e.key === "-" || e.key === "_") sendScroll("slower");
      else if (e.key === "+" || e.key === "=") sendScroll("faster");
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [toggleHidden, pick, step, sendScroll]);

  // Keep the presentation window showing what's on screen here.
  const [scrollStatus, setScrollStatus] = useState<ScrollStatus | null>(null);
  const screenState = useRef<DisplayMessage>({ type: "state", ref: null, hidden: false });
  screenState.current = { type: "state", ref: current, hidden };
  useEffect(() => {
    const ch = openChannel((m) => {
      if (m.type === "hello") ch?.postMessage(screenState.current);
      else if (m.type === "toggle-hidden") toggleHidden();
      else if (m.type === "step") step(m.dir);
      else if (m.type === "scroll-status") setScrollStatus(m.status);
    });
    channel.current = ch;
    ch?.postMessage({ type: "hello-display" } satisfies DisplayMessage); 
    return () => ch?.close();
  }, [toggleHidden, step]);
  useEffect(() => {
    channel.current?.postMessage({ type: "state", ref: current, hidden } satisfies DisplayMessage);
  }, [current, hidden]);

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
        loadDone={vc.loadDone}
        slowLoad={vc.slowLoad}
        listening={vc.listening}
        starting={vc.starting}
        tip={vc.tip}
        hearing={vc.hearing}
        notice={vc.notice}
        onToggle={vc.toggleListening}
        accent={vc.accent}
        onAccent={vc.setAccent}
        transcript={vc.transcript}
        onClearTranscript={vc.clearTranscript}
        onShowVerse={vc.showVerse}
        current={vc.hidden ? null : vc.current?.label ?? null}
      />

      <TypeForm disabled={vc.status === "loading" || vc.status === "error"} onCheck={vc.check} />

      <Screen
        history={vc.history}
        shown={vc.shown}
        hidden={vc.hidden}
        typedMiss={vc.typedMiss}
        onPick={vc.pick}
        onToggleHidden={vc.toggleHidden}
        onStep={vc.step}
        onOpenDisplay={() => { track("open-display"); openDisplayWindow(); }}
        scroll={scrollStatus}
        onScroll={sendScroll}
        onReport={() => openFeedback("wrong-verse")}
      />

      <div className="mt-auto">
        <Footer onFeedback={() => openFeedback("general")} />
      </div>

      <FeedbackDialog snapshot={feedback} onClose={() => setFeedback(null)} accent={vc.accent} />
    </main>
  );
}
