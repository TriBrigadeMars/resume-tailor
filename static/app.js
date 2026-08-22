"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  backends: [],
  backend: null,
  model: null,
  resume: "",
  cover: "",
  activeTab: "resume",
};

/* ---------- Backend detection ---------- */
async function loadBackends() {
  const statusEl = $("backend-status");
  try {
    const res = await fetch("/api/backends");
    const data = await res.json();
    state.backends = data.backends || [];

    // Prefill RSS feed URL from server config if the user hasn't set one.
    if (data.rss_feed_url && !localStorage.getItem(LSKEY_RSS_URL)) {
      $rssUrl.value = data.rss_feed_url;
      localStorage.setItem(LSKEY_RSS_URL, data.rss_feed_url);
    }

    if (!state.backends.length) {
      statusEl.textContent = "⚠ No LLM backend detected. Start Ollama or configure a remote API.";
      statusEl.className = "backend-status offline";
      $("generate-btn").disabled = true;
      populateBackendSelect();
      return;
    }

    const names = state.backends.map((b) => b.label).join(" & ");
    statusEl.textContent = `✓ Backends: ${names}`;
    statusEl.className = "backend-status online";
    populateBackendSelect();
  } catch (err) {
    statusEl.textContent = "⚠ Could not reach the app server.";
    statusEl.className = "backend-status offline";
  }
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
}

function onBackendChange() {
  const sel = $("backend-select");
  const backend = state.backends.find((b) => b.id === sel.value);
  if (!backend) return;
  state.backend = backend.id;
  localStorage.setItem("RT_backend", backend.id);

  // Show/hide API key box for remote backends
  const keyBox = $("remote-api-key-box");
  if (backend.needs_api_key) {
    keyBox.classList.remove("hidden");
    const savedApiKey = localStorage.getItem("RT_remote_api_key") || "";
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
  localStorage.setItem("RT_remote_api_key", apiKey);
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

/* ---------- RSS job feed ---------- */
const LSKEY_RSS_URL = "RT_rss_url";
const $rssUrl = $("rss-url");
const $rssStatus = $("rss-status");
const $rssJobList = $("rss-job-list");

$rssUrl.value = localStorage.getItem(LSKEY_RSS_URL) || "";
$rssUrl.addEventListener("change", () =>
  localStorage.setItem(LSKEY_RSS_URL, $rssUrl.value.trim())
);

$("rss-load-btn").addEventListener("click", loadRssFeed);
$rssUrl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") loadRssFeed();
});

async function loadRssFeed() {
  const url = $rssUrl.value.trim();
  if (!url) {
    $rssStatus.textContent = "Enter an RSS feed URL first.";
    return;
  }
  localStorage.setItem(LSKEY_RSS_URL, url);
  $rssStatus.textContent = "Loading feed…";
  $rssJobList.innerHTML = "";
  try {
    const res = await fetch("/api/rss?url=" + encodeURIComponent(url));
    const data = await res.json();
    const jobs = data.jobs || [];
    if (!jobs.length) {
      $rssStatus.textContent = data.error || "No jobs found in feed.";
      return;
    }
    $rssStatus.textContent = `${jobs.length} jobs loaded. Click one to use it.`;
    renderRssJobs(jobs);
  } catch (err) {
    $rssStatus.textContent = "Failed to load feed: " + err.message;
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
  if (job.link) parts.push(`Link: ${job.link}`);
  if (job.description) parts.push(`\nDescription:\n${job.description}`);
  $("job-description").value = parts.join("\n");
}

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
$researchApiKey.value = localStorage.getItem(LSKEY_SEARCH_APIKEY) || "";
onResearchModeChange();

$researchMode.addEventListener("change", onResearchModeChange);
$researchProvider.addEventListener("change", () =>
  localStorage.setItem(LSKEY_SEARCH_PROVIDER, $researchProvider.value)
);
$researchApiKey.addEventListener("input", () =>
  localStorage.setItem(LSKEY_SEARCH_APIKEY, $researchApiKey.value)
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
    div.innerHTML = `<span><strong>${escapeHtml(s.name)}</strong> (${s.type}) — ${escapeHtml(s.url)}</span>`;
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
    if (!tools.length) {
      $("mcp-tools").textContent = data.error || "No tools found.";
      return;
    }
    $("mcp-tools").innerHTML = "";
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
    return;
  }
  if (!state.model) {
    setStatus("No model selected. Select a backend and model first.", "error");
    return;
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
    if (data.error) {
      setStatus(data.error, "error");
      return;
    }
    state.resume = data.resume_md;
    state.cover = data.cover_letter;
    $("output-resume").innerHTML = renderMarkdown(data.resume_md);
    $("output-cover").innerHTML = renderMarkdown(data.cover_letter);
    $("empty-state").style.display = "none";
    setStatus("✓ Done. Review, edit, and download below.", "ok");
    switchTab("resume");
  } catch (err) {
    setStatus("Request failed: " + err.message, "error");
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
