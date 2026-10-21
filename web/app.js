const $ = (s) => document.querySelector(s);
const MAX_BYTES = 100 * 1024 * 1024;
const OFFLINE = "Can't reach the model. Check the Colab tab is still running.";
// Intl.DisplayNames doesn't know every Indic code; fill the gaps.
const EXTRA_NAMES = { brx: "Bodo", sat: "Santali", mni: "Manipuri", kok: "Konkani", doi: "Dogri", mai: "Maithili",
  bho: "Bhojpuri", hne: "Chhattisgarhi", bgc: "Haryanvi", bhb: "Bhili", jw: "Javanese", haw: "Hawaiian", yue: "Cantonese" };
const names = new Intl.DisplayNames(["en"], { type: "language" });
const langName = (c) => EXTRA_NAMES[c] || (() => { try { return names.of(c); } catch { return c; } })();

let engines = [];
const items = [];

async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(body.detail || `Request failed (${r.status})`), { status: r.status });
  return body;
}

/* ---------- status line ---------- */
function setStatus(state, text) {
  $("#status").dataset.state = state;
  if ($("#status-text").textContent !== text) $("#status-text").textContent = text;
}
async function health() {
  try {
    const h = await api("/api/health");
    h.gpu ? setStatus("ok", "Model ready on GPU") : setStatus("slow", "Model ready (no GPU, transcription will be slow)");
    if (!engines.length) loadEngines();
  } catch {
    setStatus("down", OFFLINE);
  }
}

/* ---------- settings ---------- */
const selectedEngine = () => engines.find((e) => e.id === document.querySelector("input[name=engine]:checked")?.value);

async function loadEngines() {
  try { engines = await api("/api/engines"); } catch { return; }
  const keep = selectedEngine()?.id;
  const box = $("#engines");
  box.replaceChildren(...engines.map((e) => {
    const label = document.createElement("label");
    label.className = "engine";
    if (!e.available) label.dataset.unavailable = "";
    label.innerHTML = `<input type="radio" name="engine"><span class="engine-label"></span><span class="engine-desc"></span>`;
    const input = label.querySelector("input");
    input.value = e.id;
    input.checked = keep ? keep === e.id : e.default;
    label.querySelector(".engine-label").textContent = e.label;
    const desc = label.querySelector(".engine-desc");
    if (e.available) desc.textContent = e.description;
    else {
      desc.append("Accept the license on Hugging Face first: ");
      const a = Object.assign(document.createElement("a"), { href: `https://huggingface.co/${e.gated_repo}`, target: "_blank", rel: "noopener", textContent: e.gated_repo });
      desc.append(a);
    }
    input.addEventListener("change", renderOptions);
    return label;
  }));
  if (!selectedEngine() && engines[0]) box.querySelector("input").checked = true;
  renderOptions();
}

function renderOptions() {
  const e = selectedEngine();
  if (!e) return;
  const sel = $("#lang"), prev = sel.value;
  const codes = e.languages.filter(Boolean).sort((a, b) => langName(a).localeCompare(langName(b)));
  sel.replaceChildren(
    ...(e.languages.includes("") ? [new Option("Detect automatically", "")] : []),
    ...codes.map((c) => new Option(langName(c), c)),
  );
  if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
  $("#mode-field").hidden = !e.modes.includes("mixed");
}

function settings() {
  const e = selectedEngine();
  const mode = e.modes.includes("mixed") ? document.querySelector("input[name=mode]:checked").value : e.modes[0];
  return { engine: e.id, label: e.label, lang: $("#lang").value, mode };
}

/* ---------- files ---------- */
const fmtSize = (b) => b >= 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`;
const fmtTime = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const stem = (n) => n.replace(/\.[^.]+$/, "") || "transcript";

function addFiles(files) {
  if (!engines.length) return toast("The model isn't reachable yet.");
  for (const file of files) {
    const el = $("#item-tpl").content.firstElementChild.cloneNode(true);
    const item = { file, el, s: settings(), id: null, text: "", status: "" };
    el.querySelector(".name").textContent = file.name;
    el.querySelector(".copy").onclick = () => navigator.clipboard.writeText(item.text).then(() => toast("Copied"), () => toast("Couldn't copy"));
    el.querySelector(".download").onclick = () => save(new Blob([item.text + "\n"], { type: "text/plain;charset=utf-8" }), stem(file.name) + ".txt");
    el.querySelector(".retry").onclick = () => { item.s = settings(); start(item); };
    items.push(item);
    $("#items").append(el);
    start(item);
  }
  refreshList();
}

async function start(item) {
  item.id = null;
  render(item, { status: "uploading" });
  if (item.file.size > MAX_BYTES) return render(item, { status: "failed", error: "This file is over 100 MB. Convert it to mp3 and try again." });
  const fd = new FormData();
  fd.append("file", item.file);
  for (const k of ["engine", "lang", "mode"]) fd.append(k, item.s[k]);
  try {
    item.id = (await api("/api/jobs", { method: "POST", body: fd })).id;
    poll(item, item.id);
  } catch (e) {
    render(item, { status: "failed", error: e.status ? e.message : OFFLINE });
  }
}

async function poll(item, id) {
  if (item.id !== id) return; // superseded by a retry
  let job;
  try {
    job = await api(`/api/jobs/${id}`);
  } catch (e) {
    if (e.status === 404) return render(item, { status: "failed", error: e.message });
    item.el.dataset.offline = "";
    item.el.querySelector(".chip").textContent = "Can't reach the model";
    item.el.querySelector(".meta").textContent = OFFLINE;
    return setTimeout(() => poll(item, id), 2000);
  }
  render(item, job);
  if (!["done", "failed"].includes(job.status)) setTimeout(() => poll(item, id), 2000);
}

function chipText(item, j) {
  switch (j.status) {
    case "uploading": return "Uploading";
    case "queued": return j.ahead ? `Waiting, ${j.ahead} ahead` : "Waiting";
    case "loading_model": return `Loading ${item.s.label}`;
    case "transcribing": return `Transcribing ${fmtTime(j.elapsed_seconds || 0)}`;
    case "done": return "Done";
    default: return "Failed";
  }
}

function render(item, j) {
  const el = item.el, was = item.status;
  item.status = j.status;
  delete el.dataset.offline;
  el.dataset.status = j.status;
  el.querySelector(".chip").textContent = chipText(item, j);
  const parts = [fmtSize(item.file.size), item.s.label];
  if (j.audio_seconds) parts.push(fmtTime(j.audio_seconds));
  el.querySelector(".meta").textContent = parts.join(" · ");
  const err = el.querySelector(".error");
  err.hidden = j.status !== "failed";
  err.textContent = j.error || "";
  el.querySelector(".retry").hidden = j.status !== "failed";
  el.querySelector(".result").hidden = j.status !== "done";
  if (j.status === "done") {
    item.text = j.text;
    const t = el.querySelector(".text");
    t.textContent = j.text;
    t.setAttribute("aria-label", `Transcript of ${item.file.name}`);
    if (j.language) t.lang = j.language;
  }
  if (was !== j.status && (j.status === "done" || j.status === "failed")) {
    $("#announce").textContent = `${item.file.name}: ${j.status === "done" ? "transcript ready" : "failed"}`;
    if (j.status === "failed") loadEngines(); // a license failure changes engine availability
  }
  refreshList();
}

function refreshList() {
  const done = items.filter((i) => i.status === "done");
  $("#empty").hidden = items.length > 0;
  $("#count").textContent = items.length ? `${done.length} of ${items.length} done` : "";
  $("#dl-all").hidden = done.length < 2;
}

$("#dl-all").onclick = () => {
  const ids = items.filter((i) => i.status === "done").map((i) => i.id).join(",");
  const a = Object.assign(document.createElement("a"), { href: `/api/zip?ids=${ids}`, download: "transcripts.zip" });
  a.click();
};

function save(blob, name) {
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
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
// Stop the browser opening a file dropped outside the zone.
for (const t of ["dragover", "drop"]) window.addEventListener(t, (e) => e.preventDefault());
drop.addEventListener("dragover", () => drop.classList.add("over"));
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { drop.classList.remove("over"); addFiles([...e.dataTransfer.files]); });

health();
setInterval(health, 20000);
