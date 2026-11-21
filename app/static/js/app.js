/* Smart Study Planner – front end (Tier 1). Each page sets <body data-page="..."> and calls the REST API. */
"use strict";

// ---------- shared helpers ----------
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode: keep in memory only */ } },
  del(k) { try { localStorage.removeItem(k); } catch (e) {} },
};
const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const COLORS = ["#2563eb", "#db2777", "#7c3aed", "#16a34a", "#d97706", "#0891b2"];
const BG = ["#dbeafe", "#fce7f3", "#ede9fe", "#dcfce7", "#fef3c7", "#cffafe"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function user() { try { return JSON.parse(store.get("ssp_user") || "null"); } catch (e) { return null; } }

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = store.get("ssp_token");
  if (token) headers.Authorization = "Bearer " + token;
  const res = await fetch("/api" + path, { method: opts.method || "GET", headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (res.status === 401 && !path.startsWith("/auth/")) { logout(); return Promise.reject({ error: "Please log in." }); }
  const type = res.headers.get("Content-Type") || "";
  const data = type.includes("json") ? await res.json() : await res.text();
  if (!res.ok) return Promise.reject(typeof data === "object" ? { ...data, status: res.status } : { error: data, status: res.status });
  return data;
}

async function download(path, filename) {
  const res = await fetch("/api" + path, { headers: { Authorization: "Bearer " + store.get("ssp_token") } });
  if (!res.ok) return toast("Download failed.", "bad");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await res.blob());
  a.download = filename;
  a.click();
}

function toast(text, kind = "ok") {
  let t = $("#toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
  t.className = "msg " + kind;
  t.textContent = text;
  t.style.display = "block";
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.style.display = "none"), 5000);
}

function showFieldErrors(form, fields = {}) {
  form.querySelectorAll(".err").forEach((e) => (e.textContent = ""));
  form.querySelectorAll(".bad").forEach((e) => e.classList.remove("bad"));
  Object.entries(fields).forEach(([name, text]) => {
    const input = form.querySelector(`[name="${name}"]`);
    if (input) input.classList.add("bad");
    const box = form.querySelector(`[data-err="${name}"]`);
    if (box) box.textContent = text;
  });
}

function logout() { store.del("ssp_token"); store.del("ssp_user"); location.href = "/index.html"; }

function shell(active) {
  const u = user();
  if (!u) { location.href = "/index.html"; throw new Error("not logged in"); }
  const menus = {
    student: [["dashboard", "Dashboard"], ["plan", "Study Plan"], ["tasks", "Courses & Tasks"], ["availability", "Availability"], ["sharing", "Sharing"]],
    advisor: [["advisor", "My Students"]],
    admin: [["admin", "Admin Console"]],
  }[u.role];
  if (!menus.some(([p]) => p === active)) { location.href = "/" + menus[0][0] + ".html"; throw new Error("wrong role"); }
  $("#side").innerHTML = `<div class="logo">📘 Smart Study Planner</div>` +
    menus.map(([p, t]) => `<a href="/${p}.html" class="${p === active ? "on" : ""}">${t}</a>`).join("") +
    `<div class="who">${esc(u.full_name)}<br>${esc(u.role)}<button class="ghost small" id="logout">Log out</button></div>`;
  $("#logout").onclick = logout;
  return u;
}

const fmtDate = (s) => new Date(s.replace(" ", "T")).toLocaleString("en-GB", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function monday(d) { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; }

// ---------- pages ----------
const pages = {};

// Login, registration and password reset (UC-01)
pages.login = function () {
  const u = user();
  if (u) location.href = u.role === "student" ? "/dashboard.html" : (u.role === "advisor" ? "/advisor.html" : "/admin.html");
  const reset = new URLSearchParams(location.search).get("reset");
  const show = (id) => ["#loginForm", "#registerForm", "#forgotForm", "#resetForm"].forEach((f) => $(f).classList.toggle("hidden", f !== id));
  if (reset) show("#resetForm");
  $("#toRegister").onclick = (e) => { e.preventDefault(); show("#registerForm"); };
  $("#toForgot").onclick = (e) => { e.preventDefault(); show("#forgotForm"); };
  document.querySelectorAll(".toLogin").forEach((a) => (a.onclick = (e) => { e.preventDefault(); show("#loginForm"); }));
  const done = (d) => { store.set("ssp_token", d.token); store.set("ssp_user", JSON.stringify(d.user)); pages.login(); };

  $("#loginForm").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    $("#loginError").classList.add("hidden");
    try { done(await api("/auth/login", { method: "POST", body: { email: f.email.value, password: f.password.value } })); }
    catch (err) { $("#loginError").textContent = err.error; $("#loginError").classList.remove("hidden"); }
  };
  $("#registerForm").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    try { done(await api("/auth/register", { method: "POST", body: { full_name: f.full_name.value, email: f.email.value, password: f.password.value } })); }
    catch (err) { showFieldErrors(f, err.fields); if (!err.fields) toast(err.error, "bad"); }
  };
  $("#forgotForm").onsubmit = async (e) => {
    e.preventDefault();
    const d = await api("/auth/forgot-password", { method: "POST", body: { email: e.target.email.value } });
    toast(d.message); show("#loginForm");
  };
  $("#resetForm").onsubmit = async (e) => {
    e.preventDefault();
    try { const d = await api("/auth/reset-password", { method: "POST", body: { token: reset, password: e.target.password.value } }); toast(d.message); history.replaceState(null, "", "/index.html"); show("#loginForm"); }
    catch (err) { toast(err.error, "bad"); }
  };
};

// Progress dashboard (UC-06, UC-11)
pages.dashboard = async function () {
  shell("dashboard");
  const [p, ranked] = await Promise.all([api("/progress"), api("/tasks/ranked")]);
  $("#cards").innerHTML = [
    ["Completion rate (sessions due so far)", p.week.completion_rate + "%", p.week.completion_rate >= 80 ? "var(--green)" : ""],
    ["Study streak", p.streak + (p.streak === 1 ? " day" : " days"), ""],
    ["Completed / planned this week", `${p.week.completed} / ${p.week.planned}`, ""],
    ["Overdue tasks", p.overdue_tasks, p.overdue_tasks ? "var(--red)" : ""],
  ].map(([t, v, c]) => `<div class="card stat"><small>${t}</small><b style="color:${c}">${v}</b></div>`).join("");
  const max = Math.max(1, ...p.history.map((h) => h.planned));
  $("#weekChart").innerHTML = p.history.map((h) => `<div class="wk"><div class="pair">
      <div title="Planned ${h.planned}" style="height:${(h.planned / max) * 130}px;background:#cbd5e1"></div>
      <div title="Completed ${h.completed}" style="height:${(h.completed / max) * 130}px;background:var(--blue)"></div></div>
      ${new Date(h.week_start).toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}</div>`).join("");
  $("#courseChart").innerHTML = p.by_course.length ? p.by_course.map((c) => `<div class="hbar"><div style="width:62px">${esc(c.course_code)}</div>
      <div class="track"><div class="fill" style="width:${c.completion_rate}%;background:${c.completion_rate >= 80 ? "var(--green)" : "#f59e0b"}"></div></div>
      <div style="width:42px">${c.completion_rate}%</div></div>`).join("") : `<p class="muted">No finished sessions yet.</p>`;
  $("#ranked").innerHTML = ranked.length ? ranked.slice(0, 6).map((r, i) => `<tr><td>${i + 1}</td><td>${esc(r.course_code)} ${esc(r.title)}
      ${r.at_risk ? '<span class="pill red">at risk</span>' : ""}</td><td>${esc(r.reason)}</td><td>${r.score}</td></tr>`).join("")
    : `<tr><td colspan="4" class="muted">No open tasks. Add tasks under Courses &amp; Tasks.</td></tr>`;
  $("#upcoming").innerHTML = p.upcoming.map((u) => `<div>📌 ${fmtDate(u.deadline)} · ${esc(u.course_code)} ${esc(u.title)}</div>`).join("") || `<p class="muted">Nothing due.</p>`;
};

// Study plan timetable (UC-05, UC-07, UC-08, UC-09, UC-15)
pages.plan = function () {
  shell("plan");
  let week = monday(new Date());
  const H0 = 7, H1 = 23, PX = 34;
  let selected = null;
  const courseColor = {};

  async function load() {
    const d = await api("/plans?week=" + iso(week));
    const end = new Date(week); end.setDate(end.getDate() + 6);
    $("#weekLabel").textContent = `${week.toLocaleDateString("en-GB", { day: "2-digit", month: "short" })} – ${end.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}`;
    $("#risk").innerHTML = d.at_risk.map((t) => `<div class="msg warn">⚠ ${esc(t.course_code)} ${esc(t.title)} is at risk: there is not enough free time before ${fmtDate(t.deadline)}. Try raising your daily study limit or adding free time.</div>`).join("");
    let html = `<div class="hd"></div>` + [0, 1, 2, 3, 4, 5, 6].map((i) => { const x = new Date(week); x.setDate(x.getDate() + i); return `<div class="hd">${DAYS[i]} ${x.getDate()}</div>`; }).join("");
    html += `<div class="hours">${Array.from({ length: H1 - H0 }, (_, i) => `<div style="height:${PX}px">${H0 + i}:00</div>`).join("")}</div>`;
    for (let i = 0; i < 7; i++) {
      const day = new Date(week); day.setDate(day.getDate() + i);
      const items = d.sessions.filter((s) => s.planned_start.startsWith(iso(day)));
      html += `<div class="col" style="height:${(H1 - H0) * PX}px">` + items.map((s) => {
        if (!(s.course_code in courseColor)) courseColor[s.course_code] = Object.keys(courseColor).length % COLORS.length;
        const c = courseColor[s.course_code];
        const st = new Date(s.planned_start.replace(" ", "T")), en = new Date(s.planned_end.replace(" ", "T"));
        const top = (st.getHours() + st.getMinutes() / 60 - H0) * PX, h = Math.max(((en - st) / 3600000) * PX - 2, 14);
        const label = (s.is_locked ? "🔒 " : "") + (s.session_type === "review" ? "REVIEW · " : "") + `${s.course_code} · ${s.title}`;
        return `<div class="sess ${s.session_type} ${s.status}" data-id="${s.session_id}" style="top:${top}px;height:${h}px;background:${BG[c]};border-color:${COLORS[c]}" title="${esc(label)}">${esc(label)}</div>`;
      }).join("") + `</div>`;
    }
    $("#tt").innerHTML = html;
    $("#legend").innerHTML = Object.entries(courseColor).map(([k, c]) => `<span style="white-space:nowrap"><span style="color:${COLORS[c]}">■</span> ${esc(k)}</span>`).join(" &nbsp; ") +
      `<br>┅ dashed border = review session<br>🔒 = locked session<br>faded = completed, crossed out = missed`;
    document.querySelectorAll(".sess").forEach((el) => (el.onclick = () => pick(d.sessions.find((s) => s.session_id == el.dataset.id))));
    if (selected) pick(d.sessions.find((s) => s.session_id === selected.session_id));
  }

  function pick(s) {
    selected = s || null;
    document.querySelectorAll(".sess").forEach((el) => el.classList.toggle("sel", !!(s && el.dataset.id == s.session_id)));
    if (!s) { $("#detail").innerHTML = `<p class="muted">Click a session to see its details.</p>`; return; }
    const mins = (new Date(s.planned_end.replace(" ", "T")) - new Date(s.planned_start.replace(" ", "T"))) / 60000;
    $("#detail").innerHTML = `<h2>${esc(s.course_code)} · ${esc(s.title)}</h2>
      <div class="muted">${s.session_type === "review" ? `Review session (${s.review_offset_days} day(s) before the exam)<br>` : ""}
      ${fmtDate(s.planned_start)} · ${mins} min<br>Status: <b>${s.status.replace("_", " ")}</b>${s.reschedule_count ? ` · moved ${s.reschedule_count}×` : ""}
      <br>Task due ${fmtDate(s.deadline)} · priority score ${s.priority_score ?? "–"}</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px">
        <button class="green small" data-st="completed">✓ Completed</button>
        <button class="ghost small" data-st="partly_completed">½ Partly</button>
        <button class="red small" data-st="missed">✗ Missed</button>
        <button class="ghost small" id="lockBtn">${s.is_locked ? "🔓 Unlock" : "🔒 Lock"}</button></div>`;
    document.querySelectorAll("[data-st]").forEach((b) => (b.onclick = async () => {
      try { const r = await api(`/sessions/${s.session_id}/status`, { method: "PATCH", body: { status: b.dataset.st } }); toast(r.message, r.action === "none" ? "warn" : "ok"); load(); }
      catch (err) { toast(err.error, "bad"); }
    }));
    $("#lockBtn").onclick = async () => { await api(`/sessions/${s.session_id}/lock`, { method: "PATCH", body: { locked: !s.is_locked } }); load(); };
  }

  $("#prev").onclick = () => { week.setDate(week.getDate() - 7); selected = null; pick(null); load(); };
  $("#next").onclick = () => { week.setDate(week.getDate() + 7); selected = null; pick(null); load(); };
  $("#generate").onclick = async () => {
    try {
      const r = await api("/plans/generate", { method: "POST" });
      toast(`Plan ready: ${r.sessions_created} sessions, including ${r.review_sessions} review session(s).` + (r.at_risk.length ? ` ${r.at_risk.length} task(s) at risk.` : ""), r.at_risk.length ? "warn" : "ok");
      load();
    } catch (err) { toast(err.error, "bad"); if (err.code === "NO_AVAILABILITY") setTimeout(() => (location.href = "/availability.html"), 1500); }
  };
  $("#export").onclick = () => download("/plans/export.ics?week=" + iso(week), `study_plan_${iso(week)}.ics`);
  pick(null);
  load();
};

// Courses and tasks (UC-02, UC-03)
pages.tasks = function () {
  shell("tasks");
  let courses = [], current = null;
  async function loadCourses() {
    courses = await api("/courses");
    if (!current && courses.length) current = courses[0].course_id;
    $("#courseList").innerHTML = courses.map((c) => `<div class="list-item ${c.course_id === current ? "on" : ""}" data-id="${c.course_id}">${esc(c.course_code)} ${esc(c.course_name)}</div>`).join("") || `<p class="muted">No courses yet.</p>`;
    document.querySelectorAll(".list-item").forEach((el) => (el.onclick = () => { current = +el.dataset.id; loadCourses(); }));
    loadTasks();
  }
  async function loadTasks() {
    const c = courses.find((x) => x.course_id === current);
    $("#taskArea").classList.toggle("hidden", !c);
    if (!c) return;
    $("#courseTitle").textContent = `${c.course_code} ${c.course_name}`;
    $("#weightWarn").classList.toggle("hidden", c.total_weight <= 100);
    $("#weightWarn").textContent = `⚠ The total grade weight of ${c.course_code} tasks is ${c.total_weight}%. Please check the weights.`;
    const tasks = await api(`/courses/${current}/tasks`);
    $("#taskRows").innerHTML = tasks.map((t) => `<tr><td>${esc(t.title)} ${t.at_risk ? '<span class="pill red">at risk</span>' : ""}</td><td>${t.task_type}</td>
      <td>${fmtDate(t.deadline)}</td><td>${t.grade_weight}%</td><td>${t.difficulty}</td><td>${t.estimated_hours} h</td>
      <td><span class="pill ${t.status === "done" ? "green" : "amber"}">${t.status.replace("_", " ")}</span></td>
      <td>${t.status !== "done" ? `<button class="ghost small" data-done="${t.task_id}">Mark done</button>` : ""} <button class="ghost small" data-del="${t.task_id}" aria-label="Delete">🗑</button></td></tr>`).join("")
      || `<tr><td colspan="8" class="muted">No tasks yet for this course.</td></tr>`;
    document.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => { if (confirm("Delete this task?")) { await api(`/tasks/${b.dataset.del}`, { method: "DELETE" }); toast("Task deleted."); loadCourses(); } }));
    document.querySelectorAll("[data-done]").forEach((b) => (b.onclick = async () => { await api(`/tasks/${b.dataset.done}`, { method: "PUT", body: { status: "done" } }); toast("Task marked as done."); loadCourses(); }));
  }
  $("#courseForm").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    try { const c = await api("/courses", { method: "POST", body: { course_code: f.course_code.value, course_name: f.course_name.value, credit_hours: f.credit_hours.value } }); current = c.course_id; f.reset(); showFieldErrors(f); toast("Course added."); loadCourses(); }
    catch (err) { showFieldErrors(f, err.fields); }
  };
  $("#taskForm").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    const body = Object.fromEntries(new FormData(f).entries());
    try {
      const r = await api(`/courses/${current}/tasks`, { method: "POST", body });
      f.reset(); showFieldErrors(f);
      toast(r.warning || "Task saved." + (r.plan ? " Your study plan was updated." : ""), r.warning ? "warn" : "ok");
      loadCourses();
    } catch (err) { showFieldErrors(f, err.fields); }
  };
  loadCourses();
};

// Weekly availability and settings (UC-04)
pages.availability = function () {
  shell("availability");
  let blocks = [];
  function draw() {
    $("#blocks").innerHTML = DAYS.map((d, i) => `<tr><td><b>${d}</b></td><td>${blocks.filter((b) => b.day_of_week === i)
      .map((b) => `<span class="pill green" style="margin:2px">${b.start_time.slice(0, 5)}–${b.end_time.slice(0, 5)} <a href="#" data-rm="${blocks.indexOf(b)}" aria-label="Remove">✕</a></span>`).join("") || '<span class="muted">no free time</span>'}</td></tr>`).join("");
    document.querySelectorAll("[data-rm]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); blocks.splice(+a.dataset.rm, 1); draw(); }));
    const mins = blocks.reduce((s, b) => s + (toMin(b.end_time) - toMin(b.start_time)), 0);
    $("#weekTotal").textContent = `${(mins / 60).toFixed(1)} h of free time per week`;
  }
  const toMin = (t) => +t.slice(0, 2) * 60 + +t.slice(3, 5);
  async function load() {
    const d = await api("/availability");
    blocks = d.blocks.map((b) => ({ day_of_week: b.day_of_week, start_time: b.start_time, end_time: b.end_time }));
    const f = $("#settingsForm");
    f.daily_study_limit.value = d.settings.daily_study_limit;
    f.session_length.value = d.settings.session_length;
    f.reminder_lead_time.value = d.settings.reminder_lead_time;
    f.quiet_hours_start.value = (d.settings.quiet_hours_start || "").slice(0, 5);
    f.quiet_hours_end.value = (d.settings.quiet_hours_end || "").slice(0, 5);
    $("#busyRows").innerHTML = d.busy_events.map((b) => `<tr><td>${esc(b.title)}</td><td>${fmtDate(b.start_at)} – ${b.end_at.slice(11, 16)}</td><td><button class="ghost small" data-busy="${b.event_id}">Remove</button></td></tr>`).join("") || `<tr><td colspan="3" class="muted">No busy events.</td></tr>`;
    document.querySelectorAll("[data-busy]").forEach((b) => (b.onclick = async () => { await api(`/busy-events/${b.dataset.busy}`, { method: "DELETE" }); load(); }));
    draw();
  }
  $("#blockForm").onsubmit = (e) => {
    e.preventDefault();
    const f = e.target;
    if (f.end_time.value <= f.start_time.value) return toast("The end time must be after the start time.", "bad");
    blocks.push({ day_of_week: +f.day_of_week.value, start_time: f.start_time.value + ":00", end_time: f.end_time.value + ":00" });
    draw();
  };
  $("#settingsForm").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    const settings = { daily_study_limit: f.daily_study_limit.value, session_length: f.session_length.value, reminder_lead_time: f.reminder_lead_time.value,
      quiet_hours_start: f.quiet_hours_start.value || null, quiet_hours_end: f.quiet_hours_end.value || null };
    try { const r = await api("/availability", { method: "PUT", body: { blocks, settings } }); showFieldErrors(f); toast("Availability saved." + (r.plan ? " Your study plan was updated." : "")); }
    catch (err) { showFieldErrors(f, err.fields); toast(err.error, "bad"); }
  };
  $("#busyForm").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    try { await api("/busy-events", { method: "POST", body: { title: f.title.value, start_at: f.start_at.value, end_at: f.end_at.value } }); f.reset(); toast("Busy event added. The plan avoids this time."); load(); }
    catch (err) { toast(err.error, "bad"); }
  };
  load();
};

// Share progress with an advisor (UC-12)
pages.sharing = function () {
  shell("sharing");
  let chosen = null;
  async function load() {
    const d = await api("/sharing");
    $("#status").innerHTML = d.sharing_on ? `<span class="pill green">Sharing is ON</span>` : `<span class="pill">Sharing is OFF</span>`;
    $("#history").innerHTML = d.history.map((h) => `<tr><td>${esc(h.advisor_name)}</td><td>${fmtDate(h.granted_at)}</td><td>${h.revoked_at ? fmtDate(h.revoked_at) : "–"}</td>
      <td>${h.is_active ? `<span class="pill green">Active</span> <button class="ghost small" data-off="${h.consent_id}">Turn off</button>` : '<span class="pill">Revoked</span>'}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">You have not shared your progress with anyone.</td></tr>`;
    document.querySelectorAll("[data-off]").forEach((b) => (b.onclick = async () => { const r = await api(`/sharing/${b.dataset.off}`, { method: "DELETE" }); toast(r.message); load(); }));
  }
  $("#search").oninput = async (e) => {
    chosen = null; $("#confirm").disabled = true;
    const list = await api("/advisors?q=" + encodeURIComponent(e.target.value));
    $("#results").innerHTML = list.map((a) => `<div class="list-item" data-id="${a.user_id}"><b>${esc(a.full_name)}</b> · ${esc(a.department)} · ${esc(a.email)}</div>`).join("") ||
      (e.target.value.length >= 2 ? `<p class="muted">Advisor not found.</p>` : "");
    document.querySelectorAll("#results .list-item").forEach((el) => (el.onclick = () => {
      document.querySelectorAll("#results .list-item").forEach((x) => x.classList.remove("on"));
      el.classList.add("on"); chosen = +el.dataset.id; $("#confirm").disabled = false;
    }));
  };
  $("#confirm").onclick = async () => {
    try { const r = await api("/sharing", { method: "POST", body: { advisor_id: chosen } }); toast(r.message); $("#results").innerHTML = ""; $("#search").value = ""; load(); }
    catch (err) { toast(err.error, "bad"); }
  };
  $("#exportData").onclick = () => download("/me/export", "my_study_data.csv");
  $("#deleteAccount").onclick = async () => {
    if (!window.confirm("Delete your account and all your study data permanently? This cannot be undone.")) return;
    try { await api("/me", { method: "DELETE" }); logout(); } catch (e) { toast(e.error || "Could not delete the account.", "bad"); }
  };
  load();
};

// Advisor portal (UC-13)
pages.advisor = function () {
  shell("advisor");
  async function load() {
    const list = await api("/advisor/students");
    $("#students").innerHTML = list.map((s) => `<tr class="list-item" data-id="${s.user_id}"><td><b>${esc(s.full_name)}</b></td>
      ${s.sharing ? `<td>${s.completion_rate}%</td><td>${s.overdue_tasks}</td>` : `<td colspan="2" class="muted">sharing turned off</td>`}</tr>`).join("") || `<tr><td colspan="3" class="muted">No students share their progress with you yet.</td></tr>`;
    document.querySelectorAll("#students .list-item").forEach((el) => (el.onclick = () => show(+el.dataset.id)));
  }
  async function show(id) {
    try {
      const s = await api(`/advisor/students/${id}/summary`);
      const diff = (a, b, good) => { const d = +(a - b).toFixed(1); return d === 0 ? "–" : `<span style="color:${(d > 0) === good ? "var(--green)" : "var(--red)"}">${d > 0 ? "▲" : "▼"} ${Math.abs(d)}</span>`; };
      const pts = s.trend.map((t, i) => [20 + i * 120, 100 - t.completion_rate * 0.8]);
      $("#summary").innerHTML = `<h2>Weekly Progress Summary – ${esc(s.student_name)}</h2>
        <table><tr><th>Measure</th><th>This week</th><th>Last week</th><th>Change</th></tr>
        <tr><td>Session completion rate</td><td>${s.completion_rate}%</td><td>${s.last_week_completion_rate}%</td><td>${diff(s.completion_rate, s.last_week_completion_rate, true)}</td></tr>
        <tr><td>Study streak</td><td>${s.streak} days</td><td>–</td><td>–</td></tr>
        <tr><td>Overdue tasks</td><td>${s.overdue_tasks}</td><td>–</td><td>–</td></tr></table>
        <h2 style="margin-top:14px">Completion rate – last 5 weeks</h2>
        <svg width="540" height="120" role="img" aria-label="Completion rate trend"><polyline fill="none" stroke="#2563eb" stroke-width="3" points="${pts.map((p) => p.join(",")).join(" ")}"/>
        ${s.trend.map((t, i) => `<circle cx="${pts[i][0]}" cy="${pts[i][1]}" r="5" fill="#2563eb"/><text x="${pts[i][0] - 14}" y="${pts[i][1] - 9}" font-size="11">${t.completion_rate}%</text><text x="${pts[i][0] - 18}" y="117" font-size="11" fill="#64748b">${t.week_start.slice(5)}</text>`).join("")}</svg>
        <p class="muted">🔒 Task titles, notes and timetables are not shared. Only this summary is visible.</p>`;
    } catch (err) { $("#summary").innerHTML = `<div class="msg warn">${esc(err.error)}</div>`; }
  }
  load();
};

// Admin console (UC-14)
pages.admin = function () {
  shell("admin");
  async function load() {
    const [st, users, logs] = await Promise.all([api("/admin/stats"), api(`/admin/users?q=${encodeURIComponent($("#q").value)}&role=${$("#role").value}&status=${$("#status").value}`), api("/admin/logs")]);
    $("#stats").innerHTML = [["Registered users", st.registered_users], ["Students", st.students], ["Plans generated", st.plans_generated], ["Notifications delivered", st.delivery_rate + "%"]]
      .map(([t, v]) => `<div class="card stat"><small>${t}</small><b>${v}</b></div>`).join("");
    $("#users").innerHTML = users.map((u) => `<tr><td>${esc(u.full_name)}</td><td>${esc(u.email)}</td><td>${u.role}</td>
      <td><span class="pill ${u.status === "active" ? "green" : "red"}">${u.status}</span></td>
      <td>${u.status === "active" ? `<button class="ghost small" data-set="deactivated" data-id="${u.user_id}">Deactivate</button>`
        : `<button class="ghost small" data-set="active" data-id="${u.user_id}">${u.status === "locked" ? "Unlock" : "Reactivate"}</button>`}
        <button class="red small" data-delete="${u.user_id}">Delete</button></td></tr>`).join("");
    document.querySelectorAll("[data-set]").forEach((b) => (b.onclick = async () => { try { await api(`/admin/users/${b.dataset.id}`, { method: "PATCH", body: { status: b.dataset.set } }); load(); } catch (err) { toast(err.error, "bad"); } }));
    document.querySelectorAll("[data-delete]").forEach((b) => (b.onclick = async () => { if (confirm("Delete this user and all their data?")) { try { await api(`/admin/users/${b.dataset.delete}`, { method: "DELETE" }); load(); } catch (err) { toast(err.error, "bad"); } } }));
    $("#logs").textContent = logs.map((l) => `${l.created_at}  ${l.level.padEnd(5)} ${l.message}`).join("\n") || "No log entries.";
  }
  ["#q", "#role", "#status"].forEach((s) => ($(s).oninput = load));
  $("#runJobs").onclick = async () => { const r = await api("/admin/run-jobs", { method: "POST" }); toast(`Jobs run: ${r.notifications_sent} notification(s) sent, ${r.missed_sessions_rescheduled} missed session(s) rescheduled, ${r.deadline_alerts_created} deadline alert(s).`); load(); };
  load();
};

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (!pages[page]) return;
  try { Promise.resolve(pages[page]()).catch((err) => err && err.error && toast(err.error, "bad")); }
  catch (e) { /* redirected to the login page or the right home page */ }
});
