"use strict";

const dashboardState = { trend: [], events: [], seenEvents: new Set(), preferences: null, settingsOpen: false };
const COLORS = { crack: "#10988d", pothole: "#ef3d3d", other: "#2563eb" };
const COLORS_DEFAULTS = { ...COLORS };

function getEffectiveColors() {
  const custom = dashboardState.preferences?.customColors;
  return custom && typeof custom === "object"
    ? { ...COLORS_DEFAULTS, ...custom }
    : { ...COLORS_DEFAULTS };
}

function setText(id, value) { document.getElementById(id).textContent = value; }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char])); }
function countFor(counts, name) { return Number(counts?.[name] ?? counts?.[name[0].toUpperCase() + name.slice(1)] ?? 0) || 0; }

function deriveViewState(data) {
  const status = ["live", "stale", "offline"].includes(data?.status) ? data.status : "offline";
  const age = data?.age_seconds == null ? null : Math.max(0, Number(data.age_seconds));
  return {
    status,
    statusLabel: status[0].toUpperCase() + status.slice(1),
    ageLabel: age == null || !Number.isFinite(age) ? "No data" : `${age.toFixed(1)} sec ago`,
    counts: data?.counts && typeof data.counts === "object" ? data.counts : {},
    hasFrame: Boolean(data?.has_frame),
    seq: data?.seq ?? null,
  };
}

function mergeEvents(existing, seen, incoming, seq) {
  const result = [...existing];
  (Array.isArray(incoming) ? incoming : []).forEach((event, index) => {
    const className = String(event.class_name ?? event.class ?? "unknown");
    const key = String(event.id ?? `${seq}-${index}-${className}`);
    if (seen.has(key)) return;
    seen.add(key);
    result.unshift({
      key,
      time: new Date().toLocaleTimeString(),
      className,
      confidence: Number(event.conf ?? event.confidence ?? 0),
      id: String(event.id ?? key),
    });
  });
  return result.slice(0, 100);
}

function appendTrendPoint(history, data, maxPoints = 40) {
  if (data?.seq == null || history.at(-1)?.seq === data.seq) return history;
  const base = history.length && Number(data.seq) < Number(history.at(-1).seq)
    ? []
    : history;
  const point = {
    seq: data.seq,
    time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    counts: { ...(data.counts || {}) },
  };
  return [...base, point].slice(-maxPoints);
}

function drawTrend(canvas, history, selectedClass = "all") {
  const width = Math.max(320, Math.round(canvas.clientWidth || canvas.width));
  const height = Math.max(180, Math.round(canvas.clientHeight || canvas.height));
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const context = canvas.getContext("2d");
  context.scale(dpr, dpr);
  context.clearRect(0, 0, width, height);
  const styles = getComputedStyle(document.documentElement);
  const muted = styles.getPropertyValue("--muted").trim() || "#61708a";
  const line = styles.getPropertyValue("--line").trim() || "#d5ddea";
  const varBg = styles.getPropertyValue("--surface").trim() || "#ffffff";
  const left = 42, right = 18, top = 18, bottom = 34;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const classes = [...new Set(history.flatMap((point) => Object.keys(point.counts || {})))];
  const visible = selectedClass === "all" ? classes : classes.filter((name) => name === selectedClass);
  const maximum = Math.max(1, ...history.flatMap((point) => visible.map((name) => Number(point.counts[name]) || 0)));
  context.strokeStyle = line;
  context.fillStyle = muted;
  context.font = "12px Segoe UI, Arial";
  for (let row = 0; row <= 4; row += 1) {
    const y = top + (plotHeight * row / 4);
    context.beginPath(); context.moveTo(left, y); context.lineTo(width - right, y); context.stroke();
    context.fillText(String(Math.round(maximum * (4 - row) / 4)), 8, y + 4);
  }
  const effectiveColors = getEffectiveColors();
  visible.forEach((name, index) => {
    const color = effectiveColors[name.toLowerCase()] || [effectiveColors.other, "#7c3aed", "#f59e0b"][index % 3];
    const points = [];
    history.forEach((point, pointIndex) => {
      const x = left + (plotWidth * pointIndex / Math.max(1, history.length - 1));
      const y = top + plotHeight - ((Number(point.counts[name]) || 0) / maximum * plotHeight);
      points.push({ x, y });
    });
    if (points.length < 2) return;

    /* Area fill gradient */
    context.beginPath();
    context.moveTo(points[0].x, top + plotHeight);
    points.forEach((p) => context.lineTo(p.x, p.y));
    context.lineTo(points.at(-1).x, top + plotHeight);
    context.closePath();
    const gradient = context.createLinearGradient(0, top, 0, top + plotHeight);
    gradient.addColorStop(0, color + "40");
    gradient.addColorStop(1, color + "05");
    context.fillStyle = gradient;
    context.fill();

    /* Line */
    context.beginPath();
    context.moveTo(points[0].x, points[0].y);
    points.forEach((p) => context.lineTo(p.x, p.y));
    context.strokeStyle = color;
    context.lineWidth = 2.5;
    context.shadowColor = color + "50";
    context.shadowBlur = 6;
    context.stroke();
    context.shadowBlur = 0;

    /* Data dots */
    points.forEach((p, i) => {
      if (i === 0 || i === points.length - 1 || i % Math.max(1, Math.floor(points.length / 8)) === 0) {
        context.beginPath();
        context.arc(p.x, p.y, 4, 0, Math.PI * 2);
        context.fillStyle = color;
        context.fill();
        context.strokeStyle = varBg;
        context.lineWidth = 2;
        context.stroke();
      }
    });
  });
  if (!history.length) context.fillText("Waiting for trend data", left + 12, top + plotHeight / 2);
  else {
    context.fillText(history[0].time, left, height - 10);
    const last = history.at(-1).time;
    context.fillText(last, width - right - context.measureText(last).width, height - 10);
  }
}

function loadPreferences() {
  const defaults = { classFilter: "all", refreshInterval: 500, theme: "dark", customColors: {} };
  try { return { ...defaults, ...JSON.parse(localStorage.getItem("project4Preferences") || "{}") }; }
  catch { return defaults; }
}

function savePreferences(preferences) {
  const rawColors = preferences.customColors;
  const cleanColors = rawColors && typeof rawColors === "object"
    ? Object.fromEntries(
        Object.entries(rawColors).filter(([, value]) => typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value))
      )
    : {};
  const clean = {
    classFilter: String(preferences.classFilter || "all"),
    refreshInterval: Math.max(250, Math.min(5000, Number(preferences.refreshInterval) || 500)),
    theme: preferences.theme === "dark" ? "dark" : "light",
    customColors: cleanColors,
  };
  localStorage.setItem("project4Preferences", JSON.stringify(clean));
  document.documentElement.dataset.theme = clean.theme;
  dashboardState.preferences = clean;
  return clean;
}

function refreshClassOptions(counts) {
  const select = document.getElementById("class-filter");
  Object.keys(counts || {}).forEach((name) => {
    if (![...select.options].some((option) => option.value === name)) {
      select.add(new Option(name, name));
    }
  });
  select.value = dashboardState.preferences.classFilter;
}

function renderEvents(events, selectedClass) {
  const visible = events.filter((event) => {
    return selectedClass === "all" || event.className === selectedClass;
  });
  document.getElementById("event-rows").innerHTML = visible.length
    ? visible.map((event) => `<tr><td>${escapeHtml(event.time)}</td><td>${escapeHtml(event.className)}</td><td>${(event.confidence * 100).toFixed(1)}%</td><td>${escapeHtml(event.id)}</td></tr>`).join("")
    : '<tr><td colspan="4">No matching events</td></tr>';
  setText("event-summary", `${visible.length} of ${events.length} events`);
}

function exportEventsCsv(events) {
  const csvCell = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const rows = [["Time", "Class", "Confidence", "Event ID"]];
  events.forEach((event) => rows.push([
    event.time,
    event.className,
    `${(event.confidence * 100).toFixed(1)}%`,
    event.id,
  ]));
  const csv = rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `road-defect-events-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function renderDashboard(data) {
  const view = deriveViewState(data);
  const status = document.getElementById("status");
  status.className = `connection ${view.status}`;
  setText("status-text", view.statusLabel);
  setText("last-update", view.ageLabel);
  setText("sequence", `seq: ${view.seq ?? "--"}`);
  setText("frame-source", `source: ${data.frame_source || "--"}`);
  setText("total-count", Object.values(view.counts).reduce((sum, value) => sum + (Number(value) || 0), 0));
  setText("crack-count", countFor(view.counts, "crack"));
  setText("pothole-count", countFor(view.counts, "pothole"));
  refreshClassOptions(view.counts);
  dashboardState.trend = appendTrendPoint(dashboardState.trend, data);
  dashboardState.events = mergeEvents(dashboardState.events, dashboardState.seenEvents, data.events, view.seq);
  const selected = dashboardState.preferences.classFilter;
  setText("trend-label", selected === "all" ? "All classes" : selected);
  drawTrend(document.getElementById("trend-canvas"), dashboardState.trend, selected);
  renderEvents(dashboardState.events, selected);
  const image = document.getElementById("latest-frame");
  const placeholder = document.getElementById("frame-placeholder");
  if (view.hasFrame) {
    image.src = `/latest.jpg?v=${view.seq ?? Date.now()}`;
    image.style.display = "block";
    placeholder.style.display = "none";
  } else {
    image.style.display = "none";
    placeholder.style.display = "grid";
  }
}

async function poll() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderDashboard(await response.json());
  } catch { renderDashboard({ status: "offline", counts: {}, events: [], has_frame: false }); }
  window.setTimeout(poll, dashboardState.preferences.refreshInterval);
}

function rebuildSettingsPanel() {
  const panel = document.getElementById("settings-panel");
  const effectiveColors = getEffectiveColors();
  const knownClasses = new Set(["crack", "pothole", "other"]);
  dashboardState.trend.forEach((point) => Object.keys(point.counts || {}).forEach((name) => knownClasses.add(name)));
  dashboardState.events.forEach((event) => knownClasses.add(event.className));

  panel.innerHTML = "";
  const colorsSection = document.createElement("div");
  colorsSection.className = "settings-section";
  colorsSection.innerHTML = "<h3>Category Colors</h3>";
  const colorsContainer = document.createElement("div");
  colorsContainer.id = "color-pickers";
  knownClasses.forEach((name) => {
    const row = document.createElement("div");
    row.className = "color-row";
    const hex = effectiveColors[name] || effectiveColors.other;
    row.innerHTML = `
      <label for="color-${name}">${escapeHtml(name)}</label>
      <input type="color" id="color-${name}" value="${hex}">
    `;
    row.querySelector("input").addEventListener("input", (event) => {
      const customColors = { ...(dashboardState.preferences.customColors || {}), [name]: event.target.value };
      savePreferences({ ...dashboardState.preferences, customColors });
      const sel = document.getElementById("class-filter").value;
      drawTrend(document.getElementById("trend-canvas"), dashboardState.trend, sel);
    });
    colorsContainer.appendChild(row);
  });
  colorsSection.appendChild(colorsContainer);
  const colorActions = document.createElement("div");
  colorActions.className = "color-actions";
  colorActions.innerHTML = '<button type="button" id="reset-colors">Reset Colors</button>';
  colorsSection.appendChild(colorActions);
  panel.appendChild(colorsSection);

  document.getElementById("reset-colors").addEventListener("click", () => {
    savePreferences({ ...dashboardState.preferences, customColors: {} });
    rebuildSettingsPanel();
    const sel = document.getElementById("class-filter").value;
    drawTrend(document.getElementById("trend-canvas"), dashboardState.trend, sel);
  });
}

function bindControls() {
  const filter = document.getElementById("class-filter");
  const refresh = document.getElementById("refresh-select");
  const theme = document.getElementById("theme-toggle");
  filter.value = dashboardState.preferences.classFilter;
  refresh.value = String(dashboardState.preferences.refreshInterval);
  theme.textContent = dashboardState.preferences.theme === "dark" ? "Light Theme" : "Dark Theme";
  filter.addEventListener("change", () => { savePreferences({ ...dashboardState.preferences, classFilter: filter.value }); setText("trend-label", filter.value === "all" ? "All classes" : filter.value); renderEvents(dashboardState.events, filter.value); drawTrend(document.getElementById("trend-canvas"), dashboardState.trend, filter.value); });
  refresh.addEventListener("change", () => savePreferences({ ...dashboardState.preferences, refreshInterval: Number(refresh.value) }));
  theme.addEventListener("click", () => { const next = dashboardState.preferences.theme === "dark" ? "light" : "dark"; savePreferences({ ...dashboardState.preferences, theme: next }); theme.textContent = next === "dark" ? "Light Theme" : "Dark Theme"; drawTrend(document.getElementById("trend-canvas"), dashboardState.trend, filter.value); });
  document.getElementById("export-events").addEventListener("click", () => exportEventsCsv(dashboardState.events));
  document.getElementById("clear-events").addEventListener("click", () => { dashboardState.events = []; dashboardState.seenEvents.clear(); renderEvents([], filter.value); });

  /* ---- Settings panel ---- */
  const settingsBtn = document.createElement("button");
  settingsBtn.type = "button";
  settingsBtn.className = "settings-btn";
  settingsBtn.textContent = "⚙ Settings";
  document.querySelector(".controls").appendChild(settingsBtn);

  const settingsPanel = document.createElement("div");
  settingsPanel.className = "settings-panel";
  settingsPanel.id = "settings-panel";
  document.querySelector(".topbar").appendChild(settingsPanel);

  settingsBtn.addEventListener("click", () => {
    dashboardState.settingsOpen = !dashboardState.settingsOpen;
    settingsPanel.classList.toggle("open", dashboardState.settingsOpen);
    if (dashboardState.settingsOpen) rebuildSettingsPanel();
  });
  document.addEventListener("click", (event) => {
    if (dashboardState.settingsOpen && !settingsBtn.contains(event.target) && !settingsPanel.contains(event.target)) {
      dashboardState.settingsOpen = false;
      settingsPanel.classList.remove("open");
    }
  });
}

function runBrowserSelfCheck() {
  const originalPreferences = localStorage.getItem("project4Preferences");
  const sample = { status: "live", seq: 9, age_seconds: 0.4, counts: { crack: 2, pothole: 1 }, events: [{ id: "e-1", class_name: "crack", conf: 0.8 }] };
  const checks = [];
  try { checks.push(deriveViewState(sample).statusLabel === "Live"); } catch { checks.push(false); }
  try { checks.push(mergeEvents([], new Set(), sample.events, 9).length === 1); } catch { checks.push(false); }
  try { const history = appendTrendPoint([], sample); drawTrend(document.getElementById("trend-canvas"), history); checks.push(history.length === 1); } catch { checks.push(false); }
  try { const saved = savePreferences({ classFilter: "crack", refreshInterval: 500, theme: "dark" }); checks.push(saved.theme === "dark" && JSON.parse(localStorage.getItem("project4Preferences")).classFilter === "crack"); } catch { checks.push(false); }
  setText("check-result", checks.every(Boolean) ? "Tasks 1-4: PASS" : "Tasks 1-4: NOT COMPLETE");
  if (originalPreferences == null) localStorage.removeItem("project4Preferences");
  else localStorage.setItem("project4Preferences", originalPreferences);
  dashboardState.preferences = loadPreferences();
  document.documentElement.dataset.theme = dashboardState.preferences.theme;
}

dashboardState.preferences = savePreferences(loadPreferences());
if (document.body.dataset.page === "dashboard") { bindControls(); poll(); }
else if (document.body.dataset.page === "self-check") runBrowserSelfCheck();

Object.assign(window, { deriveViewState, mergeEvents, appendTrendPoint, drawTrend, savePreferences, exportEventsCsv });
