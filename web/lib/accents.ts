// Accents offered for speech recognition. The browser's speech service
// (Google in Chrome, Microsoft in Edge, Apple in Safari) uses a model tuned to the accent
// chosen here, which matters a lot for how many words come out right.
export const ACCENTS = [
  { code: "en-NG", label: "Nigerian English" },
  { code: "en-GH", label: "Ghanaian English" },
  { code: "en-KE", label: "Kenyan English" },
  { code: "en-ZA", label: "South African English" },
  { code: "en-GB", label: "British English" },
  { code: "en-US", label: "American English" },
  { code: "en-IN", label: "Indian English" },
] as const;

export const DEFAULT_ACCENT = "en-NG";
export const FALLBACK_ACCENT = "en-US"; // supported by every browser speech service

export const accentLabel = (code: string) => ACCENTS.find((a) => a.code === code)?.label ?? code;
