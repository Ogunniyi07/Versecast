// Loads the project's own scripture_refs.py into the browser with Pyodide.
// build_web.py copies scripture_refs.py and kjv.sqlite into public/.

export type Verse = [chapter: number, verse: number, text: string];

export type Ref = {
  label: string;     // "John 3:16", "Psalms 23:1-6"
  spoken: string;    // the words that matched
  after: number;     // words spoken after the reference (0 = still at the end)
  whole: boolean;    // a whole chapter
  verses: Verse[];
};

export type Detector = {
  preview: (text: string) => Ref[]; // live, stateless
  commit: (text: string) => Ref[];  // finished sentence (follow-ups resolve here)
  focus: (label: string) => void;   // operator picked a reference
};

const PYODIDE_VERSION = "0.26.4";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const PY_DIR = "/home/pyodide/vb";

type PyodideModule = { preview(t: string): string; commit(t: string): string; focus(l: string): string };
type Pyodide = {
  loadPackage(name: string): Promise<void>;
  FS: { mkdirTree(p: string): void; writeFile(p: string, d: Uint8Array): void };
  runPython(code: string): void;
  pyimport(name: string): PyodideModule;
};

declare global {
  interface Window {
    loadPyodide?: (opts: { indexURL: string }) => Promise<Pyodide>;
  }
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.loadPyodide) return resolve();
    const s = document.createElement("script");
    s.src = src;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Couldn't load Pyodide"));
    document.head.append(s);
  });
}

let loading: Promise<Detector> | null = null;

export function loadDetector(onStep?: (note: string, done: number) => void): Promise<Detector> {
  if (loading) return loading;
  loading = (async () => {
    onStep?.("Loading…", 0.03);
    await loadScript(`${PYODIDE_URL}pyodide.js`);
    onStep?.("Loading…", 0.15);
    const py = await window.loadPyodide!({ indexURL: PYODIDE_URL });
    onStep?.("Loading…", 0.45);
    await py.loadPackage("sqlite3");
    onStep?.("Loading the KJV…", 0.55);
    py.FS.mkdirTree(PY_DIR);
    for (const name of ["scripture_refs.py", "detect.py", "kjv.sqlite"]) {
      const res = await fetch(`/${name}`, { cache: "no-cache" });
      if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
      py.FS.writeFile(`${PY_DIR}/${name}`, new Uint8Array(await res.arrayBuffer()));
      onStep?.("Loading the KJV…", name === "kjv.sqlite" ? 0.8 : 0.6);
    }
    onStep?.("Getting ready…", 0.85);
    await new Promise((r) => setTimeout(r, 60));
    py.runPython(`import sys; sys.path.insert(0, "${PY_DIR}")\nimport detect`);
    const mod = py.pyimport("detect");
    return {
      preview: (t) => JSON.parse(mod.preview(t)) as Ref[],
      commit: (t) => JSON.parse(mod.commit(t)) as Ref[],
      focus: (l) => void mod.focus(l),
    };
  })();
  loading.catch(() => (loading = null));
  return loading;
}
