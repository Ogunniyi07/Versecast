// Keeps the presentation window (/display/) in step with the main page.
// Both windows are on the same site in the same browser, so a BroadcastChannel is enough: no server involved.

import type { Ref } from "./detector";

export const CHANNEL = "versecast-display";

export type DisplayMessage =
  | { type: "state"; ref: Ref | null; hidden: boolean } // main -> display
  | { type: "hello" }                                     // display -> main: send me the current state
  | { type: "hello-display" }                             // main -> display: send me your scroll status
  | { type: "toggle-hidden" }                             // display -> main: H pressed on the display
  | { type: "step"; dir: 1 | -1 }                         // display -> main: arrow key pressed on the display
  | { type: "scroll"; action: ScrollAction }              // main -> display: auto-scroll control
  | { type: "scroll-status"; status: ScrollStatus };      // display -> main: what auto-scroll is doing

export type ScrollAction = "toggle" | "slower" | "faster" | "restart";

export type ScrollStatus = {
  active: boolean;  // the passage is longer than the screen, so it auto-scrolls
  paused: boolean;
  done: boolean;  
  speed: number;
};

export function openChannel(onMessage: (m: DisplayMessage) => void): BroadcastChannel | null {
  if (typeof BroadcastChannel === "undefined") return null;
  const ch = new BroadcastChannel(CHANNEL);
  ch.onmessage = (e) => onMessage(e.data as DisplayMessage);
  return ch;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
// Open the display window, then move it to a second screen if the browser can
// tell us about one (Window Management API, Chrome/Edge; asks permission
// once). The window opens first because browsers block pop-ups that open after
// a wait such as a permission prompt.
export function openDisplayWindow(): Window | null {
  const win = window.open("/display/", "versecast-display", "popup,width=1280,height=720");
  if (win && "getScreenDetails" in window) {
    (window as any).getScreenDetails().then((details: any) => {
      const external = details.screens.find((s: any) => s !== details.currentScreen);
      if (!external) return;
      win.moveTo(external.availLeft, external.availTop);
      win.resizeTo(external.availWidth, external.availHeight);
    }).catch(() => { /* permission refused: drag the window across instead */ });
  }
  win?.focus();
  return win;
}
