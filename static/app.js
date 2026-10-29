"use strict";
const $ = (s, r=document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const AUTH = {user: null};
let ST = null, PREV = null, lang = "tr", pollT = null, failN = 0, inflight = false, again = false;
const V = {view:"map", sid:null, qi:0, sec:0, exam:null, edit:false, live:false, draft:"", drafts:{}};
const t = (k, p={}) => { let s = (I18N[lang]||{})[k] ?? I18N.tr[k] ?? k; if (typeof s === "string") for (const a in p) s = s.replace("{"+a+"}", p[a]); return s; };
const PASS = 75;
const SITE = {fox: {tr: "Foxy Study", ar: "فوكسي ستادي"}, panda: {tr: "Panda Study", ar: "باندا ستادي"}, robot: {tr: "Robo Study", ar: "روبو ستادي"}};
const siteName = () => { const k = ST?.settings?.mascot || "fox", c = CHAR_STATE.byId[k]; return c && !c.builtin ? (c.title || c.name + " Study") : (SITE[k] || SITE.fox)[lang]; };
/* ---------- theme: built-in colours, or admin-chosen colours per character ---------- */
const hex2 = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
const mix = (a, b, t) => { const x = hex2(a), y = hex2(b); return "#" + x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, "0")).join(""); };
const lum = h => { const [r, g, b] = hex2(h).map(v => v / 255); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const THEME_VARS = ["--pri", "--pri-d", "--pri-l", "--on-pri", "--sec", "--sec-d", "--bg", "--bg2", "--card", "--txt", "--mut", "--line"];
const paletteVars = th => [th.pri, mix(th.pri, "#000000", .25), mix(th.pri, th.bg, .86), lum(th.pri) > .62 ? "#1b1b1b" : "#ffffff", th.sec, mix(th.sec, "#000000", .2), th.bg, mix(th.bg, th.txt, .05), th.card, th.txt, mix(th.txt, th.bg, .45), mix(th.bg, th.txt, .14)];
function applyTheme() {
  const k = ST?.settings?.mascot || "fox", root = document.documentElement, th = CHAR_STATE.byId[k]?.theme; document.title = siteName();
  root.dataset.theme = MASCOTS[k] ? k : "fox";
  if (!th) { THEME_VARS.forEach(v => root.style.removeProperty(v)); return; }
  const vals = paletteVars(th); THEME_VARS.forEach((v, i) => root.style.setProperty(v, vals[i]));
}
async function loadChars() {
  if (CHAR_STATE.loading) return; CHAR_STATE.loading = true;
  try {
    const j = await fetch("/api/characters").then(r => r.json());
    if (j.ok) { CHAR_STATE.list = j.characters; CHAR_STATE.byId = Object.fromEntries(j.characters.map(c => [c.id, c])); CHAR_STATE.phrases = j.phrases; CHAR_STATE.modes = j.modes; CHAR_STATE.v = j.v;
      ["#top", "#root", "#widget", "#layer", "#nav"].forEach(x => { const e = $(x); if (e) e._sig = null; }); if (ST) { applyTheme(); render(); } }
  } catch (e) {}
  CHAR_STATE.loading = false;
}
/* phrases the mascot says (admin edits them): random or in order */
const SEQ = (() => { try { return JSON.parse(localStorage.getItem("foxy_seq") || "{}"); } catch (e) { return {}; } })(), LASTP = {};
function phraseFor(use, kind) {
  if (!CHAR_STATE.v) { const a = t(use === "click" ? "pokes" : "cheers"); return a[Math.floor(Math.random() * a.length)]; }
  const ok = p => (p.lang === "any" || p.lang === lang) && (p.kind === use || p.kind === "both");
  const own = CHAR_STATE.phrases.filter(p => p.target === kind && ok(p)), common = CHAR_STATE.phrases.filter(p => p.target === "all" && ok(p));
  const mode = CHAR_STATE.modes[kind] || CHAR_STATE.modes.all || "random", key = kind + ":" + use;
  const list = mode === "sequence" && own.length ? own : [...own, ...common];     // in order mode a character's own lines form an exact script
  if (!list.length) return null;
  if (mode === "sequence") { const i = (SEQ[key] || 0) % list.length; SEQ[key] = i + 1; try { localStorage.setItem("foxy_seq", JSON.stringify(SEQ)); } catch (e) {} return list[i].text; }
  let i = Math.floor(Math.random() * list.length); if (list.length > 1 && LASTP[key] === i) i = (i + 1) % list.length; LASTP[key] = i; return list[i].text;
}

async function api(path, body, method) {
  const o = {method: method || (body !== undefined ? "POST" : "GET"), headers: {"X-Requested-With": "foxy"}};
  if (body instanceof FormData) o.body = body;
  else if (body !== undefined) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(body); }
  const r = await fetch(path, o);
  if (r.status === 401 && !/\/api\/(login|setup)$/.test(path)) { onAuthLost(); throw new Error("auth"); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok && !j.error) throw new Error("http " + r.status);
  return j;
}
/* ---------- helpers ---------- */
function fmt(txt) {
  const lines = esc(txt).split("\n"); let out = "", ul = false;
  for (const l of lines) {
    const b = l.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    if (/^\s*[-•*]\s+/.test(l)) { if (!ul) { out += "<ul>"; ul = true; } out += "<li>" + b.replace(/^\s*[-•*]\s+/, "") + "</li>"; }
    else { if (ul) { out += "</ul>"; ul = false; } out += b.trim() ? "<p>" + b + "</p>" : ""; }
  }
  return out + (ul ? "</ul>" : "");
}
function setIf(el, sig, fn) { if (el && el._sig !== sig) { el._sig = sig; fn(el); return true; } return false; }
function toast(msg) { const tt = $("#toasts"); while (tt.children.length >= 2) tt.firstChild.remove(); const d = document.createElement("div"); d.className = "toast"; d.textContent = msg; tt.append(d); setTimeout(() => d.remove(), 4000); }
function confetti() {
  const cols = {fox: ["#ff9600","#ffc800","#ff4b4b","#ffb84d","#1cb0f6","#ff7a00"], robot: ["#1cb0f6","#58cc02","#8cff4d","#ffc800","#84d8ff","#1899d6"], panda: ["#333","#999","#555","#bbb","#111","#ffc800"]}[document.documentElement.dataset.theme] || ["#ff9600","#ffc800"];
  for (let i = 0; i < 46; i++) { const d = document.createElement("i"); d.className = "conf"; d.style.cssText = `left:${Math.random()*100}vw;background:${cols[i%6]};animation-duration:${1.8+Math.random()*1.6}s;animation-delay:${Math.random()*.5}s`; document.body.append(d); setTimeout(() => d.remove(), 4200); }
}
function typeInto(el, full, render) {
  el._full = full; if (el._raf) return;
  const step = () => {
    const have = el._shown || "", want = el._full;
    if (!want.startsWith(have)) { el._shown = want; render(el, want); el._raf = 0; return; }
    if (have.length < want.length) {
      const n = Math.max(1, Math.ceil((want.length - have.length) / 14));
      el._shown = want.slice(0, have.length + n); render(el, el._shown); el._raf = requestAnimationFrame(step);
    } else el._raf = 0;
  };
  el._raf = requestAnimationFrame(step);
}
const plain = (el, s) => { el.textContent = s; };
const resetViewCache = () => { const r = $("#root"); r._sig = null; r._shell = null; };

/* ---------- data helpers ---------- */
const course = () => ST?.course, prog = () => ST?.progress;
const stageById = id => course()?.stages.find(s => s.id === id);
const stageOfQ = qid => course().stages.find(s => s.question_ids.includes(qid))?.id;
const recOf = (qid, exam) => prog()?.answers[`${exam || stageOfQ(qid)}:${qid}`];
const qText = qid => course().questions.find(q => q.id === qid)?.text || "";
const SS = sid => prog().stage_stats[sid] || {total:0, answered:0, graded:0, avg:null, passed:false};
const unlocked = i => i === 0 || ST.me.is_admin || SS(course().stages[i-1].id).passed;
const allPassed = () => course() && course().stages.length > 0 && (ST.me.is_admin || course().stages.every(s => SS(s.id).passed));
const currentQids = () => V.exam ? prog().exams.find(e => e.id === V.exam)?.qids || [] : stageById(V.sid)?.question_ids || [];
const scoreClass = s => s >= 70 ? "good" : s >= 40 ? "mid" : "bad";
function stageState(s, i) {
  const ss = SS(s.id);
  if (s.status === "paused" && !s.sections.length) return "paused";
  if (!unlocked(i)) return "locked";
  if (s.status !== "ready" && !s.sections.length) return "building";
  if (ss.passed) return "passed";
  if (ss.total > 0 && ss.answered === ss.total) return ss.graded === ss.total ? "failed" : "pending";
  return "open";
}
const starsOf = avg => avg === null ? 0 : avg >= 90 ? 3 : avg >= 82 ? 2 : 1;

/* ---------- state loop (local server only) ---------- */
async function refresh() {
  clearTimeout(pollT);
  if (!AUTH.user) return;
  if (inflight) { again = true; return; } inflight = true;
  try { const s = await api("/api/state"); failN = 0; $("#banner").hidden = true; onState(s); }
  catch (e) { failN++; const b = $("#banner"); b.hidden = false; b.textContent = t("offline"); }
  inflight = false;
  let wait = failN ? Math.min(30000, 2000 * 2 ** failN) : (ST?.busy || V.pendingFast ? 900 : 20000);
  if (again && !failN) { again = false; wait = 60; }
  pollT = setTimeout(refresh, wait);
}
function onState(s) {
  PREV = ST; ST = s; lang = s.settings.lang;
  document.documentElement.lang = lang; document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  SFX.setOn(s.settings.sound); applyTheme(); document.title = siteName(); if (s.constants.cv !== CHAR_STATE.v) loadChars();
  if (PREV && PREV.settings.active === s.settings.active && PREV.course && s.course) {
    s.course.stages.forEach((st, i) => { const p = PREV.course.stages[i]; if (p && p.status !== "ready" && st.status === "ready" && i > 0) { toast(t("stageReady", {t: st.title})); SFX.play("pop"); } });
  }
  const oldIds = new Set((PREV?.notifications || []).map(n => n.id));
  s.notifications.filter(n => PREV && !oldIds.has(n.id)).slice(0, 3).forEach(n => {
    if (n.kind === "graded") { if (!(V.view === "quiz" && n.key === curKey())) { toast(t("gradedN", {s: n.score}) + (n.lost_heart ? " · " + t("lostHeart") : "")); SFX.play("ding"); } }
    else if (n.kind === "badge") { toast("🏅 " + t("badgeN", {b: t("b_" + n.badge)})); confetti(); SFX.play("perfect"); }
    else if (n.kind === "lesson_ready") { toast("✨ " + t("lessonReady")); SFX.play("chime"); }
    else if (n.kind === "error") { toast("⚠️ " + t("errN")); SFX.play("oops"); }
  });
  V.pendingFast = prog() ? Object.values(prog().answers).some(r => r.status === "queued" || r.status === "grading") : false;
  render();
}
const curKey = () => { if (V.view !== "quiz") return null; const q = currentQids()[V.qi]; return q ? `${V.exam || stageOfQ(q)}:${q}` : null; };

/* ---------- render ---------- */
let chatWait = false;
function render() {
  renderTop(); renderWidget(); renderPanels(); if (typeof renderNav === "function") renderNav();
  const root = $("#root"), extra = ["shop", "profile", "admin", "monitor"].includes(V.view);
  if (!ST.course && !extra) { setIf(root, "welcome" + lang + ST.me.can_upload, welcome); V.view = "map"; V.live = false; }
  else if (V.view === "learn") renderLearn();
  else if (V.view === "quiz") renderQuiz();
  else if (V.view === "results") renderResults();
  else if (V.view === "shop") renderShop();
  else if (V.view === "profile") renderProfile();
  else if (V.view === "admin") renderAdmin();
  else if (V.view === "monitor") renderMonitor();
  else renderMap();
  if (V.view !== "quiz") V.live = false;
  SFX.think((V.view === "quiz" && V.live) || chatWait);
}
function renderTop() {
  const s = ST, st = s.stats, a = s.ai, me = s.me, off = s.settings.offline, L = s.lessons.find(l => l.id === s.settings.active), unread = s.notifications.filter(n => !n.read).length;
  const ico = {unknown:"🤖", ok:"✅", cooling:"⏳", quota:"⛔", nokey:"🔑", auth:"🔑", error:"⚠️", offline:"✈️"}[a.state] || "🤖";
  const lbl = {unknown:t("ai_unknown"), ok:t("ai_ok"), cooling:t("ai_cool",{s:a.cooldown_left}), quota:t("ai_quota"), nokey:t("ai_nokey"), auth:t("ai_auth"), error:t("ai_err"), offline:t("ai_off")}[a.state] || a.state;
  setIf($("#top"), [lang, L?.title, st.streak, st.gems, st.xp, st.xp_avail, st.hearts, a.state, lbl, unread, s.settings.mascot, off, me.id, me.can_ai, me.is_admin, me.is_teacher].join("|"), el => {
    el.innerHTML = `<button class="brand" data-act="home" title="${t("homeTitle")}" aria-label="${t("homeTitle")}">${mascotHTML(s.settings.mascot)}<span>${siteName()}</span></button>
    <button class="lesson-btn" data-act="lessons" title="${t("history")}">📚 <span>${esc(L ? L.title : t("noLesson"))}</span> ▾</button><div class="spacer"></div>
    <span class="chip streak" title="${t("streak")}">🔥 ${st.streak}</span><button class="chip gems" data-act="shop" title="${t("shopT")}">💎 ${st.gems}</button>
    <span class="chip xp" title="${t("xp")}">⚡ ${me.is_admin ? st.xp : st.xp_avail}</span><button class="chip hearts" data-act="shop" title="${t("hearts")}">❤️ ${me.is_admin ? "∞" : st.hearts}</button>
    ${me.can_ai ? `<button class="chip net ${off ? "off" : ""}" data-act="toggleOffline" title="${off ? t("goOnline") : t("goOffline")}">${off ? "✈️" : "🌐"}<span class="lbl"> ${off ? t("offlineChip") : t("onlineChip")}</span></button>` : ""}
    <button class="chip ai ${a.state}" data-act="gear" title="${esc(me.can_ai ? (a.message || t("ai_note")) : t("ai_note"))}">${ico}<span class="lbl"> ${lbl}</span></button>
    ${me.is_admin || me.is_teacher ? `<button class="icon-btn" data-act="monitor" aria-label="${t("monitorT")}" title="${t("monitorT")}">📊</button>` : ""}
    ${me.is_admin ? `<button class="icon-btn" data-act="admin" aria-label="${t("adminT")}" title="${t("adminT")}">🛡️</button>` : ""}
    <button class="icon-btn" data-act="bell" aria-label="${t("notifs")}">🔔${unread ? `<i class="badge">${unread}</i>` : ""}</button>
    <button class="icon-btn" data-act="gear" aria-label="${t("settings")}">⚙️</button>`;
  });
}
function welcome(el) {
  const me = ST.me;
  el.innerHTML = `<div class="shell center big-mascot" style="padding-top:30px">${mascotHTML(ST.settings.mascot)}<h1>${t("welcomeT")}</h1><p>${me.can_upload ? t("welcomeS") : t("waitLesson")}</p>
  <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">${me.can_upload ? `<button class="btn" data-act="newLesson">${t("newLesson")}</button>` : `<button class="btn" data-act="newLesson">📦 ${t("importBtn")}</button><button class="btn ghost" data-act="gear">🔑 ${t("keyOpen")}</button>`}</div><p style="color:var(--mut);font-size:14px">${t("ai_note")}</p></div>`;
}
function sideHTML() {
  const st = ST.stats, goal = 50, frac = Math.min(1, st.daily_xp / goal), C = +(2 * Math.PI * 34).toFixed(2), hit = st.daily_xp >= goal;
  const all = ["first_answer","stage1","streak3","streak7","xp100","xp500","perfect","exam"];
  const bolt = `<path d="M45 17 27 43h11l-4 20 19-28H42z" fill="url(#boltg)" stroke="#d98900" stroke-width="1.2" stroke-linejoin="round"/>`;
  return `<aside class="side"><div class="card goal ${hit ? "hit" : ""}"><h3>${t("dailyGoal")}</h3><div class="goal-row">
    <svg class="ring-svg" viewBox="0 0 80 80" aria-hidden="true"><defs><linearGradient id="boltg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff0a0"/><stop offset="1" stop-color="#f29a00"/></linearGradient></defs>
      <circle cx="40" cy="40" r="34" class="ring-bg"/><circle cx="40" cy="40" r="34" class="ring-fg" stroke-dasharray="${C}" stroke-dashoffset="${(C * (1 - frac)).toFixed(2)}" transform="rotate(-90 40 40)"/><circle cx="40" cy="40" r="28" class="ring-core"/>${bolt}</svg>
    <div><b class="goal-n">${st.daily_xp}/${goal}</b><div class="mut">XP${hit ? " ✓" : ""}</div><div class="mut">${t("level")} ${Math.floor(st.xp / 100) + 1}</div></div></div></div>
  <div class="card"><h3>${t("badges")}</h3><div class="badges">${all.map(b => `<div class="bd ${st.badges.includes(b) ? "on" : ""}">${badgeSVG(b)}<small>${t("b_" + b)}</small></div>`).join("")}</div></div></aside>`;
}

/* ---------- map (duolingo-style path) ---------- */
const STAR = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5L2.5 9.4l6.6-.9z" stroke="currentColor" stroke-linejoin="round" stroke-width="1.5"/></svg>`;
const DUMBBELL = `<svg viewBox="0 0 40 24" aria-hidden="true"><rect x="1" y="8" width="5" height="8" rx="2"/><rect x="6" y="4" width="6" height="16" rx="2.5"/><rect x="12" y="10.5" width="16" height="3"/><rect x="28" y="4" width="6" height="16" rx="2.5"/><rect x="34" y="8" width="5" height="8" rx="2"/></svg>`;
function chestSVG(state) {
  const body = state === "ready" ? "#c98a2b" : state === "open" ? "#b9b9b9" : "#c9c9c9", lid = state === "ready" ? "#e5a63a" : "#d6d6d6", band = state === "ready" ? "#ffd75e" : "#aaa";
  const lidPath = state === "open" ? `<path d="M10 22 14 4h40l4 18Z" fill="${lid}" transform="rotate(-18 10 22)"/>` : `<path d="M8 24C8 10 14 6 34 6s26 4 26 18Z" fill="${lid}"/>`;
  return `<svg viewBox="0 0 68 60" aria-hidden="true"><rect x="8" y="24" width="52" height="30" rx="5" fill="${body}"/>${lidPath}<rect x="8" y="22" width="52" height="6" fill="${band}"/><rect x="29" y="25" width="10" height="12" rx="3" fill="${state === "ready" ? "#fff3b0" : "#9a9a9a"}"/>${state === "open" ? `<circle cx="34" cy="34" r="3" fill="#ffd75e"/>` : ""}</svg>`;
}
function renderMap() {
  const root = $("#root"), c = ST.course, P = prog();
  const sig = [lang, ST.settings.active, c.status, c.title, JSON.stringify(c.stages.map(s => [s.status, s.sections.length])), JSON.stringify(P.stage_stats), JSON.stringify(P.chests), ST.settings.mascot, c.error?.kind, ST.ai.state, JSON.stringify(P.exams.map(e => e.done))].join("|");
  setIf(root, sig, el => {
    V.view = "map";
    let body = "";
    if (c.status === "analyzing") {
      body = `<div class="card center big-mascot">${mascotHTML(ST.settings.mascot, "talk")}<div class="spinner"></div><h2>${t("analyzing")}</h2><p>${t("analyzingS")}</p><p>${aiLine()}</p></div>`;
    } else if (c.status === "paused" && !c.stages.length) {
      body = `<div class="card center big-mascot">${mascotHTML(ST.settings.mascot, "sad")}<h2>${aiLine()}</h2><p class="err-text">${esc(c.error?.message || "")}</p><div class="sheet-row" style="justify-content:center;gap:10px">${["nokey","auth"].includes(ST.ai.state) ? `<button class="btn blue" data-act="gear">🔑 ${t("keyOpen")}</button>` : ""}${ST.settings.offline ? `<button class="btn blue" data-act="toggleOffline">🌐 ${t("reconnect")}</button>` : `<button class="btn" data-act="retryAnalyze">${t("retry")}</button>`}</div></div>`;
    } else {
      const off = [0, 46, 74, 46, 0, -46, -74, -46], dir = lang === "ar" ? -1 : 1; let seq = 0; const nextO = () => off[seq++ % 8];
      const curIdx = c.stages.findIndex(s => !SS(s.id).passed), allOk = curIdx === -1;
      const reader = (o, idx) => { const left = o * dir >= 0; return `<div class="reader" style="${left ? "right" : "left"}:calc(100% + 18px)"><div class="platform"></div>${STACK_SVG}${mascotHTML(ST.settings.mascot)}${BOOK_SVG}</div>`; };
      let nodes = "";
      c.stages.forEach((s, i) => {
        const ss = SS(s.id), state = stageState(s, i), o = nextO(), cur = i === curIdx;
        let cls = "", icon = STAR, sub = "";
        if (state === "paused") { cls = "paused"; icon = s.error?.kind === "offline" ? "✈️" : "⚠️"; sub = t("paused"); }
        else if (state === "locked") { cls = "locked"; sub = s.status !== "ready" && !s.sections.length ? t("building") : ""; }
        else if (state === "building") { cls = "building"; icon = s.emoji; sub = `${t("building")}<span class="shimmer"></span>`; }
        else if (state === "passed") { cls = "done"; const n = starsOf(ss.avg); sub = `<span class="stars">${"★".repeat(n)}${"☆".repeat(3-n)}</span> ${ss.avg}%`; }
        else if (state === "failed") { cls = "failed"; icon = "↻"; sub = `${ss.avg}% / ${PASS}%`; }
        else if (state === "pending") { cls = "pending"; icon = "⏳"; sub = t("pending"); }
        else sub = t("qCount", {n: ss.total});
        nodes += `<div class="pn ${cur ? "cur" : ""}" data-sid="${s.id}" style="--o:${o}">${cur && state === "open" ? `<div class="start-bubble">${t("start")}</div>` : ""}${cur ? reader(o, i) : ""}
          <div class="ring"><button class="node ${cls}" data-act="stage" data-i="${i}" aria-label="${esc(s.title)}">${icon}</button></div>
          <div class="pn-title ${state === "locked" ? "dim" : ""}">${esc(s.title)}</div><div class="node-sub">${sub}</div></div>`;
        if (ss.answered > 0) { const o2 = nextO(); nodes += `<div class="pn" style="--o:${o2}"><button class="small-node" data-act="redoStage" data-sid="${s.id}" title="${t("redo")}" aria-label="${t("redo")}">${DUMBBELL}</button></div>`; }
        const o3 = nextO(), claimed = !!P.chests[s.id], cs = claimed ? "open" : ss.passed ? "ready" : "locked";
        nodes += `<div class="pn" style="--o:${o3}"><button class="chest ${cs}" data-act="chest" data-sid="${s.id}" title="${cs === "locked" ? t("chestLocked") : t("chestOpen")}" aria-label="chest">${chestSVG(cs)}</button></div>`;
      });
      const oe = nextO(), ex = P.exams[P.exams.length - 1];
      nodes += `<div class="pn ${allOk ? "cur" : ""}" style="--o:${oe}">${allOk ? reader(oe, -1) : ""}<div class="ring"><button class="node exam ${allPassed() ? "" : "locked"}" data-act="exam">🏆</button></div><div class="pn-title">${t("finalExam")}</div><div class="node-sub">${allPassed() ? t("examS") : t("examNeed")}${ex?.done ? " · ✓" : ""}</div></div>`;
      const ready = c.stages.filter(s => s.status === "ready").length;
      body = `<div class="unit"><div><h2>${esc(c.title)}</h2><small>${ready}/${c.stages.length} ${t("stages")} · ${t("passNeed")}</small></div><div style="display:flex;gap:8px">${ST.lessons.find(l => l.id === c.id)?.can_manage ? `<button class="btn ghost" data-act="exportLesson" data-id="${c.id}" title="${t("exportBtn")}">⬇️</button>` : ""}<button class="btn ghost" data-act="newLesson">＋</button></div></div><div class="path">${nodes}</div>`;
    }
    el.innerHTML = `<div class="layout"><section>${body}</section>${sideHTML()}</div>`;
  });
}
function aiLine() { const a = ST.ai; return a.state === "offline" ? "✈️ " + t("offlineHint") : a.state === "ok" ? "✅ " + t("ai_ok") : a.state === "cooling" ? "⏳ " + t("ai_cool", {s: a.cooldown_left}) : a.state === "nokey" ? "🔑 " + t("ai_nokey") + " — " + t("ai_hint") : a.state === "unknown" ? "🤖 " + t("analyzingS") : "⚠️ " + (a.message || t("ai_err")); }

/* ---------- stages ---------- */
function openStage(i) {
  const s = course().stages[i], state = s ? stageState(s, i) : "locked", node = $(`.pn[data-sid="${s?.id}"] .node`);
  if (state === "locked") { SFX.play("bad"); toast(t("stageLocked")); if (node) { node.classList.remove("lockshake"); void node.offsetWidth; node.classList.add("lockshake"); } return; }
  if (state === "building") { toast(t("stageBuilding")); return; }
  if (state === "paused") { api("/api/retry", {lesson: ST.settings.active, what: "stage", sid: s.id}).then(refresh); return; }
  const ss = SS(s.id);
  V.sid = s.id; V.exam = null; V.sec = 0; V.qi = 0; V.edit = false; SFX.play("sparkle");
  if (ss.total > 0 && ss.answered === ss.total) V.view = "results";
  else if (prog().read[s.id]) { V.view = "quiz"; V.qi = Math.max(0, s.question_ids.findIndex(q => !recOf(q))); }
  else V.view = "learn";
  $("#root").innerHTML = ""; resetViewCache(); render();
}
function renderLearn() {
  const root = $("#root"), st = stageById(V.sid), secs = st.sections, total = Math.max(st.outline.length, secs.length);
  if (!root.querySelector(".learn")) {
    resetViewCache();
    root.innerHTML = `<div class="shell learn"><div class="l-top"><button class="x" data-act="exit">✕</button><div class="bar"><i id="lbar"></i></div></div><div class="talk-row"><div id="lmascot">${mascotHTML(ST.settings.mascot)}</div><div class="say" id="lsay"></div></div><div class="card sec" id="lcard"></div><div class="sheet" id="lsheet"></div></div>`;
  }
  $("#lbar").style.width = Math.min(100, (V.sec + (st.status === "ready" ? 1 : 0.5)) / total * 100) + "%";
  setIf($("#lsay"), lang + V.sec, el => el.textContent = V.sec === 0 ? t("hello") : t("cheers")[V.sec % t("cheers").length]);
  const card = $("#lcard"), cur = secs[V.sec];
  if (cur) { setIf(card, "full" + V.sec + cur.body.length + st.id, el => { el._shown = ""; el._full = ""; el.classList.remove("cursor"); el.innerHTML = `<h2>${esc(cur.title)}</h2><div class="body">${fmt(cur.body)}</div>`; el.style.animation = "none"; void el.offsetWidth; el.style.animation = ""; }); }
  else if (st.partial) {
    setIf(card, "part" + V.sec, el => { el.innerHTML = `<h2></h2><div class="body cursor"></div>`; el._shown = ""; });
    $("h2", card).textContent = st.partial.title; typeInto($(".body", card), st.partial.body, (e, s) => e.innerHTML = fmt(s));
  } else setIf(card, "wait" + V.sec + st.status, el => el.innerHTML = st.status === "paused" ? `<div class="center"><p class="err-text">${esc(aiLineErr(st))}</p><button class="btn red" data-act="retryStage">${t("retry")}</button></div>` : `<div class="center"><div class="spinner"></div><b>${t("writing")}</b></div>`);
  const lastReady = st.status === "ready" && V.sec >= secs.length - 1, can = !!cur;
  setIf($("#lsheet"), [lang, V.sec, can, lastReady, secs.length].join("|"), el => {
    el.className = "sheet"; el.innerHTML = `<div class="sheet-row"><span>${V.sec > 0 ? `<button class="btn ghost" data-act="prevSec">${lang === "ar" ? "▶" : "◀"} ${t("prev")}</button> ` : ""}${t("sectionN", {a: Math.min(V.sec+1, total), b: total})}</span><button class="btn" data-act="learnNext" ${can ? "" : "disabled"}>${lastReady ? (st.question_ids.length ? t("toQuestions") : t("finish")) : t("cont")}</button></div>`;
  });
}

/* ---------- quiz (stage questions and final exam) ---------- */
function renderQuiz() {
  const root = $("#root"), qids = currentQids(), qid = qids[V.qi];
  if (!qids.length) { V.view = "map"; resetViewCache(); return render(); }
  const shellKey = [V.sid, V.exam, V.qi, lang].join("|");
  if (root._shell !== shellKey) {
    root._shell = shellKey; root._sig = null;
    const title = V.exam ? t("finalExam") : stageById(V.sid).title;
    root.innerHTML = `<div class="shell quiz"><div class="l-top"><button class="x" data-act="exit">✕</button><div class="bar"><i style="width:${V.qi/qids.length*100}%"></i></div><button class="btn ghost" data-act="ask">💬 ${t("ask")}</button></div>
      <div class="talk-row"><div id="qm">${mascotHTML(ST.settings.mascot)}</div><div class="say">${esc(title)}</div></div>
      <div class="card qcard"><small>${t("qN", {a: V.qi+1, b: qids.length})}</small><h2>${esc(qText(qid))}</h2></div>
      <textarea id="ans" placeholder="${t("yourAnswer")}" ${lang === "ar" ? 'dir="rtl"' : ""}></textarea><div id="hist"></div><div class="sheet" id="qsheet"></div></div>`;
    let lastKey = 0;
    $("#ans").addEventListener("input", () => { V.draft = $("#ans").value; V.drafts[curKey()] = V.draft; const n = performance.now(); if (n - lastKey > 70) { lastKey = n; SFX.play("key"); } updateSheet(true); });
    V.draft = V.drafts[curKey()] || ""; $("#ans").value = V.draft; V.edit = false;
  }
  updateSheet();
}
function updateSheet() {
  const el = $("#qsheet"); if (!el) return;
  const qids = currentQids(), qid = qids[V.qi], r = recOf(qid, V.exam), last = V.qi >= qids.length - 1, ta = $("#ans");
  const editing = !!(r && V.edit && r.status === "done" && !V.exam), showResult = !!r && !editing;
  ta.disabled = showResult; if (showResult && ta.value !== r.answer) ta.value = r.answer;
  const prevBtn = `<button class="btn ghost" data-act="prevQ" ${V.qi === 0 ? "disabled" : ""}>${lang === "ar" ? "▶" : "◀"} ${t("prev")}</button>`;
  const nextTxt = last ? t("finish") : t("next"), cool = ST.ai.state === "cooling" ? `<br><small>⏳ ${t("ai_cool", {s: ST.ai.cooldown_left})}</small>` : "";
  const live = !!(showResult && (r.status === "queued" || r.status === "grading")); V.live = live;
  const noHearts = !ST.me.is_admin && ST.stats.hearts <= 0;
  // earlier attempts and their feedback stay visible under the answer box
  const att = r ? [...(r.history || [])] : []; if (editing) att.push({answer: r.answer, score: r.score, text: r.text});
  setIf($("#hist"), JSON.stringify(att) + "|" + lang, h => {
    h.innerHTML = att.slice().reverse().map((a, i) => `<div class="card hist-item"><div class="hist-h">✏️ ${t("attemptN", {n: att.length - i})} <span class="pill p-${scoreClass(a.score)}">${a.score}</span></div><p class="hist-a"></p><p class="hist-f"></p></div>`).join("");
    [...h.querySelectorAll(".hist-item")].forEach((d, i) => { const a = att[att.length - 1 - i]; d.querySelector(".hist-a").textContent = a.answer; d.querySelector(".hist-f").textContent = a.text; });
  });
  const sig = [V.qi, V.exam, r?.status, r?.score, r?.attempt, !!V.draft?.trim(), editing, lang, cool, r?.error?.kind, noHearts].join("|");
  if (!showResult) {
    setIf(el, sig, e => { e.className = noHearts ? "sheet s-bad" : "sheet"; e.innerHTML = noHearts ? `<h3>💔 ${t("noHearts")}</h3><div class="sheet-row">${prevBtn}<button class="btn red" data-act="shop">🛒 ${t("goShop")}</button></div>` : `<div class="sheet-row">${prevBtn}<button class="btn" data-act="check" ${V.draft?.trim() ? "" : "disabled"}>${editing ? t("sendAgain") : t("check")}</button></div>`; });
    return;
  }
  setIf(el, sig, e => {
    if (live) { e.className = "sheet s-wait"; e.innerHTML = `<h3>${r.status === "queued" ? "⏳ " + t("queued") : "🔎 " + t("grading")}</h3><p id="fb" class="cursor"></p><small>${t("waitGrade")}</small>${cool}`; e._shown = ""; }
    else if (r.status === "paused") { const off = r.error?.kind === "offline"; e.className = "sheet s-bad"; e.innerHTML = `<h3>${off ? "✈️" : "⚠️"} ${t("paused")}</h3><p>${esc(aiLineErr(r))}</p><div class="sheet-row">${prevBtn}${off ? `<button class="btn blue" data-act="toggleOffline">🌐 ${t("reconnect")}</button>` : `<button class="btn red" data-act="retryGrade" data-key="${r.key}">${t("retry")}</button>`}<button class="btn ghost" data-act="qNext">${nextTxt}</button></div>`; }
    else {
      const c = scoreClass(r.score), canEdit = r.score < 100 && !V.exam; e.className = "sheet s-" + c;
      e.innerHTML = `<h3>${c === "good" ? "🎉 " + t("great") : c === "mid" ? "👍 " + t("good") : "💪 " + t("wrong")} · ${r.score}/100</h3><p id="fb"></p>${canEdit ? `<p class="edit-hint">${t("editHint")}</p>` : ""}<div class="sheet-row">${prevBtn}${canEdit ? `<button class="btn blue" data-act="edit">✏️ ${t("editAnswer")}</button>` : ""}<button class="btn" data-act="qNext">${nextTxt}</button></div>`;
      $("#fb", e).textContent = r.text;
      if (V.fresh === r.key) { V.fresh = null; SFX.play(r.score >= 100 ? "perfect" : c === "good" ? "good" : c === "mid" ? "mid" : "bad"); reactMascot($("#qm .mascot"), c === "bad" ? "sad" : "celebrate"); if (c === "good") confetti(); }
    }
  });
  const fb = $("#fb", el); if (fb && live) typeInto(fb, r.text || "", plain);
}
const aiLineErr = r => (r.error?.kind === "offline" ? t("offlineHint") : r.error?.kind === "quota_day" ? t("ai_quota") : r.error?.kind === "nokey" ? t("ai_hint") : r.error?.message || t("ai_err"));

async function submitAnswer() {
  const qid = currentQids()[V.qi], val = $("#ans").value.trim(); if (!val) return;
  const btn = $("[data-act=check]"); if (btn) btn.disabled = true;
  SFX.play("send");
  const j = await api("/api/answer", {lesson: ST.settings.active, qid, answer: val, exam: V.exam || undefined});
  if (j.ok) { delete V.drafts[curKey()]; V.fresh = j.key; V.edit = false; reactMascot($("#qm .mascot"), "talk"); await refresh(); }
  else { if (j.error === "no_hearts") { toast("💔 " + t("noHearts")); SFX.play("oops"); ACT.shop(); return; } toast(t("err_" + j.error)); if (btn) btn.disabled = false; }
}
function qNext() {
  const qids = currentQids();
  if (V.qi < qids.length - 1) { V.qi++; V.edit = false; SFX.play("flip"); renderQuiz(); }
  else { V.view = "results"; V.resK = null; resetViewCache(); render(); }
}

/* ---------- results (75% rule) ---------- */
function renderResults() {
  const root = $("#root"), qids = currentQids(), recs = qids.map(q => recOf(q, V.exam)), have = recs.filter(Boolean), graded = have.filter(r => r.status === "done");
  const total = qids.length, avg = graded.length === total && total ? Math.round(graded.reduce((a, r) => a + r.score, 0) / total) : null, waiting = have.length - graded.length;
  const passed = avg !== null && avg >= PASS;
  setIf(root, ["res", lang, V.sid, V.exam, JSON.stringify(recs.map(r => r ? [r.status, r.score] : 0))].join("|"), el => {
    root._shell = null;
    const banner = avg === null ? "" : passed ? `<div class="pass-banner ok">${V.exam ? t("examDone") : t("passedT")}</div>` : `<div class="pass-banner no">${t("needMore", {a: avg})}</div>`;
    el.innerHTML = `<div class="shell center"><div class="big-mascot">${mascotHTML(ST.settings.mascot, avg !== null && !passed ? "sad" : "celebrate")}</div><h1>${V.exam ? t("finalExam") : t("stageDone")}</h1>
      <div class="card"><h3>${t("avg")}: ${avg === null ? "…" : avg + "%"} ${waiting ? `<span class="pill p-wait">⏳ ${waiting} ${t("pending")}</span>` : ""}</h3>${banner}
      <div class="res-list">${qids.map((q, i) => { const r = recs[i]; const p = !r ? "" : r.status === "done" ? `<span class="pill p-${scoreClass(r.score)}">${r.score}</span>` : `<span class="pill p-wait">⏳</span>`; return `<button class="res-item" data-act="gotoQ" data-i="${i}"><span>${i+1}. ${esc(qText(q).slice(0, 80))}</span>${p}</button>`; }).join("")}</div></div>
      <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:16px">${V.exam ? "" : `<button class="btn ghost" data-act="reviewLesson">${t("review2")}</button>`}${V.exam ? "" : `<button class="btn ghost" data-act="redoStage" data-sid="${V.sid}">↻ ${t("redo")}</button>`}<button class="btn" data-act="close">${t("back")}</button></div></div>`;
  });
  const k = (V.exam || V.sid) + ":" + avg + ":" + (waiting === 0);
  if (V.resK !== k) { V.resK = k; if (avg === null) SFX.play("whoosh"); else if (passed) { SFX.play("fanfare"); confetti(); reactMascot($("#root .mascot"), "celebrate"); } else { SFX.play("sad"); reactMascot($("#root .mascot"), "sad"); } }
}

/* ---------- popups ---------- */
let panel = null, confirmFn = null;
function renderPanels() {
  const layer = $("#layer");
  const typing = ["keyin", "vol", "modelsel", "pwold", "pwnew"].includes(document.activeElement?.id);
  if (panel === "lessons") setIf(layer, "L" + lang + JSON.stringify(ST.lessons) + ST.settings.active, lessonsPanel);
  else if (panel === "bell") setIf(layer, "B" + lang + JSON.stringify(ST.notifications) + JSON.stringify(Object.values(prog()?.answers || {}).map(r => [r.key, r.status, r.text?.length])), bellPanel);
  else if (panel === "gear" && typing) { /* keep what is being typed */ }
  else if (panel === "gear") setIf(layer, "G" + lang + JSON.stringify(ST.settings) + JSON.stringify(ST.ai) + V.testing, gearPanel);
  else if (["new", "chat", "exit", "confirm"].includes(panel)) { /* these keep their own state */ }
  else if (layer._sig) { layer._sig = null; layer.innerHTML = ""; }
}
function openPanel(p) { panel = panel === p ? null : p; const l = $("#layer"); l._sig = null; l.innerHTML = ""; if (panel === "new") newLessonModal(); if (panel === "chat") chatPanel(); render(); if (panel === "bell") setTimeout(() => api("/api/notifications/read", {}).then(refresh), 1500); }
function closePanel() { panel = null; const l = $("#layer"); l.innerHTML = ""; l._sig = null; renderWidget(); }
document.addEventListener("click", e => { if (panel && !["chat", "new", "exit", "confirm"].includes(panel) && !e.target.closest(".pop,.modal,[data-act]")) openPanel(panel); }, true);

function confirmBox(text, yes, fn, kind) {
  panel = "confirm"; confirmFn = fn;
  $("#layer").innerHTML = `<div class="scrim"><div class="modal exit center">${mascotHTML(ST.settings.mascot, kind || "")}<h2>${esc(text)}</h2><button class="btn red" style="width:100%" data-act="confirmYes">${esc(yes)}</button><button class="endbtn" style="color:var(--blue)" data-act="closePanel">${t("cancel")}</button></div></div>`;
  SFX.play("oops");
}
function exitModal() {
  panel = "exit";
  $("#layer").innerHTML = `<div class="scrim"><div class="modal exit center big-mascot">${mascotHTML(ST.settings.mascot, "cry")}<h2>${t("exitT")}</h2><button class="btn blue" style="width:100%" data-act="closePanel">${t("keepLearning")}</button><button class="endbtn" data-act="endSession">${t("endSession")}</button></div></div>`;
  SFX.play("oops");
}
function lessonsPanel(el) {
  el.innerHTML = `<div class="pop"><h3 style="margin:0 0 8px">📚 ${t("history")}</h3>${ST.lessons.map(l => `<div class="row ${l.id === ST.settings.active ? "on" : ""}"><button class="grow" data-act="switch" data-id="${l.id}"><b>${esc(l.title)}</b><small>${l.mine ? "" : "👤 " + esc(l.owner_name) + " · "}${l.status === "analyzing" ? t("building") : `${l.ready}/${l.stages} ${t("stages")} · ${l.answered}/${l.total_q}`}</small></button>${l.can_manage ? `<button class="icon-btn" data-act="exportLesson" data-id="${l.id}" title="${t("exportBtn")}">⬇️</button>` : ""}<button class="icon-btn" data-act="resetLesson" data-id="${l.id}" title="${t("resetLesson")}">↻</button>${l.can_manage ? `<button class="icon-btn" data-act="delLesson" data-id="${l.id}" aria-label="${t("del")}">🗑</button>` : ""}</div>`).join("") || `<p>${t("noLesson")}</p>`}
    <button class="btn" style="width:100%;margin-top:10px" data-act="newLesson">${ST.me.can_upload ? "＋ " + t("newLesson") : "📦 " + t("importBtn")}</button></div>`;
}
function bellPanel(el) {
  const items = ST.notifications.map(n => {
    let txt = "", fb = "", icon = "🔔";
    if (n.kind === "graded") { const r = prog()?.answers[n.key]; icon = n.score >= 70 ? "🎉" : n.score >= 40 ? "👍" : "💪"; txt = `${t("gradedN", {s: n.score})} — ${esc(n.q)}`; fb = r?.text || ""; }
    else if (n.kind === "badge") { icon = "🏅"; txt = t("badgeN", {b: t("b_" + n.badge)}); }
    else if (n.kind === "lesson_ready") { icon = "✨"; txt = t("lessonReady"); }
    else if (n.kind === "error") { icon = "⚠️"; txt = t("errN"); }
    return `<div class="notif-wrap"><button class="notif ${n.read ? "" : "unread"}" data-act="toggleFb" data-id="${n.id}"><b>${icon} ${txt}</b>${fb && openFb.has(n.id) ? `<div class="fb">${esc(fb)}</div>` : ""}</button><button class="notif-x" data-act="delNotif" data-id="${n.id}" title="${t("delNotif")}" aria-label="${t("delNotif")}">✕</button></div>`;
  }).join("") || `<p>${t("noNotifs")}</p>`;
  el.innerHTML = `<div class="pop"><div class="pop-head"><h3>🔔 ${t("notifs")}</h3>${ST.notifications.length ? `<button class="btn ghost small" data-act="clearNotifs">🗑 ${t("clearAll")}</button>` : ""}</div>${items}</div>`;
}
const openFb = new Set();
function gearPanel(el) {
  const s = ST.settings, a = ST.ai, me = ST.me;
  const keyLine = me.is_admin ? t("usingAdmin") : me.has_own_key ? t("usingOwn") : t("usingShared");
  const canClear = me.is_admin ? me.has_own_key : me.has_own_key;
  el.innerHTML = `<div class="pop"><div class="pop-head"><h3>👤 ${esc(me.username)}${me.is_admin ? " 🛡️" : ""}</h3><button class="btn ghost small" data-act="logout">${t("logout")}</button></div>
  <h3 style="margin:0 0 6px">${t("language")}</h3><div class="seg"><button data-act="lang" data-v="tr" class="${s.lang === "tr" ? "on" : ""}">Türkçe</button><button data-act="lang" data-v="ar" class="${s.lang === "ar" ? "on" : ""}">العربية</button></div>
  <h3 style="margin:0 0 6px">${t("character")}</h3><div class="seg mpick">${charList().map(c => `<button data-act="mascot" data-v="${c.id}" class="${s.mascot === c.id ? "on" : ""}">${mascotHTML(c.id)}<div>${esc(c.name)}</div></button>`).join("")}</div>
  <h3 style="margin:0 0 6px">${t("sound")}</h3><div class="seg"><button data-act="sound" class="${s.sound ? "on" : ""}">${s.sound ? "🔊 " + t("on") : "🔇 " + t("off")}</button><input type="range" id="vol" min="0" max="100" value="${Math.round(SFX.vol * 100)}" aria-label="${t("volume")}"></div>
  ${me.can_ai ? `<h3 style="margin:0 0 6px">🌐 Internet</h3><div class="seg"><button data-act="toggleOffline" class="${s.offline ? "" : "on"}">${s.offline ? "✈️ " + t("offlineChip") + " — " + t("goOnline") : "🌐 " + t("onlineChip") + " — " + t("goOffline")}</button></div>
  <h3 style="margin:0 0 6px">🧠 ${t("modelTitle")}</h3>${modelHTML()}` : ""}
  <h3 style="margin:0 0 6px">🔑 ${me.is_admin ? t("sharedKeyTitle") : t("ownKeyTitle")}</h3><p style="margin:0 0 6px;color:var(--mut)">${keyLine}${me.key_hint ? " · " + me.key_hint : ""}</p>
  <input class="txt" id="keyin" type="password" autocomplete="off" spellcheck="false" placeholder="${t("keyPh")}"><p class="err-text" id="keyerr"></p>
  <div class="sheet-row" style="margin-bottom:6px"><button class="btn" data-act="saveKey">${t("keySave")}</button>${canClear ? `<button class="btn ghost" data-act="clearKey">${t("keyRemove")}</button>` : ""}</div>
  <p style="color:var(--mut);font-size:13px;margin:0 0 12px">${me.is_admin ? t("keyNote") : t("ownKeyNote")}</p>
  ${me.can_ai ? `<h3 style="margin:0 0 6px">🤖 Gemini</h3><p style="margin:0 0 8px">${aiLine()}</p><button class="btn blue" data-act="testAi" ${V.testing || s.offline ? "disabled" : ""}>${V.testing ? t("ai_testing") : t("ai_test")}</button><p style="color:var(--mut);font-size:13px">${t("ai_note")}</p>` : `<p style="margin:0 0 8px">${aiLine()}</p>`}
  <h3 style="margin:12px 0 6px">${t("changePw")}</h3><input class="txt" id="pwold" type="password" autocomplete="current-password" placeholder="${t("oldPw")}"><input class="txt" id="pwnew" type="password" autocomplete="new-password" placeholder="${t("newPw")}" style="margin-top:6px"><p class="err-text" id="pwerr"></p>
  <button class="btn ghost" data-act="savePw">${t("save")}</button></div>`;
}
function modelHTML() {
  const a = ST.ai, cur = ST.settings.model || "", list = [["", t("autoModel")], ["gemini-flash-lite-latest", t("modelLite")], ["gemini-flash-latest", t("modelFlash")]];
  (V.models || []).forEach(m => { if (!list.some(x => x[0] === m)) list.push([m, m]); });
  if (cur && !list.some(x => x[0] === cur)) list.push([cur, cur]);
  const opts = list.map(([v, label]) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(label)}${v && a.exhausted.includes(v) ? " — " + t("modelExhausted") + " ⛔" : ""}</option>`).join("");
  return `${ST.me.is_admin ? `<p style="color:var(--mut);font-size:13px;margin:0 0 6px">${t("usingAdmin")}</p>` : ""}<select class="txt" id="modelsel" aria-label="${t("modelTitle")}">${opts}</select>
  <div class="sheet-row" style="margin:8px 0"><button class="btn ghost" data-act="fetchModels" ${V.fetching || ST.settings.offline ? "disabled" : ""}>${V.fetching ? t("modelFetching") : t("modelFetch")}</button></div>
  <p style="color:var(--mut);font-size:13px;margin:0 0 12px">${cur ? t("modelNote", {m: a.fallback}) : t("modelNoteAuto")}${a.exhausted.length && !cur ? " ⛔ " + a.exhausted.join(", ") : ""}</p>`;
}
function newLessonModal() {
  $("#layer").innerHTML = `<div class="scrim"><div class="modal"><h2>${t("newLesson")}</h2>
  ${ST.me.can_upload ? `<label class="file"><input type="file" id="fq" accept=".txt,.md,.csv,.pdf,.docx"><b>📝 ${t("upQ")}</b><span id="fqn">${t("chooseFile")}</span></label>
  <label class="file"><input type="file" id="fn" accept=".txt,.md,.pdf,.docx"><b>📖 ${t("upN")}</b><span id="fnn">${t("chooseFile")}</span></label>
  <input class="txt" id="ftitle" placeholder="${t("upTitle")}"><p class="err-text" id="uerr"></p>
  <div class="sheet-row" style="margin:10px 0 16px"><button class="btn ghost" data-act="closePanel">${t("cancel")}</button><button class="btn" id="fgo" data-act="upload">${t("create")}</button></div>` : `<p class="err-text" id="uerr"></p><p>${t("waitLesson")}</p><div class="sheet-row" style="margin-bottom:10px"><button class="btn ghost" data-act="closePanel">${t("cancel")}</button></div>`}
  <label class="file"><input type="file" id="fi" accept=".foxy,.json"><b>📦 ${t("importBtn")}</b><span>${t("importHint")}</span></label></div></div>`;
  if ($("#fq")) { $("#fq").onchange = e => $("#fqn").textContent = e.target.files[0]?.name || t("chooseFile"); $("#fn").onchange = e => $("#fnn").textContent = e.target.files[0]?.name || t("chooseFile"); }
  $("#fi").onchange = async e => {
    const f = e.target.files[0]; if (!f) return; const fd = new FormData(); fd.append("file", f);
    const j = await api("/api/lessons/import", fd).catch(() => ({ok: false}));
    if (!j.ok) { $("#uerr").textContent = t("err_" + j.error) !== "err_" + j.error ? t("err_" + j.error) : t("err_bad_file"); return; }
    closePanel(); V.view = "map"; resetViewCache(); toast(t("importDone")); SFX.play("chime"); await refresh();
  };
}
async function upload() {
  const q = $("#fq").files[0], n = $("#fn").files[0], err = $("#uerr");
  if (!q || !n) { err.textContent = t("err_missing_files"); return; }
  const fd = new FormData(); fd.append("questions", q); fd.append("notes", n); fd.append("title", $("#ftitle").value);
  $("#fgo").disabled = true; $("#fgo").textContent = t("uploading");
  try {
    const j = await api("/api/lessons", fd);
    if (!j.ok) { err.textContent = t("err_" + j.error) !== "err_" + j.error ? t("err_" + j.error) : (j.error || t("err_generic")); $("#fgo").disabled = false; $("#fgo").textContent = t("create"); return; }
    closePanel(); V.view = "map"; resetViewCache(); await refresh();
  } catch (e) { err.textContent = t("err_generic"); $("#fgo").disabled = false; $("#fgo").textContent = t("create"); }
}

/* ---------- helper character: bubble + chat + poke ---------- */
let bubbleT = null, chatHist = [], chatBusy = false;
function renderWidget() {
  const w = $("#widget");
  setIf(w, "w" + ST.settings.mascot + lang + (panel === "chat"), el => {
    if (panel === "chat") { el.innerHTML = ""; clearTimeout(bubbleT); return; }
    el.innerHTML = `<div id="wb"></div><button class="w-btn" data-act="ask" aria-label="${t("ask")}">${mascotHTML(ST.settings.mascot)}</button>`;
    scheduleBubble(4000);
  });
}
function scheduleBubble(delay) {
  clearTimeout(bubbleT);
  bubbleT = setTimeout(() => {
    const wb = $("#wb"); if (!wb || panel === "chat") return;
    const line = phraseFor("bubble", ST?.settings?.mascot || "fox");
    if (line) { wb.innerHTML = `<div class="w-bubble">${esc(line)}</div>`; SFX.play("boing"); reactMascot($("#widget .mascot"), "celebrate"); setTimeout(() => { if ($("#wb")) $("#wb").innerHTML = ""; }, 5600); }
    scheduleBubble(22000 + Math.random() * 12000);
  }, delay);
}
function pokeMascot(m) {
  const kind = m.dataset.kind || ST?.settings?.mascot || "fox", r = m.getBoundingClientRect(), line = phraseFor("click", kind);
  if (line) { const d = document.createElement("div"); d.className = "poke"; d.textContent = line; d.style.left = Math.min(Math.max(r.left + r.width / 2, 90), innerWidth - 90) + "px"; d.style.top = (r.top - 8) + "px"; document.body.append(d); setTimeout(() => d.remove(), 2300); }
  reactMascot(m, "celebrate"); SFX.play("giggle");
}
function chatPanel() {
  const st = V.view !== "map" && V.sid ? stageById(V.sid) : null;
  $("#layer").innerHTML = `<div class="chat"><header>${mascotHTML(ST.settings.mascot)}<div><b>${esc(charName(ST.settings.mascot))}</b><small>${st ? esc(t("ctx", {t: st.title})) : esc(course()?.title || "")}</small></div><button class="x" data-act="closePanel">✕</button></header>
  <div class="msgs" id="msgs"><div class="msg a">${t("hello")}</div>${chatHist.length ? "" : `<div class="chips">${[1, 2, 3, 4].map(i => `<button class="chipq" data-act="chip" data-q="${esc(t("q" + i))}">${esc(t("q" + i))}</button>`).join("")}</div>`}${chatHist.map(m => `<div class="msg ${m.role === "user" ? "u" : "a"}">${esc(m.text)}</div>`).join("")}</div>
  <form id="cform"><input id="cin" placeholder="${t("askPh")}" autocomplete="off"><button class="btn" type="submit">${t("send")}</button></form></div>`;
  $("#cform").onsubmit = e => { e.preventDefault(); sendChat(); }; $("#cin").focus(); const m = $("#msgs"); m.scrollTop = m.scrollHeight; renderWidget(); SFX.play("pop");
}
async function sendChat() {
  const inp = $("#cin"), text = inp.value.trim(); if (!text || chatBusy) return;
  inp.value = ""; chatBusy = true; chatWait = true; SFX.think(true); SFX.play("send"); const box = $("#msgs"); box.querySelector(".chips")?.remove();
  box.insertAdjacentHTML("beforeend", `<div class="msg u">${esc(text)}</div><div class="msg a" id="cur">…</div>`);
  const cur = $("#cur"); box.scrollTop = box.scrollHeight; reactMascot($(".chat .mascot"), "talk");
  const hist = chatHist.slice(-6); let got = "", errored = false;
  try {
    const qid = V.view === "quiz" ? currentQids()[V.qi] : undefined;
    const r = await fetch("/api/chat", {method: "POST", headers: {"Content-Type": "application/json", "X-Requested-With": "foxy"}, body: JSON.stringify({lesson: ST.settings.active, sid: V.sid || undefined, qid, message: text, history: hist})});
    if (r.status === 401) { onAuthLost(); return; }
    const rd = r.body.getReader(), dec = new TextDecoder(); let buf = "";
    while (true) {
      const {value, done} = await rd.read(); if (done) break;
      buf += dec.decode(value, {stream: true}); let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, i).replace(/^data: /, ""); buf = buf.slice(i + 2); let ev; try { ev = JSON.parse(line); } catch { continue; }
        if (ev.t) { if (chatWait) { chatWait = false; SFX.think(false); } got += ev.t; cur.textContent = got; SFX.play("blip", charInfo(ST.settings.mascot).voice); }
        else if (ev.w) cur.textContent = got || t("waitAi", {s: ev.w});
        else if (ev.error) { errored = true; cur.textContent = got || (ev.error.kind === "offline" ? t("offlineHint") : ev.error.kind === "rate" || ev.error.kind === "quota_day" ? t("waitAi", {s: ev.error.retry || 30}) : t("chatErr")); }
        box.scrollTop = box.scrollHeight;
      }
    }
  } catch (e) { errored = true; cur.textContent = got || t("chatErr"); }
  chatWait = false; SFX.think(false);
  cur.removeAttribute("id"); if (got) { chatHist.push({role: "user", text}, {role: "model", text: got}); chatHist = chatHist.slice(-12); SFX.play("ding"); reactMascot($(".chat .mascot"), "celebrate"); } else if (errored) SFX.play("oops");
  chatBusy = false; refresh();
}

/* ---------- actions ---------- */
const ACT = {
  lessons: () => openPanel("lessons"), bell: () => openPanel("bell"), gear: () => openPanel("gear"), ask: () => { panel = null; openPanel("chat"); }, closePanel,
  newLesson: () => { panel = null; openPanel("new"); }, upload,
  switch: async b => { await api("/api/settings", {active: b.dataset.id}); V.view = "map"; closePanel(); resetViewCache(); await refresh(); },
  delLesson: b => confirmBox(t("delAsk"), t("yes"), async () => { await api("/api/lessons/" + b.dataset.id, undefined, "DELETE"); V.view = "map"; closePanel(); resetViewCache(); await refresh(); }),
  resetLesson: b => confirmBox(t("resetAsk"), t("resetYes"), async () => { await api("/api/reset", {lesson: b.dataset.id}); V.view = "map"; closePanel(); resetViewCache(); await refresh(); }),
  redoStage: b => confirmBox(t("redoAsk"), t("redoYes"), async () => { await api("/api/reset", {lesson: ST.settings.active, sid: b.dataset.sid}); V.view = "map"; closePanel(); resetViewCache(); V.resK = null; await refresh(); }, "cry"),
  confirmYes: async () => { const f = confirmFn; confirmFn = null; if (f) await f(); },
  exportLesson: async b => {
    try {
      const r = await fetch(`/api/lessons/${b.dataset.id}/export`);
      if (!r.ok) { const j = await r.json().catch(() => ({})); toast(t("err_" + j.error)); SFX.play("bad"); return; }
      const blob = await r.blob(), a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = (r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || "lesson.foxy"; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      toast(t("exported")); SFX.play("chime");
    } catch (e) { toast(t("err_generic")); }
  },
  stage: b => openStage(+b.dataset.i),
  chest: async b => {
    const sid = b.dataset.sid;
    if (b.classList.contains("open")) return;
    if (b.classList.contains("locked")) { SFX.play("bad"); toast(t("chestLocked")); return; }
    b.classList.add("opening"); SFX.play("chest");
    const j = await api("/api/chest", {lesson: ST.settings.active, sid}).catch(() => ({}));
    if (j.ok) { toast(t("chestGot", {g: 10, x: 15})); confetti(); }
    setTimeout(refresh, 400);
  },
  exam: async () => {
    if (!allPassed()) { SFX.play("bad"); return toast(t("examNeed")); }
    const j = await api("/api/exam/start", {lesson: ST.settings.active}); if (!j.ok) return toast(t("err_" + j.error));
    V.exam = j.exam; V.sid = null; V.qi = 0; V.view = "quiz"; SFX.play("fanfare"); $("#root").innerHTML = ""; resetViewCache(); await refresh();
  },
  home: () => { if (panel === "exit") return; if (panel) closePanel(); if (V.view === "learn" || V.view === "quiz") exitModal(); else if (V.view !== "map") ACT.close(); else { const r = $("#root"); window.scrollTo({top: 0, behavior: "smooth"}); reactMascot($(".brand .mascot"), "celebrate"); } },
  chip: b => { const i = $("#cin"); if (i) { i.value = b.dataset.q; sendChat(); } },
  prevQ: () => { if (V.qi > 0) { V.qi--; V.edit = false; SFX.play("flip"); renderQuiz(); } },
  prevSec: () => { if (V.sec > 0) { V.sec--; renderLearn(); } },
  delNotif: async b => { await api("/api/notifications/delete", {ids: [+b.dataset.id]}); SFX.play("pop"); $("#layer")._sig = null; await refresh(); },
  clearNotifs: async () => { await api("/api/notifications/delete", {all: true}); SFX.play("whoosh"); $("#layer")._sig = null; await refresh(); },
  exit: () => { if (V.view === "learn" || V.view === "quiz") exitModal(); else ACT.close(); },
  endSession: () => { closePanel(); ACT.close(); },
  close: () => { V.view = "map"; resetViewCache(); render(); refresh(); },
  learnNext: async () => { const st = stageById(V.sid), secs = st.sections; if (!secs[V.sec]) return; SFX.play("flip");
    if (st.status === "ready" && V.sec >= secs.length - 1) { await api("/api/read", {lesson: ST.settings.active, sid: V.sid}); if (st.question_ids.length) { V.view = "quiz"; V.qi = 0; $("#root").innerHTML = ""; resetViewCache(); await refresh(); } else ACT.close(); }
    else { V.sec++; reactMascot($("#lmascot .mascot"), "talk"); renderLearn(); } },
  check: submitAnswer, qNext,
  edit: () => { V.edit = true; const ta = $("#ans"); ta.disabled = false; V.draft = ta.value; ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); updateSheet(); },
  again: () => ACT.edit(),
  gotoQ: b => { V.view = "quiz"; V.qi = +b.dataset.i; V.edit = false; $("#root").innerHTML = ""; resetViewCache(); render(); },
  retryStage: async () => { await api("/api/retry", {lesson: ST.settings.active, what: "stage", sid: V.sid}); refresh(); },
  retryAnalyze: async () => { await api("/api/retry", {lesson: ST.settings.active, what: "analyze"}); refresh(); },
  retryGrade: async b => { await api("/api/retry", {lesson: ST.settings.active, what: "grade", key: b.dataset.key}); refresh(); },
  reviewLesson: () => { V.view = "learn"; V.sec = 0; $("#root").innerHTML = ""; resetViewCache(); render(); },
  toggleFb: b => { const id = +b.dataset.id; openFb.has(id) ? openFb.delete(id) : openFb.add(id); $("#layer")._sig = null; render(); },
  toggleOffline: async () => { const off = !ST.settings.offline; await api("/api/offline", {offline: off}); toast(off ? t("offlineToast") : t("onlineToast")); SFX.play(off ? "oops" : "chime"); $("#layer")._sig = null; ["#top", "#root"].forEach(x => $(x)._sig = null); await refresh(); },
  lang: async b => { await api("/api/settings", {lang: b.dataset.v}); ["#root", "#top", "#widget", "#layer"].forEach(s => $(s)._sig = null); $("#root")._shell = null; await refresh(); },
  mascot: async b => { await api("/api/settings", {mascot: b.dataset.v}); ["#root", "#top", "#widget", "#layer"].forEach(s => $(s)._sig = null); $("#root")._shell = null; await refresh(); },
  sound: async () => { await api("/api/settings", {sound: !ST.settings.sound}); await refresh(); },
  fetchModels: async () => { V.fetching = true; $("#layer")._sig = null; render();
    const j = await api("/api/ai/models", {}).catch(() => ({ok: false})); V.fetching = false;
    if (j.ok) V.models = j.models; else toast("⚠️ " + (j.message || t("ai_err")));
    $("#layer")._sig = null; await refresh(); },
  saveKey: async () => { const v = $("#keyin").value.trim(), err = $("#keyerr"); if (!v) { err.textContent = t("keyPh"); return; }
    const j = await api("/api/ai/key", {key: v}); if (!j.ok) { err.textContent = t("keyBad"); return; }
    $("#keyin").value = ""; ["#root", "#top", "#layer"].forEach(x => $(x)._sig = null); await refresh(); if (ST.me.can_ai) ACT.testAi(); },
  clearKey: async () => { await api("/api/ai/key", {key: ""}); ["#root", "#top", "#layer"].forEach(x => $(x)._sig = null); await refresh(); },
  testAi: async () => { if (V.testing) return; V.testing = true; $("#layer")._sig = null; render(); try { await api("/api/ai/test", {}); } catch (e) {} V.testing = false; $("#layer")._sig = null; await refresh(); },
};
document.addEventListener("click", e => {
  const b = e.target.closest("[data-act]");
  if (b && ACT[b.dataset.act]) { SFX.play(b.classList.contains("btn") ? "tap" : "click"); ACT[b.dataset.act](b, e); return; }
  const m = e.target.closest(".mascot"); if (m && !e.target.closest("button") && !e.target.closest(".chat")) pokeMascot(m);
});
document.addEventListener("change", async e => {
  if (e.target.id !== "modelsel") return;
  const j = await api("/api/ai/model", {model: e.target.value}); if (!j.ok) return toast(t("err_" + j.error));
  toast("🧠 " + t("modelDone")); SFX.play("chime"); $("#layer")._sig = null; ["#top"].forEach(x => $(x)._sig = null); await refresh();
});
document.addEventListener("input", e => { if (e.target.id === "vol") { SFX.setVol(e.target.value / 100); SFX.play("pop"); } });
document.addEventListener("keydown", e => { if (e.key === "Escape" && panel) closePanel(); });
