"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  backends: [],
  backend: null,
  model: null,
  resume: "",
  cover: "",
  activeTab: "resume",
  rssJobs: [],
  cronJobs: [],
  // Capability flags reported by /api/backends.
  stdioMcpAvailable: true,
  appVersion: "",
};

// Secrets (API keys) must not persist across sessions. Migrate any legacy
// keys out of localStorage (which survives restarts) into sessionStorage
// (which does not), then drop the old keys entirely.
const SECRET_KEYS = ["RT_remote_api_key", "RT_search_api_key"];
SECRET_KEYS.forEach((k) => {
  const legacy = localStorage.getItem(k);
  if (legacy) sessionStorage.setItem(k, legacy);
  localStorage.removeItem(k);
});

/* ---------- Secret storage (desktop keyring or sessionStorage fallback) ----------
 * In the desktop app, prefer the OS keyring so keys survive a restart and
 * are never written to plaintext disk. The browser version falls back to
 * sessionStorage (cleared on tab close) so the privacy guarantee from the
 * README still holds when the app is used in a plain browser.
 */
const keyStore = (() => {
  const isDesktop =
    typeof window !== "undefined" &&
    window.pywebview &&
    typeof window.pywebview.api === "object";
  const usesKeyring = isDesktop && window.pywebview.api.has_keyring
    ? window.pywebview.api.has_keyring()
    : false;

  return {
    isDesktop,
    usesKeyring,
    async get(key) {
      if (usesKeyring) {
        try {
          const res = await window.pywebview.api.load_key(key);
          if (res && res.ok) return res.value || "";
        } catch {
          /* fall through to sessionStorage */
        }
      }
      return sessionStorage.getItem(key) || "";
    },
    async set(key, value) {
      if (usesKeyring) {
        try {
          const res = await window.pywebview.api.store_key(key, value || "");
          if (res && res.ok) {
            // Keep a sessionStorage copy too so a hot-reload before the
            // keyring finishes doesn't briefly show an empty field.
            if (value) sessionStorage.setItem(key, value);
            else sessionStorage.removeItem(key);
            return true;
          }
        } catch {
          /* fall through */
        }
      }
      if (value) sessionStorage.setItem(key, value);
      else sessionStorage.removeItem(key);
      return false;
    },
  };
})();

/* ---------- Backend detection ---------- */
const LSKEY_CACHED_BACKENDS = "RT_cached_backends";
const BACKEND_CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24h

function loadCachedBackends() {
  // Read the cached model list so the UI is populated instantly while the
  // /api/backends request is in flight. The cache also serves as a fallback
  // when the server is briefly unreachable.
  try {
    const raw = localStorage.getItem(LSKEY_CACHED_BACKENDS);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.backends)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveCachedBackends(backends) {
  try {
    const payload = {
      fetched_at: new Date().toISOString(),
      backends,
    };
    localStorage.setItem(LSKEY_CACHED_BACKENDS, JSON.stringify(payload));
  } catch {
    /* localStorage may be disabled in private mode — silently ignore */
  }
}

function renderBackendStatus(backends, opts = {}) {
  const statusEl = $("backend-status");
  if (!backends.length) {
    statusEl.textContent = opts.stale
      ? "⚠ Cached backends (stale): none detected. Refresh to retry."
      : "⚠ No LLM backend detected. Start Ollama or configure a remote API.";
    statusEl.className = "backend-status offline";
    $("generate-btn").disabled = true;
    return;
  }
  const names = backends.map((b) => b.label).join(" & ");
  statusEl.textContent = opts.stale
    ? `⚠ Cached backends (stale): ${names}. Refreshing…`
    : `✓ Backends: ${names}`;
  statusEl.className = opts.stale ? "backend-status offline" : "backend-status online";
}

async function loadBackends() {
  const statusEl = $("backend-status");

  // 1. Render cached backends immediately so the model dropdown is populated
  //    before the network round-trip completes.
  const cached = loadCachedBackends();
  if (cached && cached.backends.length) {
    state.backends = cached.backends;
    const ageMs = Date.now() - new Date(cached.fetched_at).getTime();
    renderBackendStatus(cached.backends, { stale: ageMs > BACKEND_CACHE_MAX_AGE_MS });
    populateBackendSelect();
  }

  // 2. Refresh from the server in the background.
  try {
    const res = await fetch("/api/backends");
    const data = await res.json();
    state.backends = data.backends || [];
    state.stdioMcpAvailable = data.stdio_mcp_available !== false;
    state.appVersion = data.version || "";
    const verEl = $("app-version");
    if (verEl && state.appVersion) verEl.textContent = `v${state.appVersion}`;

    // Prefill RSS feed URL from server config if the user hasn't set one.
    if (data.rss_feed_url && !localStorage.getItem(LSKEY_RSS_URL)) {
      $rssUrl.value = data.rss_feed_url;
      localStorage.setItem(LSKEY_RSS_URL, data.rss_feed_url);
    }

    saveCachedBackends(state.backends);
    renderBackendStatus(state.backends);
    populateBackendSelect();
    await maybeShowSetupBanner();
  } catch (err) {
    if (!cached) {
      statusEl.textContent = "⚠ Could not reach the app server.";
      statusEl.className = "backend-status offline";
    }
    // If we had a cache, keep showing it as a fallback (already rendered above).
  }
}

/* ---------- First-run setup banner ---------- */
async function maybeShowSetupBanner() {
  // No local backends detected AND no remote API key entered yet — nudge the
  // user toward one of the three setup paths. The banner is dismissible and
  // remembers the dismissal in localStorage so it only shows once.
  const dismissed = localStorage.getItem("RT_setup_banner_dismissed") === "1";
  if (dismissed) return;
  const remoteKey = await keyStore.get("RT_remote_api_key");
  const hasRemoteKey =
    (state.backends || []).some((b) => b.needs_api_key) && remoteKey.length > 0;
  const hasLocalBackend = (state.backends || []).some((b) => !b.needs_api_key);
  if (hasLocalBackend || hasRemoteKey) return;

  let banner = $("setup-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "setup-banner";
    banner.className = "setup-banner";
    document.querySelector("main.layout")?.prepend(banner);
  }
  banner.innerHTML = `
    <strong>No local LLM found.</strong>
    Install <a href="https://ollama.com" target="_blank" rel="noopener">Ollama</a>
    and run <code>ollama pull hermes3:8b</code>,
    start LM Studio's local server,
    or paste an OpenRouter key in Settings.
    <button class="setup-dismiss" type="button">✕</button>
  `;
  banner.querySelector(".setup-dismiss").onclick = () => {
    localStorage.setItem("RT_setup_banner_dismissed", "1");
    banner.remove();
  };
}

function populateBackendSelect() {
  const sel = $("backend-select");
  sel.innerHTML = "";
  state.backends.forEach((b) => {
    const opt = document.createElement("option");
    opt.value = b.id;
    opt.textContent = b.label + (b.needs_api_key ? " (needs API key)" : "");
    sel.appendChild(opt);
  });

  // Restore saved selection
  const savedBackend = localStorage.getItem("RT_backend");
  if (savedBackend && state.backends.some((b) => b.id === savedBackend)) {
    sel.value = savedBackend;
  }

  sel.addEventListener("change", onBackendChange);
  onBackendChange();
  return Promise.resolve();
}

async function onBackendChange() {
  const sel = $("backend-select");
  const backend = state.backends.find((b) => b.id === sel.value);
  if (!backend) return;
  state.backend = backend.id;
  localStorage.setItem("RT_backend", backend.id);

  // Show/hide API key box for remote backends
  const keyBox = $("remote-api-key-box");
  if (backend.needs_api_key) {
    keyBox.classList.remove("hidden");
    const savedApiKey = await keyStore.get("RT_remote_api_key");
    $("remote-api-key").value = savedApiKey;
  } else {
    keyBox.classList.add("hidden");
  }

  populateModels();
}

/* ---------- Model fetching ---------- */
function populateModels() {
  const sel = $("backend-select");
  const backend = state.backends.find((b) => b.id === sel.value);
  if (!backend) return;

  const modelSel = $("model-select");
  modelSel.innerHTML = "";

  if (backend.models && backend.models.length) {
    backend.models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      modelSel.appendChild(opt);
    });
    const savedModel = localStorage.getItem("RT_model");
    if (savedModel && backend.models.includes(savedModel)) {
      modelSel.value = savedModel;
    }
    state.model = modelSel.value || backend.models[0];
    return;
  }

  // No models yet (remote backend without fetched models, or local with empty)
  modelSel.innerHTML = '<option value="">— no models loaded —</option>';
  if (!backend.needs_api_key) {
    modelSel.innerHTML = '<option value="">— no models detected —</option>';
  }
  state.model = "";
}

$("fetch-models-btn").addEventListener("click", async () => {
  const apiKey = $("remote-api-key").value.trim();
  if (!apiKey) {
    $("models-fetch-status").textContent = "Enter an API key first.";
    return;
  }
  await keyStore.set("RT_remote_api_key", apiKey);
  $("models-fetch-status").textContent = "Fetching…";
  $("fetch-models-btn").disabled = true;

  try {
    const res = await fetch("/api/models", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backend_id: state.backend, api_key: apiKey }),
    });
    const data = await res.json();
    const models = data.models || [];
    if (!models.length) {
      $("models-fetch-status").textContent = "No models returned. Check your key.";
      return;
    }
    // Update the backend's model list in state
    const b = state.backends.find((b) => b.id === state.backend);
    if (b) b.models = models;
    populateModels();
    $("models-fetch-status").textContent = `✓ ${models.length} models loaded.`;
  } catch (err) {
    $("models-fetch-status").textContent = "Fetch failed: " + err.message;
  } finally {
    $("fetch-models-btn").disabled = false;
  }
});

$("model-select").addEventListener("change", () => {
  state.model = $("model-select").value;
  localStorage.setItem("RT_model", state.model);
});

/* ---------- Update check ---------- */
$("check-update-btn").addEventListener("click", async () => {
  const btn = $("check-update-btn");
  const status = $("update-status");
  btn.disabled = true;
  status.textContent = "Checking…";
  status.style.color = "";
  try {
    const res = await fetch("/api/check-update");
    const data = await res.json();
    if (data.error) {
      status.textContent = `Could not check: ${data.error}`;
      status.style.color = "#f87171";
      return;
    }
    if (data.update_available) {
      status.innerHTML =
        `v${data.latest} available — ` +
        `<a href="${data.url}" target="_blank" rel="noopener">download</a>`;
      status.style.color = "#34d399";
    } else {
      status.textContent = `✓ You have the latest version (v${data.current}).`;
      status.style.color = "#34d399";
    }
  } catch (err) {
    status.textContent = "Update check failed: " + err.message;
    status.style.color = "#f87171";
  } finally {
    btn.disabled = false;
  }
});

/* ---------- File upload ---------- */
$("resume-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  $("file-name").textContent = file.name;
  const fd = new FormData();
  fd.append("file", file);
  const statusEl = $("status");
  statusEl.textContent = "Reading file…";
  statusEl.className = "status";
  try {
    const res = await fetch("/api/extract", { method: "POST", body: fd });
    const data = await res.json();
    if (data.error) {
      statusEl.textContent = data.error;
      statusEl.className = "status error";
      return;
    }
    $("resume-text").value = data.text;
    statusEl.textContent = "✓ Resume loaded from file.";
    statusEl.className = "status ok";
  } catch (err) {
    statusEl.textContent = "Failed to read file.";
    statusEl.className = "status error";
  }
});

/* ---------- Temperature slider ---------- */
$("temperature").addEventListener("input", (e) => {
  $("temp-value").textContent = e.target.value;
});

/* ---------- RSS / Atom job feed (2b) ---------- */
const LSKEY_RSS_URL = "RT_rss_url";
const $rssUrl = $("rss-url");
const $rssStatus = $("rss-status");
const $rssJobList = $("rss-job-list");

$rssUrl.value = localStorage.getItem(LSKEY_RSS_URL) || "";
$("rss-load-btn").addEventListener("click", loadRssJobs);

async function loadRssJobs() {
  const url = $rssUrl.value.trim();
  if (!isHttpUrl(url)) {
    $rssStatus.textContent = "Enter a valid http(s) RSS/Atom feed URL.";
    return;
  }
  localStorage.setItem(LSKEY_RSS_URL, url);
  $rssStatus.textContent = "Loading RSS feed…";
  $rssJobList.innerHTML = "";
  try {
    const res = await fetch(`/api/rss?url=${encodeURIComponent(url)}`);
    const data = await res.json();
    const jobs = data.jobs || [];
    if (!res.ok || !jobs.length) {
      state.rssJobs = [];
      $rssStatus.textContent = data.error || "No jobs found in this feed.";
      return;
    }
    state.rssJobs = jobs;
    $rssStatus.textContent = `${jobs.length} RSS jobs loaded. Click one to use it.`;
    renderRssJobs(jobs);
  } catch (err) {
    state.rssJobs = [];
    $rssStatus.textContent = "Failed to load RSS feed: " + err.message;
  }
}

function renderRssJobs(jobs) {
  $rssJobList.innerHTML = "";
  jobs.forEach((job) => {
    const div = document.createElement("div");
    div.className = "rss-job";
    const desc = job.description || "";
    div.innerHTML =
      `<div class="jt">${escapeHtml(job.title || "Untitled")}</div>` +
      (job.company ? `<div class="jc">${escapeHtml(job.company)}</div>` : "") +
      (desc ? `<div class="jd">${escapeHtml(desc)}</div>` : "") +
      `<button class="rss-gen-btn">✨ Generate</button>`;
    div.title = "Click to load this job into the generator";
    div.addEventListener("click", () => useRssJob(job));
    const genBtn = div.querySelector(".rss-gen-btn");
    genBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      generateForJob(job);
    });
    $rssJobList.appendChild(div);
  });
}

function useRssJob(job) {
  buildJobDescription(job);
  setStatus(`✓ Loaded "${job.title}" into the job description. Click Generate.`, "ok");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function generateForJob(job) {
  buildJobDescription(job);
  setStatus(`Generating for "${job.title}"…`, "");
  generate();
}

function buildJobDescription(job) {
  // Build a job description from the feed entry.
  const parts = [];
  if (job.title) parts.push(`Job Title: ${job.title}`);
  if (job.company) parts.push(`Company: ${job.company}`);
  if (job.link || job.url) parts.push(`Link: ${job.link || job.url}`);
  if (job.location) parts.push(`Location: ${job.location}`);
  if (job.description) parts.push(`\nDescription:\n${job.description}`);
  $("job-description").value = parts.join("\n");
}

/* ---------- Job Opportunities (Hermes cron feed) ---------- */
const $cronStatus = $("cron-status");
const $cronJobList = $("cron-job-list");

async function loadCronJobs() {
  $cronStatus.textContent = "Loading job opportunities…";
  try {
    const res = await fetch("/api/cron-jobs");
    const data = await res.json();
    const jobs = data.jobs || [];
    if (!jobs.length) {
      state.cronJobs = [];
      $cronStatus.textContent = data.error || "No job opportunities in the cron feed yet.";
      $cronJobList.innerHTML = "";
      return;
    }
    state.cronJobs = jobs;
    $cronStatus.textContent = `${jobs.length} job opportunities from the latest cron run.`;
    renderCronJobs(jobs);
  } catch (err) {
    $cronStatus.textContent = "Failed to load cron jobs: " + err.message;
  }
}

function renderCronJobs(jobs) {
  $cronJobList.innerHTML = "";
  jobs.forEach((job) => {
    const div = document.createElement("div");
    div.className = "rss-job";
    const title = job.title || "Untitled";
    const company = job.company || "";
    const loc = job.location || "";
    const src = job.source || "";
    div.innerHTML =
      `<div class="jt">${escapeHtml(title)}</div>` +
      (company ? `<div class="jc">${escapeHtml(company)}${loc ? " · " + escapeHtml(loc) : ""}</div>` : (loc ? `<div class="jc">${escapeHtml(loc)}</div>` : "")) +
      (src ? `<span class="jsrc">${escapeHtml(src)}</span>` : "");
    div.title = "Click to open this job in your browser";
    div.addEventListener("click", () => useCronJob(job));
    $cronJobList.appendChild(div);
  });
}

function useCronJob(job) {
  if (!isHttpUrl(job.url)) {
    setStatus("This job does not have a safe http(s) URL to preview.", "error");
    return;
  }
  openPreview(job);
}

/* ---------- Job preview modal ---------- */
const $previewModal = $("preview-modal");
const $previewTitle = $("preview-title");
const $previewSource = $("preview-source");
const $previewUrl = $("preview-url");
const $previewBody = $("preview-body");
let previewJobUrl = "";

function openPreview(job) {
  if (!isHttpUrl(job.url)) {
    setStatus("This job does not have a safe http(s) URL to preview.", "error");
    return;
  }
  previewJobUrl = job.url;
  $previewTitle.textContent = job.title || "Job Preview";
  $previewSource.textContent = job.source ? `Source: ${job.source}` : "";
  $previewUrl.textContent = job.url;
  $previewUrl.href = job.url;
  $previewBody.textContent = "Loading preview…";
  $previewModal.classList.remove("hidden");

  fetch(`/api/preview?url=${encodeURIComponent(job.url)}`)
    .then((res) => res.json())
    .then((data) => {
      if (data.error) {
        $previewBody.textContent = "Preview unavailable: " + data.error;
        return;
      }
      if (data.title) $previewTitle.textContent = data.title;
      $previewBody.textContent = data.text || "(No readable text found on this page.)";
    })
    .catch((err) => {
      $previewBody.textContent = "Preview failed: " + err.message;
    });
}

function closePreview() {
  $previewModal.classList.add("hidden");
}

$("preview-close").addEventListener("click", closePreview);
$("preview-open").addEventListener("click", () => {
  if (previewJobUrl) {
    window.open(previewJobUrl, "_blank");
    closePreview();
  }
});
$previewModal.addEventListener("click", (e) => {
  if (e.target === $previewModal) closePreview();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closePreview();
});

$("cron-refresh-btn").addEventListener("click", loadCronJobs);
loadCronJobs();

/* ---------- Auto-process jobs ---------- */
const $autoControls = $("auto-controls");
const $autoResumeName = $("auto-resume-name");
let autoResumeText = "";
let autoJobs = [];
let autoIndex = 0;
let autoRunning = false;

// Select a resume file to use for every job in the batch.
$("auto-resume-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/extract", { method: "POST", body: fd });
    const data = await res.json();
    if (data.error) { setStatus(data.error, "error"); return; }
    autoResumeText = data.text;
    $autoResumeName.textContent = file.name;
    setStatus(`✓ Resume loaded for auto-processing: ${file.name}`, "ok");
  } catch (err) {
    setStatus("Failed to read resume file.", "error");
  }
});

function startAutoProcess(jobs, label) {
  if (!jobs || !jobs.length) {
    setStatus("No jobs to process. Load a feed first.", "error");
    return;
  }
  autoJobs = jobs;
  autoIndex = 0;
  autoRunning = true;
  $autoControls.classList.remove("hidden");
  setStatus(`Auto-processing ${label}: ${jobs.length} jobs.`, "");
  processNextJob();
}

async function processNextJob() {
  if (!autoRunning) return;
  if (autoIndex >= autoJobs.length) {
    setStatus("✓ All jobs processed.", "ok");
    autoRunning = false;
    $autoControls.classList.add("hidden");
    return;
  }
  const job = autoJobs[autoIndex];
  const url = job.url || job.link;
  setStatus(`Processing ${autoIndex + 1}/${autoJobs.length}: ${job.title || "job"}…`, "");
  if (!url) {
    setStatus(`No URL for "${job.title || "job"}". Click Next to skip.`, "error");
    return;
  }
  try {
    const res = await fetch(`/api/preview?url=${encodeURIComponent(url)}`);
    const data = await res.json();
    if (data.error) {
      setStatus(`Could not fetch "${job.title || "job"}": ${data.error}`, "error");
      return;
    }
    $("job-description").value = data.text || "";
    if (autoResumeText) $("resume-text").value = autoResumeText;
    setStatus(`✓ Loaded job ${autoIndex + 1}. Generating…`, "ok");
    await autoGenerate();
  } catch (err) {
    setStatus(`Error processing "${job.title || "job"}": ${err.message}`, "error");
  }
}

async function autoGenerate() {
  if (!state.model) {
    setStatus("No model selected. Select a backend and model, then click Next.", "error");
    return;
  }
  if (!$("resume-text").value.trim() || !$("job-description").value.trim()) {
    setStatus("Resume or job description missing. Click Next to skip.", "error");
    return;
  }
  const generated = await generate();
  if (generated) {
    setStatus(`✓ Generated for job ${autoIndex + 1}. Review, then click Next.`, "ok");
  }
}

$("auto-process-rss").addEventListener("click", () => startAutoProcess(state.rssJobs, "RSS feed"));
$("auto-process-cron").addEventListener("click", () => startAutoProcess(state.cronJobs, "cron feed"));
$("auto-next").addEventListener("click", () => {
  if (!autoRunning) return;
  autoIndex++;
  processNextJob();
});
$("auto-stop").addEventListener("click", () => {
  autoRunning = false;
  $autoControls.classList.add("hidden");
  setStatus("Auto-processing stopped.", "");
});

/* ---------- Research settings ---------- */
const LSKEY_RESEARCH_MODE = "RT_research_mode";
const LSKEY_SEARCH_PROVIDER = "RT_search_provider";
const LSKEY_SEARCH_APIKEY = "RT_search_api_key";

const $researchMode = $("research-mode");
const $webSearchConfig = $("web-search-config");
const $llmResearchNote = $("llm-research-note");
const $researchProvider = $("research-provider");
const $researchApiKey = $("research-api-key");

// Restore
$researchMode.value = localStorage.getItem(LSKEY_RESEARCH_MODE) || "";
$researchProvider.value = localStorage.getItem(LSKEY_SEARCH_PROVIDER) || "tavily";
keyStore.get(LSKEY_SEARCH_APIKEY).then((v) => {
  $researchApiKey.value = v;
});
onResearchModeChange();

$researchMode.addEventListener("change", onResearchModeChange);
$researchProvider.addEventListener("change", () =>
  localStorage.setItem(LSKEY_SEARCH_PROVIDER, $researchProvider.value)
);
$researchApiKey.addEventListener("input", () =>
  keyStore.set(LSKEY_SEARCH_APIKEY, $researchApiKey.value)
);

function onResearchModeChange() {
  const mode = $researchMode.value;
  localStorage.setItem(LSKEY_RESEARCH_MODE, mode);
  $webSearchConfig.classList.toggle("hidden", mode !== "web");
  $llmResearchNote.classList.toggle("hidden", mode !== "llm");
}

/* ---------- MCP settings ---------- */
const LSKEY_MCP_SERVERS = "RT_mcp_servers";
const $mcpEnabled = $("mcp-enabled");
const $mcpConfig = $("mcp-config");
let mcpServers = [];

try {
  mcpServers = JSON.parse(localStorage.getItem(LSKEY_MCP_SERVERS) || "[]") || [];
} catch { mcpServers = []; }

$mcpEnabled.addEventListener("change", () => {
  $mcpConfig.classList.toggle("hidden", !$mcpEnabled.checked);
});

function renderMcpServers() {
  const list = $("mcp-server-list");
  list.innerHTML = "";
  mcpServers.forEach((s, i) => {
    const div = document.createElement("div");
    div.className = "mcp-server";
    const target = s.type === "stdio"
      ? [s.command, ...(s.args || [])].join(" ")
      : s.url;
    div.innerHTML = `<span><strong>${escapeHtml(s.name)}</strong> (${s.type}) — ${escapeHtml(target)}</span>`;
    const rm = document.createElement("button");
    rm.className = "rm";
    rm.textContent = "✕";
    rm.onclick = () => {
      mcpServers.splice(i, 1);
      saveMcpServers();
      renderMcpServers();
    };
    div.appendChild(rm);
    list.appendChild(div);
  });
}

function saveMcpServers() {
  localStorage.setItem(LSKEY_MCP_SERVERS, JSON.stringify(mcpServers));
}

$("mcp-add-btn").addEventListener("click", () => {
  const name = $("mcp-name").value.trim();
  const type = $("mcp-type").value;
  const url = $("mcp-url").value.trim();
  if (!name || !url) {
    setStatus("MCP: provide a name and URL/command.", "error");
    return;
  }
  if (type === "stdio" && !state.stdioMcpAvailable) {
    setStatus(
      "stdio MCP servers require Node.js installed. HTTP MCP servers work without it.",
      "error"
    );
    return;
  }
  const server = { name, type };
  if (type === "stdio") {
    const parts = url.split(/\s+/);
    server.command = parts[0];
    server.args = parts.slice(1);
  } else {
    server.url = url;
  }
  mcpServers.push(server);
  saveMcpServers();
  renderMcpServers();
  $("mcp-name").value = "";
  $("mcp-url").value = "";
});

$("mcp-list-tools-btn").addEventListener("click", async () => {
  if (!mcpServers.length) {
    setStatus("MCP: add at least one server first.", "error");
    return;
  }
  const btn = $("mcp-list-tools-btn");
  btn.disabled = true;
  $("mcp-tools").textContent = "Connecting…";
  try {
    const res = await fetch("/api/mcp/tools", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ servers: mcpServers }),
    });
    const data = await res.json();
    const tools = data.tools || [];
    const skipped = data.skipped || [];
    if (!tools.length) {
      let msg = data.error || "No tools found.";
      if (skipped.length) {
        msg +=
          "\nSkipped stdio server(s) (Node.js not installed): " +
          skipped.map((s) => s.name).join(", ");
      }
      $("mcp-tools").textContent = msg;
      return;
    }
    $("mcp-tools").innerHTML = "";
    if (skipped.length) {
      const warn = document.createElement("div");
      warn.className = "hint";
      warn.style.color = "#f87171";
      warn.textContent =
        "Skipped stdio server(s) (Node.js not installed): " +
        skipped.map((s) => s.name).join(", ");
      $("mcp-tools").appendChild(warn);
    }
    tools.forEach((t) => {
      const div = document.createElement("div");
      div.className = "tool";
      div.innerHTML = `<strong>${escapeHtml(t.function.name)}</strong> — ${escapeHtml(t.function.description || "")}`;
      $("mcp-tools").appendChild(div);
    });
  } catch (err) {
    $("mcp-tools").textContent = "MCP error: " + err.message;
  } finally {
    btn.disabled = false;
  }
});

renderMcpServers();

function isHttpUrl(value) {
  if (!value) return false;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* ---------- Generate ---------- */
$("generate-btn").addEventListener("click", generate);

async function generate() {
  const resumeText = $("resume-text").value.trim();
  const jobDesc = $("job-description").value.trim();
  if (!resumeText || !jobDesc) {
    setStatus("Please provide both a resume and a job description.", "error");
    return false;
  }
  if (!state.model) {
    setStatus("No model selected. Select a backend and model first.", "error");
    return false;
  }

  const btn = $("generate-btn");
  btn.disabled = true;

  const researchMode = $researchMode.value;
  const statusMsg = researchMode
    ? "Researching company, then generating… (this can take a couple of minutes)"
    : "Generating tailored resume… (this can take a minute)";
  setStatus(statusMsg, "");

  const payload = {
    resume_text: resumeText,
    job_description: jobDesc,
    backend: state.backend,
    model: state.model,
    temperature: parseFloat($("temperature").value),
    research_mode: researchMode,
  };

  // Include API key for remote backends
  const remoteApiKey = $("remote-api-key").value.trim();
  if (remoteApiKey) payload.api_key = remoteApiKey;

  // Include search params for web research
  if (researchMode === "web") {
    payload.research_provider = $researchProvider.value;
    payload.research_api_key = $researchApiKey.value;
  }

  // Include MCP settings
  payload.mcp_enabled = $mcpEnabled.checked;
  payload.mcp_servers = mcpServers;

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      setStatus(data.error || `Generation failed (HTTP ${res.status}).`, "error");
      return false;
    }
    state.resume = data.resume_md;
    state.cover = data.cover_letter;
    $("output-resume").innerHTML = renderMarkdown(data.resume_md);
    $("output-cover").innerHTML = renderMarkdown(data.cover_letter);
    $("empty-state").style.display = "none";
    setStatus("✓ Done. Review, edit, and download below.", "ok");
    switchTab("resume");
    return true;
  } catch (err) {
    setStatus("Request failed: " + err.message, "error");
    return false;
  } finally {
    btn.disabled = false;
  }
}

/* ---------- Tabs ---------- */
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

function switchTab(name) {
  state.activeTab = name;
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.tab === name)
  );
  document.querySelectorAll(".output-content").forEach((el) => {
    el.classList.toggle("active", el.id === "output-" + name);
  });
}

/* ---------- Copy & Download ---------- */
$("copy-btn").addEventListener("click", async () => {
  const text = state.activeTab === "resume" ? state.resume : state.cover;
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    setStatus("✓ Copied to clipboard.", "ok");
  } catch {
    setStatus("Could not copy to clipboard.", "error");
  }
});

$("download-docx").addEventListener("click", () => download("docx"));
$("download-txt").addEventListener("click", () => download("txt"));

function download(format) {
  const type = state.activeTab;
  const content = type === "resume" ? state.resume : state.cover;
  if (!content) return;

  // Inside the desktop app, use the native save dialog (reliable in WebView2).
  if (window.pywebview && window.pywebview.api && window.pywebview.api.save_document) {
    window.pywebview.api.save_document(content, type, format)
      .then((res) => {
        if (res && res.saved) {
          setStatus(`✓ Saved to ${res.path}`, "ok");
        } else {
          setStatus((res && res.message) || "Save cancelled.", "");
        }
      })
      .catch((err) => setStatus("Save failed: " + err.message, "error"));
    return;
  }

  // Browser fallback: blob download via the backend.
  fetch(`/download/${type}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, format }),
  })
    .then((res) => {
      if (!res.ok) throw new Error("Download failed");
      return res.blob();
    })
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${type === "resume" ? "tailored_resume" : "cover_letter"}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    })
    .catch((err) => setStatus(err.message, "error"));
}

/* ---------- Tiny markdown renderer ---------- */
function renderMarkdown(md) {
  const lines = md.split("\n");
  let html = "";
  let inList = false;
  const closeList = () => {
    if (inList) { html += "</ul>"; inList = false; }
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) { closeList(); continue; }
    const s = line.trim();
    const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    if (/^#{1,6}\s/.test(s)) {
      closeList();
      const level = s.match(/^#+/)[0].length;
      const text = esc(s.replace(/^#+\s*/, ""));
      html += `<h${Math.min(level, 3)}>${text}</h${Math.min(level, 3)}>`;
    } else if (/^[-*]\s/.test(s)) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${esc(s.replace(/^[-*]\s*/, ""))}</li>`;
    } else {
      closeList();
      html += `<p>${esc(s)}</p>`;
    }
  }
  closeList();
  return html;
}

function setStatus(msg, cls) {
  const el = $("status");
  el.textContent = msg;
  el.className = "status" + (cls ? " " + cls : "");
}

loadBackends();
