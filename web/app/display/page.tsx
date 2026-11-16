"use client";

// Presentation view: only the verse, full screen, for a projector or second
// screen. Opened from the main page ("Open display") and kept in step with it
// over a BroadcastChannel. Keys: F = full screen, H = hide/show (synced back),
// ← / → = previous / next verse, P = pause/resume auto-scroll,
// - / + = slower / faster.
//
// A passage longer than the screen scrolls slowly on its own: it waits
// START_DELAY_MS so people can start reading, moves about one line every
// SECONDS_PER_LINE seconds, and stops at the end.

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Ref } from "@/lib/detector";
import { openChannel, type DisplayMessage, type ScrollAction, type ScrollStatus } from "@/lib/display";
import { displayLabel } from "@/lib/format";

const MAX_FONT = 160;
const MIN_FONT = 40;
const LINE_HEIGHT = 1.35;
const START_DELAY_MS = 3000;
const SECONDS_PER_LINE = 2.5;
const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3];

export default function Display() {
  const [ref, setRef] = useState<Ref | null>(null);
  const [hidden, setHidden] = useState(false);
  const [connected, setConnected] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [idle, setIdle] = useState(false);
  const [font, setFont] = useState(MAX_FONT);
  const channel = useRef<BroadcastChannel | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const [scroll, setScroll] = useState<ScrollStatus>({ active: false, paused: false, done: false, speed: 1 });
  const scrollRef = useRef(scroll);
  scrollRef.current = scroll;
  const [startedAt, setStartedAt] = useState(0); // when the current passage appeared

  // Auto-scroll
  const report = (st: ScrollStatus) =>
    channel.current?.postMessage({ type: "scroll-status", status: st } satisfies DisplayMessage);

  const scrollAction = (action: ScrollAction) => {
    setScroll((st) => {
      let next = st;
      if (action === "toggle") next = { ...st, paused: !st.paused };
      if (action === "slower" || action === "faster") {
        const i = SPEEDS.indexOf(st.speed);
        const j = Math.max(0, Math.min(SPEEDS.length - 1, i + (action === "faster" ? 1 : -1)));
        next = { ...st, speed: SPEEDS[j] };
      }
      if (action === "restart") {
        box.current?.scrollTo({ top: 0 });
        setStartedAt(performance.now());
        next = { ...st, paused: false, done: false };
      }
      return next;
    });
  };

  // Sync
  useEffect(() => {
    document.title = "VerseCast Display";
    const ch = openChannel((m: DisplayMessage) => {
      if (m.type === "state") {
        setRef(m.ref);
        setHidden(m.hidden);
        setConnected(true);
      } else if (m.type === "scroll") {
        scrollAction(m.action);
      } else if (m.type === "hello-display") {
        report(scrollRef.current);
      }
    });
    channel.current = ch;
    ch?.postMessage({ type: "hello" } satisfies DisplayMessage);
    // Closing the display: the main page should drop its scroll controls.
    const bye = () => ch?.postMessage({ type: "scroll-status", status: { active: false, paused: false, done: false, speed: 1 } } satisfies DisplayMessage);
    window.addEventListener("pagehide", bye);
    return () => { window.removeEventListener("pagehide", bye); ch?.close(); };
  }, []);

  // Fit text to the screen
  const fit = useCallback(() => {
    const b = box.current, c = content.current;
    if (!b || !c) return;
    const pad = getComputedStyle(b);
    const room = b.clientHeight - parseFloat(pad.paddingTop) - parseFloat(pad.paddingBottom);
    let lo = MIN_FONT, hi = MAX_FONT;
    c.style.fontSize = `${hi}px`;
    if (c.scrollHeight <= room) return setFont(hi);
    while (hi - lo > 1) {
      const mid = Math.floor((lo + hi) / 2);
      c.style.fontSize = `${mid}px`;
      if (c.scrollHeight <= room) lo = mid; else hi = mid;
    }
    c.style.fontSize = `${lo}px`;
    setFont(lo);
  }, []);

  useLayoutEffect(() => {
    fit();
    box.current?.scrollTo({ top: 0 });
    const b = box.current;
    const active = Boolean(b && b.scrollHeight > b.clientHeight + 2);
    setStartedAt(performance.now());
    setScroll((st) => ({ ...st, active, paused: false, done: false }));
  }, [ref, hidden, fit]);

  // Tell the main page, so it can show the scroll controls.
  useEffect(() => { report(scroll); }, [scroll]);

  // The scrolling itself: a steady glide, frame by frame.
  useEffect(() => {
    if (!scroll.active || scroll.paused || scroll.done) return;
    const b = box.current;
    if (!b) return;
    let pos = b.scrollTop;
    let last = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      if (now - startedAt >= START_DELAY_MS) {
        if (Math.abs(b.scrollTop - pos) > 2) pos = b.scrollTop; // someone scrolled by hand
        pos += ((font * LINE_HEIGHT) / SECONDS_PER_LINE) * scroll.speed * dt;
        b.scrollTop = pos;
        if (b.scrollTop + b.clientHeight >= b.scrollHeight - 1) {
          setScroll((st) => ({ ...st, done: true }));
          return;
        }
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [scroll.active, scroll.paused, scroll.done, scroll.speed, font, startedAt]);
  useEffect(() => {
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [fit]);

  // Full screen, keys, cursor
  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen().catch(() => {});
  }, []);

  useEffect(() => {
    const onFs = () => setFullscreen(Boolean(document.fullscreenElement));
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "f" || e.key === "F") toggleFullscreen();
      else if (e.key === "h" || e.key === "H") channel.current?.postMessage({ type: "toggle-hidden" } satisfies DisplayMessage);
      else if (e.key === "ArrowRight") channel.current?.postMessage({ type: "step", dir: 1 } satisfies DisplayMessage);
      else if (e.key === "ArrowLeft") channel.current?.postMessage({ type: "step", dir: -1 } satisfies DisplayMessage);
      else if (e.key === "p" || e.key === "P") scrollAction("toggle");
      else if (e.key === "-" || e.key === "_") scrollAction("slower");
      else if (e.key === "+" || e.key === "=") scrollAction("faster");
    };
    let timer: ReturnType<typeof setTimeout>;
    const onMove = () => {
      setIdle(false);
      clearTimeout(timer);
      timer = setTimeout(() => setIdle(true), 2500);
    };
    onMove();
    document.addEventListener("fullscreenchange", onFs);
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousemove", onMove);
    return () => {
      document.removeEventListener("fullscreenchange", onFs);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousemove", onMove);
      clearTimeout(timer);
    };
  }, [toggleFullscreen]);

  const showVerse = ref && !hidden;

  return (
    <main
      onDoubleClick={toggleFullscreen}
      className={`fixed inset-0 flex flex-col bg-navy text-white ${idle ? "cursor-none" : ""}`}
    >
      <div ref={box} className="flex flex-1 flex-col overflow-y-auto px-[4vw] py-[4vh]">
        <div ref={content} className="my-auto w-full" style={{ fontSize: font }}>
          {showVerse && (
            <>
              <div className="space-y-[0.8em] font-serif" style={{ lineHeight: LINE_HEIGHT }}>
                {ref.verses.map(([ch, v, text]) => (
                  <p key={`${ch}:${v}`}>
                    {ref.verses.length > 1 && (
                      <sup className="mr-[0.25em] font-sans text-[0.45em] font-bold text-brand">{v}</sup>
                    )}
                    {text}
                  </p>
                ))}
              </div>
              <p className="mt-[0.7em] font-sans text-[0.5em] font-bold text-brand">
                {displayLabel(ref.label)} · KJV
              </p>
            </>
          )}
        </div>
      </div>
      {!fullscreen && (
        <div className={`absolute bottom-4 right-4 flex items-center gap-3 rounded-xl bg-white/10 px-4 py-2 text-sm text-white/80 transition-opacity ${idle ? "opacity-0" : "opacity-100"}`}>
          {!connected && <span>Waiting for the VerseCast page…</span>}
          {connected && !ref && <span>Ready. Verses will appear here.</span>}
          <button onClick={toggleFullscreen} className="rounded-lg bg-white/15 px-3 py-1 font-semibold text-white hover:bg-white/25">
            Full screen <kbd className="ml-1 rounded border border-white/40 px-1 text-xs">F</kbd>
          </button>
        </div>
      )}
    </main>
  );
}
