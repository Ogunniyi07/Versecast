// Versecast web app: live listening.
// Speech: the browser's built-in speech recognition (streams words as you
// speak; needs internet; Chrome, Edge, Safari).
// Detection: the project's own scripture_refs.py running in Pyodide.

const APP_VERSION = "web-0.3";
const PY_DIR = "/home/pyodide/vb";
const HISTORY_MAX = 9;            // references kept in the picker
const WAIT_VERSE_MS = 350;        // reference still at the end of speech: wait this long for a change
const WAIT_CHAPTER_MS = 1200;     // "John 3" at the end: "...verse 16" may be coming

const $ = (id) => document.getElementById(id);
const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;

const state = {
  py: null,            // { preview, commit, focus }
  take: null,          // what the feedback form describes
  history: [],         // recent references, newest last (the picker)
  shownLabel: null,
};
const live = {
  on: false,
  rec: null,
  utterRefs: [],       // labels the current sentence has put in the history
  waitTimer: null,
};

// =================================================================== loading
function setStep(status, note) {
  $("dot-bible").className = `dot ${status}`;
  if (note !== undefined) $("note-bible").textContent = note;
}

async function loadBible() {
  setStep("busy", "loading…");
  const py = await loadPyodide({ indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/" });
  await py.loadPackage("sqlite3");
  setStep("busy", "loading KJV…");
  py.FS.mkdirTree(PY_DIR);
  for (const name of ["scripture_refs.py", "detect.py", "kjv.sqlite"]) {
    const res = await fetch(name, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
    py.FS.writeFile(`${PY_DIR}/${name}`, new Uint8Array(await res.arrayBuffer()));
  }
  py.runPython(`import sys; sys.path.insert(0, "${PY_DIR}")\nimport detect`);
  const mod = py.pyimport("detect");
  state.py = {
    preview: (t) => JSON.parse(mod.preview(t)),
    commit: (t) => JSON.parse(mod.commit(t)),
    focus: (label) => mod.focus(label),
  };
  setStep("done", "ready");
}

async function boot() {
  $("version").textContent = APP_VERSION;
  try { $("tester").value = localStorage.getItem("vb-tester") || ""; } catch {}
  try {
    await loadBible();
    $("loading").classList.add("done");
    $("type-input").disabled = false;
    $("type-btn").disabled = false;
    if (SpeechRec) {
      $("mic").disabled = false;
      setIdleLabels();
    } else {
      $("mic-label").textContent = "Listening isn't available in this browser";
      $("mic-sub").textContent = "Open this page in Chrome, Edge or Safari to speak. You can still type a sentence below.";
    }
  } catch (e) {
    console.error(e);
    setStep("fail", "failed");
    $("mic-label").textContent = "Couldn't load";
    $("mic-sub").textContent = `${e.message || e}. Check your connection and reload the page.`;
  }
}

function setIdleLabels() {
  $("mic-label").textContent = "Start listening";
  $("mic-sub").textContent = "Tap once and keep talking. Verses appear as soon as you say them.";
}

// ================================================================ listening
function startListening() {
  live.on = true;
  live.utterRefs = [];
  $("mic").classList.add("recording");
  $("mic").setAttribute("aria-label", "Stop listening");
  $("mic-label").textContent = "Listening… tap to stop";
  $("mic-sub").textContent = "Say a Bible reference.";
  $("live").hidden = false;
  setLiveText("", "");
  try {
    startRecognition();
  } catch (e) {
    console.error(e);
    stopListening();
    $("mic-sub").textContent = micErrorText(e);
  }
}

function stopListening() {
  live.on = false;
  clearTimeout(live.waitTimer);
  if (live.rec) { try { live.rec.stop(); } catch {} live.rec = null; }
  $("mic").classList.remove("recording");
  $("mic").setAttribute("aria-label", "Start listening");
  setIdleLabels();
}

function micErrorText(e) {
  const name = (e && (e.name || e.error)) || "";
  if (/NotAllowed|not-allowed|Security|service-not-allowed/i.test(name)) return "Microphone blocked. Allow mic access in the address bar, or type a sentence below.";
  if (/network/i.test(name)) return "Listening needs an internet connection. Check your connection and try again.";
  return `Couldn't start listening: ${e.message || name || e}`;
}

function startRecognition() {
  const rec = new SpeechRec();
  rec.continuous = true;
  rec.interimResults = true;
  rec.lang = "en-US";
  rec.maxAlternatives = 1;
  rec.onresult = (e) => {
    let finals = "", interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) {
        finals += r[0].transcript;
        onSpeech(r[0].transcript, true);
      } else {
        interim += r[0].transcript;
      }
    }
    setLiveText(finals.trim(), interim.trim());
    if (interim.trim()) onSpeech(interim, false);
  };
  rec.onerror = (e) => {
    if (e.error === "no-speech" || e.error === "aborted") return;
    $("mic-sub").textContent = micErrorText(e);
    if (e.error === "not-allowed" || e.error === "service-not-allowed" || e.error === "network") stopListening();
  };
  // Browsers end recognition after a pause; keep listening until Stop.
  rec.onend = () => { if (live.on && live.rec === rec) try { rec.start(); } catch {} };
  live.rec = rec;
  rec.start();
}

function setLiveText(finalText, interim) {
  const p = $("live-text");
  p.replaceChildren(document.createTextNode(finalText ? finalText + " " : ""));
  if (interim) {
    const s = document.createElement("span");
    s.className = "interim";
    s.textContent = interim;
    p.append(s);
  }
}

// Called many times per sentence with the text so far, then once with
// final=true when the sentence ends.
function onSpeech(text, final) {
  clearTimeout(live.waitTimer);
  if (!text.trim()) return;
  if (final) {
    const refs = state.py.commit(text);   // Session: follow-ups resolve here
    if (refs.length) present(refs, text);
    live.utterRefs = [];                  // sentence done; its references stay in the history
    return;
  }
  const refs = state.py.preview(text);
  if (!refs.length) return;
  const last = refs[refs.length - 1];
  if (last.after >= 1) {                  // speaker has moved on: show now
    present(refs, text);
    return;
  }
  // Reference is still the last thing said: wait briefly in case it grows
  // ("John 3" -> "John 3 verse 16", "verse 1" -> "verse 16").
  live.waitTimer = setTimeout(() => present(refs, text), last.whole ? WAIT_CHAPTER_MS : WAIT_VERSE_MS);
}

// Put a sentence's references into the history; the newest goes on screen.
function present(refs, text) {
  const labels = refs.map((r) => r.label);
  // This sentence's earlier preview is replaced, not added to.
  state.history = state.history.filter((h) => !live.utterRefs.includes(h.label) && !labels.includes(h.label));
  state.history.push(...refs);
  state.history = state.history.slice(-HISTORY_MAX);
  live.utterRefs = labels;
  state.take = { text, mode: live.on ? "spoken" : "typed", refs: state.history };
  $("heard").textContent = text;
  $("result").hidden = false;
  const newest = state.history[state.history.length - 1];
  renderChips();
  if (newest.label !== state.shownLabel || $("screen").classList.contains("hidden")) {
    showRef(state.history.length - 1, false);
    resetFeedback();
  } else {
    markChip(state.history.length - 1);
  }
}

// ================================================================= display
function renderChips() {
  const chips = $("chips");
  chips.replaceChildren();
  $("picker").hidden = state.history.length < 2;
  state.history.forEach((ref, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.setAttribute("role", "radio");
    const k = document.createElement("kbd");
    k.textContent = i + 1;
    b.append(k, ref.label);
    b.addEventListener("click", () => showRef(i, true));
    chips.append(b);
  });
}

function markChip(index) {
  [...$("chips").children].forEach((c, i) => c.setAttribute("aria-checked", String(i === index)));
}

// byOperator: the operator picked it, so follow-ups ("next verse") are relative to it.
function showRef(index, byOperator) {
  const ref = state.history[index];
  if (!ref) return;
  state.shownLabel = ref.label;
  if (state.take) state.take.shown = index;
  if (byOperator && state.py) state.py.focus(ref.label);
  const screen = $("screen");
  screen.classList.remove("hidden");
  screen.replaceChildren();
  const h = document.createElement("div");
  h.className = "ref";
  h.textContent = ref.label;
  screen.append(h);
  for (const [, verse, body] of ref.verses) {
    const p = document.createElement("p");
    const sup = document.createElement("sup");
    sup.textContent = verse;
    p.append(sup, body);
    screen.append(p);
  }
  screen.scrollTop = 0;
  markChip(index);
}

function toggleHide() {
  if (!$("result").hidden) $("screen").classList.toggle("hidden");
}

function typed(text) {
  const refs = state.py.commit(text);
  if (refs.length) {
    live.utterRefs = [];
    present(refs, text);
    return;
  }
  $("heard").textContent = text;
  $("result").hidden = false;
  state.take = { text, mode: "typed", refs: state.history };
  if (!state.history.length) {
    const screen = $("screen");
    screen.replaceChildren();
    const p = document.createElement("p");
    p.className = "none";
    p.textContent = "No verse detected. The screen would stay as it was.";
    screen.append(p);
  }
  resetFeedback();
}

// =============================================== feedback (Netlify Forms)
function resetFeedback() {
  const f = $("fb");
  f.querySelectorAll("input[type=radio]").forEach((r) => (r.checked = false));
  f.expected.value = "";
  f.comment.value = "";
  $("fb-status").textContent = "";
  $("fb-status").className = "fb-status";
}

async function sendFeedback(e) {
  e.preventDefault();
  const f = $("fb");
  const take = state.take;
  if (!take) return;
  const status = $("fb-status");
  const button = f.querySelector("button[type=submit]");
  const data = new URLSearchParams();
  data.append("form-name", "feedback");
  data.append("tester", f.tester.value.trim());
  data.append("verdict", f.verdict.value);
  data.append("heard", take.text);
  data.append("detected", take.refs.map((r, i) => (i === take.shown ? `[${r.label}]` : r.label)).join("; ") || "(none)");
  data.append("expected", f.expected.value.trim());
  data.append("comment", f.comment.value.trim());
  data.append("input_mode", take.mode);
  data.append("browser", navigator.userAgent);
  data.append("app_version", APP_VERSION);
  try { localStorage.setItem("vb-tester", f.tester.value.trim()); } catch {}

  button.disabled = true;
  status.className = "fb-status";
  status.textContent = "Sending…";
  try {
    const res = await fetch("/", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: data.toString(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    status.className = "fb-status ok";
    status.textContent = "Thanks! Feedback sent.";
  } catch (err) {
    status.className = "fb-status err";
    status.textContent = `Couldn't send (${err.message}). Please try again.`;
  } finally {
    button.disabled = false;
  }
}

// ================================================================ wire up
$("mic").addEventListener("click", () => (live.on ? stopListening() : startListening()));
$("type-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("type-input").value.trim();
  if (text && state.py) typed(text);
});
$("hide-btn").addEventListener("click", toggleHide);
document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, textarea")) return;
  if (e.key === "h" || e.key === "H" || e.key === "Escape") toggleHide();
  else if (/^[1-9]$/.test(e.key)) showRef(Number(e.key) - 1, true);
});
$("fb").addEventListener("submit", sendFeedback);

// Hook for automated tests (simulates speech events).
window.__vbTest = { onSpeech, state, live };

boot();
