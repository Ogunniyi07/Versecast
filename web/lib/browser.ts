// Which browsers can actually listen.
export const VOICE_UNSUPPORTED =
  "Voice isn't supported in this browser. Try Safari on iPhone, or Chrome on Android or a laptop. You can still type below.";

// On iPhone and iPad only Safari can listen. Chrome, Firefox, Edge and Opera there have the speech API but it never starts.
export function isIOSNonSafari(ua = navigator.userAgent): boolean {
  const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  return ios && /CriOS|FxiOS|EdgiOS|OPiOS|GSA\//.test(ua);
}

// A tip to show before they tap, or null.
export function voiceTip(): string | null {
  if (typeof navigator === "undefined") return null;
  if (isIOSNonSafari()) {
    const name = /CriOS/.test(navigator.userAgent) ? "Chrome" : "this browser";
    return `Voice doesn't work in ${name} on iPhone. Open this page in Safari to speak. You can still type below.`;
  }
  return null;
}

// Waiting on the mic permission prompt doesn't count as failing to start.
export async function micPrompting(): Promise<boolean> {
  try {
    const p = await navigator.permissions.query({ name: "microphone" as PermissionName });
    return p.state === "prompt";
  } catch {
    return false; // can't tell (older Safari)
  }
}

// Can this browser listen at all? (Checked without loading anything.)
export function canListen(): boolean {
  if (typeof window === "undefined") return true;
  const w = window as Window & { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown };
  const SR = w.SpeechRecognition || w.webkitSpeechRecognition;
  return !!SR && !isIOSNonSafari();
}
