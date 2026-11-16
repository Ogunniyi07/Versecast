type GoatCounter = { count?: (o: { path: string; title?: string; event?: boolean }) => void };

export function track(event: string) {
  if (typeof window === "undefined") return;
  const gc = (window as unknown as { goatcounter?: GoatCounter }).goatcounter;
  try { gc?.count?.({ path: event, title: event, event: true }); } catch { /* not loaded */ }
}
