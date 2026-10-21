const $ = (s) => document.querySelector(s);
const MAX_BYTES = 100 * 1024 * 1024;
const OFFLINE = "Can't reach the model. Check the Colab tab is still running.";
const BUSY = ["uploading", "queued", "loading_model", "transcribing"];

let engines = [];
const files = [];   // {file, status, job, jobId, s, error}
let current = null; // the file shown on the right

async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(body.detail || `Request failed (${r.status})`), { status: r.status });
  return body;
}

/* ---------- status ---------- */
function setStatus(state, text) {
  const el = $("#status");
  el.dataset.state = state;
  el.textContent = text;
}
async function health() {
  try {
    const h = await api("/api/health");
    h.gpu ? setStatus("ok", "Model ready on GPU") : setStatus("slow", "Running without a GPU, so transcription will be slow.");
    if (!engines.length) loadEngines();
  } catch {
    setStatus("down", OFFLINE);
  }
}

/* ---------- model ---------- */
const selected = () => engines.find((e) => e.id === $("#model").value);

async function loadEngines() {
  try { engines = await api("/api/engines"); } catch { return; }
  const sel = $("#model"), keep = sel.value;
  sel.replaceChildren(...engines.map((e) => {
    const o = new Option(e.label + (e.locked ? " (needs Hugging Face token)" : !e.available ? " (accept license first)" : ""), e.id);
    o.disabled = e.locked;
    return o;
  }));
  const pick = engines.find((e) => e.id === keep && !e.locked) || engines.find((e) => e.default && !e.locked) || engines.find((e) => !e.locked);
  if (pick) sel.value = pick.id;
  renderModel();
}

function renderModel() {
  const e = selected(), hint = $("#model-hint");
  hint.replaceChildren();
  if (e) {
    if (!e.available && e.gated_repo) {
      hint.append("Accept the license on Hugging Face first: ");
      hint.append(Object.assign(document.createElement("a"), { href: `https://huggingface.co/${e.gated_repo}`, target: "_blank", rel: "noopener", textContent: e.gated_repo }));
    } else hint.textContent = e.description;
    if (engines.some((x) => x.locked)) hint.append(" Add a Hugging Face token to unlock better Tamil/Malayalam.");
  }
  $("#mode-field").hidden = !e?.modes.includes("mixed");
  renderStart();
}
$("#model").addEventListener("change", renderModel);

function settings() {
  const e = selected();
  const mode = e.modes.includes("mixed") ? document.querySelector("input[name=mode]:checked").value : e.modes[0];
  return { engine: e.id, label: e.label, mode };
}

/* ---------- files ---------- */
const fmtSize = (b) => b >= 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`;
const clock = (s) => { s = Math.floor(s); return [s / 3600, (s % 3600) / 60, s % 60].map((n) => String(Math.floor(n)).padStart(2, "0")).join(":"); };
const short = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const stem = (n) => n.replace(/\.[^.]+$/, "") || "transcript";

function addFiles(list) {
  for (const file of list) {
    const f = { file, status: "ready", job: null };
    if (file.size > MAX_BYTES) Object.assign(f, { status: "failed", error: "This file is over 100 MB. Convert it to mp3 and try again." });
    files.push(f);
    current ??= f;
  }
  render();
}

function statusText(f) {
  const j = f.job || {};
  switch (f.status) {
    case "ready": return "Ready";
    case "uploading": return "Uploading…";
    case "queued": return j.ahead ? `Waiting, ${j.ahead} ahead` : "Waiting…";
    case "loading_model": return `Loading ${f.s.label}…`;
    case "transcribing": return `Transcribing ${short(j.elapsed_seconds || 0)}`;
    case "done": return "Done";
    default: return "Failed";
  }
}

const MUSIC = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`;
const CLOSE = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>`;

function renderFiles() {
  $("#files").replaceChildren(...files.map((f) => {
    const li = document.createElement("li");
    li.className = "file";
    li.setAttribute("aria-current", f === current);
    li.innerHTML = `<span class="file-icon" aria-hidden="true">${MUSIC}</span><div class="file-id"><p class="file-name"></p><p class="file-meta"></p></div>`;
    li.querySelector(".file-name").textContent = f.file.name;
    const st = document.createElement("span");
    st.className = f.status === "done" ? "st-done" : f.status === "failed" ? "st-failed" : BUSY.includes(f.status) ? "st-busy" : "";
    st.textContent = statusText(f);
    li.querySelector(".file-meta").append(`${fmtSize(f.file.size)} · `, st);
    li.tabIndex = 0;
    li.setAttribute("aria-label", `${f.file.name}, ${statusText(f)}. Show transcription.`);
    li.onclick = () => { current = f; render(); };
    li.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); li.click(); } };
    if (!BUSY.includes(f.status)) {
      const x = Object.assign(document.createElement("button"), { type: "button", className: "remove", innerHTML: CLOSE });
      x.setAttribute("aria-label", `Remove ${f.file.name}`);
      x.onclick = (e) => {
        e.stopPropagation();
        files.splice(files.indexOf(f), 1);
        if (current === f) current = files[0] || null;
        render();
      };
      li.append(x);
    }
    return li;
  }));
}

const pending = () => files.filter((f) => (f.status === "ready" || f.status === "failed") && f.file.size <= MAX_BYTES);
function renderStart() {
  $("#start").disabled = !pending().length || !selected() || selected().locked;
}

function renderOutput() {
  const out = $("#output"), f = current;
  const done = files.filter((x) => x.status === "done");
  $("#copy").disabled = f?.status !== "done";
  $("#download").disabled = !done.length;
  $("#download").lastChild.textContent = done.length > 1 ? " Download all" : " Download";

  const place = (title, text, extra = "", cls = "") => {
    out.innerHTML = `<div class="placeholder ${cls}">${extra}<strong></strong><span></span></div>`;
    out.querySelector("strong").textContent = title;
    out.querySelector("span").textContent = text;
  };
  if (!f) return place("No transcription yet", "Upload audio, choose a model, then press Start Transcription.",
    `<svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></svg>`);
  if (f.status === "ready") return place(f.file.name, "Ready. Press Start Transcription.");
  if (f.status === "failed") return place("Transcription failed", f.error || "", "", "error");
  if (BUSY.includes(f.status)) return place(statusText(f), f.file.name, `<div class="bar" aria-hidden="true"></div>`);

  const j = f.job;
  out.replaceChildren();
  if (j.segments?.length) {
    const range = Object.assign(document.createElement("p"), { className: "range", textContent: `${clock(0)}  -  ${clock(j.audio_seconds || j.segments.at(-1).end)}` });
    out.append(range, ...j.segments.map((s) => {
      const d = document.createElement("div");
      d.className = "seg";
      const t = Object.assign(document.createElement("time"), { textContent: clock(s.start) });
      d.append(t, s.text);
      return d;
    }));
  } else {
    if (j.audio_seconds) out.append(Object.assign(document.createElement("p"), { className: "range", textContent: `${clock(0)}  -  ${clock(j.audio_seconds)}` }));
    out.append(Object.assign(document.createElement("p"), { className: "plain", textContent: j.text }));
  }
  if (j.language) out.lang = j.language;
}

function render() {
  $("#drop").classList.toggle("compact", files.length > 0);
  $(".drop-title").textContent = files.length ? "Add more files" : "Click to upload or drag and drop";
  renderFiles();
  renderStart();
  renderOutput();
}

/* ---------- transcribe ---------- */
$("#start").onclick = () => {
  const s = settings();
  for (const f of pending()) { f.s = s; upload(f); }
};

async function upload(f) {
  Object.assign(f, { status: "uploading", job: null, error: null, jobId: null });
  render();
  const fd = new FormData();
  fd.append("file", f.file);
  fd.append("engine", f.s.engine);
  fd.append("lang", "");
  fd.append("mode", f.s.mode);
  try {
    f.jobId = (await api("/api/jobs", { method: "POST", body: fd })).id;
    poll(f, f.jobId);
  } catch (e) {
    finish(f, "failed", e.status ? e.message : OFFLINE);
  }
}

async function poll(f, id) {
  if (f.jobId !== id || !files.includes(f)) return;
  try {
    const j = await api(`/api/jobs/${id}`);
    f.job = j;
    if (j.status === "done" || j.status === "failed") return finish(f, j.status, j.error);
    f.status = j.status;
    render();
  } catch (e) {
    if (e.status === 404) return finish(f, "failed", e.message);
    setStatus("down", OFFLINE);
  }
  setTimeout(() => poll(f, id), 2000);
}

function finish(f, status, error) {
  Object.assign(f, { status, error });
  $("#announce").textContent = `${f.file.name}: ${status === "done" ? "transcription ready" : "failed"}`;
  if (status === "failed") loadEngines(); // a license failure changes model availability
  render();
}

/* ---------- copy / download ---------- */
$("#copy").onclick = () => navigator.clipboard.writeText(current.job.text).then(() => toast("Copied"), () => toast("Couldn't copy"));
$("#download").onclick = () => {
  const done = files.filter((f) => f.status === "done");
  if (done.length > 1) return save(`/api/zip?ids=${done.map((f) => f.jobId).join(",")}`, "transcripts.zip");
  const blob = new Blob([done[0].job.text + "\n"], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  save(url, stem(done[0].file.name) + ".txt");
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
function save(href, name) {
  Object.assign(document.createElement("a"), { href, download: name }).click();
}

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 1800);
}

/* ---------- drop zone ---------- */
const drop = $("#drop"), input = $("#file");
drop.addEventListener("click", () => input.click());
drop.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
});
input.addEventListener("change", () => { addFiles([...input.files]); input.value = ""; });
for (const t of ["dragover", "drop"]) window.addEventListener(t, (e) => e.preventDefault()); // don't let the browser open dropped files
drop.addEventListener("dragover", () => drop.classList.add("over"));
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { drop.classList.remove("over"); addFiles([...e.dataTransfer.files]); });

render();
health();
setInterval(health, 20000);
