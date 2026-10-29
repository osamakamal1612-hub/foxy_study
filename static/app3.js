"use strict";
/* ---------- admin dashboard (users, lessons, characters, colours, phrases) and teacher monitor ---------- */
const DEFAULT_THEME = {fox: {pri: "#ff9600", sec: "#1cb0f6", bg: "#ffffff", card: "#ffffff", txt: "#3c3c3c"}, robot: {pri: "#1cb0f6", sec: "#58cc02", bg: "#ffffff", card: "#ffffff", txt: "#3c3c3c"}, panda: {pri: "#4b4b4b", sec: "#8a8a8a", bg: "#ffffff", card: "#ffffff", txt: "#3c3c3c"}};
const COLOR_KEYS = [["pri", "colPri"], ["sec", "colSec"], ["bg", "colBg"], ["card", "colCard"], ["txt", "colTxt"]];
const ago = ts => { if (!ts) return t("never"); const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60)); return m < 60 ? `${m} ${t("minAgo")}` : m < 1440 ? `${Math.round(m / 60)} ${t("hrAgo")}` : `${Math.round(m / 1440)} ${t("dayAgo")}`; };

async function loadAdmin() { const j = await api("/api/admin/overview").catch(() => null); if (j?.ok) { V.adm = j; $("#root")._sig = null; if (V.view === "admin") render(); } }
async function loadMonitor() { const j = await api("/api/monitor").catch(() => null); if (j?.ok) { V.mon = j; $("#root")._sig = null; if (V.view === "monitor") render(); } }

/* ---- characters ---- */
function themeOf(c) { return c?.theme || DEFAULT_THEME[c?.id] || DEFAULT_THEME.fox; }
function charForm(c) {
  const th = themeOf(c), builtin = !!c?.builtin;
  const opt = (v, cur, label) => `<option value="${v}" ${v === cur ? "selected" : ""}>${label}</option>`;
  return `<details class="card char-card" data-cid="${c ? esc(c.id) : ""}"><summary>${c ? `<span class="char-av">${mascotHTML(c.id)}</span> <b>${esc(c.name)}</b>${builtin ? ` <span class="pill p-wait">${t("builtin")}</span>` : ""}` : `➕ <b>${t("newChar")}</b>`}</summary>
  ${builtin ? "" : `<input class="txt c-name" placeholder="${t("charName")}" maxlength="24" value="${esc(c?.name || "")}"><input class="txt c-title" style="margin-top:6px" placeholder="${t("charTitle")}" maxlength="30" value="${esc(c?.title || "")}">
    <label class="file"><input type="file" class="c-img" accept="image/png,image/jpeg,image/webp,image/gif"><b>🖼️ ${t("charImage")}</b><span class="c-imgn">${c?.image ? "✔" : t("chooseFile")}</span></label>
    <div class="c-prev" style="text-align:center">${c?.image ? `<img src="${c.image}" alt="" style="max-height:90px">` : ""}</div>
    <div class="grant-row" style="grid-template-columns:1fr 1fr"><label>${t("charAnim")}<select class="txt-sel c-anim">${[["bounce", "animBounce"], ["jump", "animJump"], ["roll", "animRoll"], ["zoom", "animZoom"], ["wiggle", "animWiggle"]].map(([v, k]) => opt(v, c?.anim || "bounce", t(k))).join("")}</select></label>
    <label>${t("charVoice")}<select class="txt-sel c-voice">${[["fox", "voiceFox"], ["panda", "voicePanda"], ["robot", "voiceRobot"]].map(([v, k]) => opt(v, c?.voice || "fox", t(k))).join("")}</select></label></div>
    <label class="mut" style="display:block;margin-top:8px">${t("charPersona")}<textarea class="txt c-persona" maxlength="200">${esc(c?.persona || "")}</textarea></label>`}
  <p style="margin:10px 0 0"><b>🎨 ${t("colors")}</b></p><div class="theme-row">${COLOR_KEYS.map(([k, l]) => `<label>${t(l)}<input type="color" class="c-${k}" value="${th[k]}"></label>`).join("")}</div>
  <div class="theme-prev"><b>${t("preview")}</b><div class="tp-card">${t("previewText")} <span class="tp-btn">OK</span></div></div>
  <div class="sheet-row" style="margin-top:8px"><button class="btn small" data-act="charSave">${t("saveChar")}</button>${c ? `<button class="btn ghost small" data-act="charReset">${t("resetColors")}</button>` : ""}${c && !builtin ? `<button class="btn red small" data-act="charDelete">${t("delChar")}</button>` : ""}</div></details>`;
}
function paintPreview(form) {
  const th = Object.fromEntries(COLOR_KEYS.map(([k]) => [k, form.querySelector(".c-" + k).value])), pv = form.querySelector(".theme-prev"), card = pv.querySelector(".tp-card"), btn = pv.querySelector(".tp-btn");
  pv.style.background = th.bg; pv.style.color = th.txt; card.style.background = th.card; btn.style.background = th.pri; btn.style.color = lum(th.pri) > .62 ? "#1b1b1b" : "#fff"; btn.style.boxShadow = "0 3px 0 " + mix(th.pri, "#000000", .25); card.style.border = "2px solid " + mix(th.bg, th.txt, .14); card.style.borderInlineStart = "6px solid " + th.sec;
}
const readTheme = form => Object.fromEntries(COLOR_KEYS.map(([k]) => [k, form.querySelector(".c-" + k).value]));
function fileToDataURL(file, max = 256) {
  return new Promise((res, rej) => { const img = new Image(), u = URL.createObjectURL(file); img.onload = () => { const k = Math.min(1, max / Math.max(img.width, img.height)), c = document.createElement("canvas"); c.width = Math.max(1, Math.round(img.width * k)); c.height = Math.max(1, Math.round(img.height * k)); c.getContext("2d").drawImage(img, 0, 0, c.width, c.height); URL.revokeObjectURL(u); res(c.toDataURL("image/png")); }; img.onerror = () => { URL.revokeObjectURL(u); rej(new Error("img")); }; img.src = u; });
}

/* ---- phrases ---- */
function phrasesHTML() {
  const targets = [["all", t("allChars")], ...charList().map(c => [c.id, c.name])], f = V.pfilter || "*";
  const sel = (cls, opts, cur) => `<select class="txt-sel ${cls}">${opts.map(([v, l]) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  const langs = [["any", t("langAny")], ["tr", "Türkçe"], ["ar", "العربية"]], kinds = [["click", t("kClick")], ["bubble", t("kBubble")], ["both", t("kBoth")]];
  const row = p => `<div class="prow" data-pid="${p ? esc(p.id) : ""}"><input class="txt p-text" maxlength="120" placeholder="${t("phText")}" value="${esc(p?.text || "")}"><div class="sel">${sel("p-target", targets, p?.target || "all")}${sel("p-lang", langs, p?.lang || "any")}${sel("p-kind", kinds, p?.kind || "click")}</div>
    <div class="sheet-row"><button class="btn small" data-act="phSave">${p ? "💾" : "➕ " + t("addPhrase")}</button>${p ? `<button class="btn red small" data-act="phDel">🗑</button>` : ""}</div></div>`;
  const list = CHAR_STATE.phrases.filter(p => f === "*" || p.target === f);
  return `<div class="card"><p class="mut" style="margin:0 0 8px">${t("phraseHelp")}</p>
    <div class="grant-row" style="grid-template-columns:1fr 1fr">${targets.map(([id, l]) => `<label>${esc(l)}<select class="txt-sel pm" data-target="${esc(id)}">${[["random", t("random")], ["sequence", t("sequence")]].map(([v, vl]) => `<option value="${v}" ${(CHAR_STATE.modes[id] || (id !== "all" && CHAR_STATE.modes.all) || "random") === v ? "selected" : ""}>${vl}</option>`).join("")}</select></label>`).join("")}</div>
    <h4 style="margin:14px 0 4px">➕ ${t("addPhrase")}</h4><div id="newphrase">${row(null)}</div>
    <h4 style="margin:14px 0 4px">${t("filter")}: ${sel("p-filter", [["*", "—"], ...targets], f)}</h4>${list.map(row).join("") || `<p class="mut">—</p>`}</div>`;
}

/* ---- admin view ---- */
function renderAdmin() {
  const root = $("#root"), A = V.adm; if (!A) { setIf(root, "admload", el => el.innerHTML = `<div class="shell center"><div class="spinner"></div></div>`); return; }
  if (root.contains(document.activeElement) && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
  setIf(root, ["adm", lang, JSON.stringify(A), CHAR_STATE.v, V.pfilter].join("|"), el => {
    const friends = A.users.filter(u => !u.is_admin);
    const urow = u => `<details class="card urow" data-uid="${u.id}"><summary><b>${esc(u.username)}</b> <span class="pill ${u.is_admin ? "p-wait" : u.role === "teacher" ? "p-good" : "p-none"}">${t("role_" + u.role)}</span>${u.has_key ? `<span class="pill p-mid">🔑 ${t("ownKeyBadge")}</span>` : ""}${u.disabled ? `<span class="pill p-bad">${t("disabledB")}</span>` : ""}<span class="mut"> ⚡${u.xp} 💎${u.gems} ❤️${u.hearts} · 📚${u.lessons} · ${ago(u.last_active)}</span></summary>
      <div class="grant-row"><label>${t("addGems")}<input class="txt g-gems" type="number" value="0"></label><label>${t("addXp")}<input class="txt g-xp" type="number" value="0"></label><label>${t("addHearts")}<input class="txt g-hearts" type="number" value="0"></label></div>
      <div class="sheet-row" style="margin:8px 0"><button class="btn small" data-act="adminGrant">${t("give")}</button></div>
      ${u.is_admin ? "" : `<input class="txt g-pw" type="password" autocomplete="new-password" placeholder="${t("newPw")}"><div class="sheet-row" style="margin:8px 0"><button class="btn ghost small" data-act="adminPw">${t("resetPw")}</button><button class="btn ghost small" data-act="adminRole" data-r="${u.role === "teacher" ? "student" : "teacher"}">${u.role === "teacher" ? t("makeStudent") : t("makeTeacher")}</button><button class="btn ghost small" data-act="adminDisable" data-d="${u.disabled ? 0 : 1}">${u.disabled ? t("enable") : t("disable")}</button><button class="btn red small" data-act="adminDelete">${t("delUser")}</button></div>`}</details>`;
    const lrow = l => `<details class="card lrow" data-lid="${l.id}"><summary><b>${esc(l.title)}</b> <span class="pill ${l.shared_all || l.shared.length ? "p-good" : "p-wait"}">${l.shared_all ? t("everyone") : l.shared.length ? t("sharedLbl") + " (" + l.shared.length + ")" : t("private")}</span><span class="mut"> ${t("ownerL")}: ${esc(l.owner_name)}</span></summary>
      <p style="margin:8px 0 4px"><b>${t("visibleTo")}</b></p><label class="chk"><input type="checkbox" data-all ${l.shared_all ? "checked" : ""}> ${t("everyone")}</label>
      ${friends.filter(u => u.id !== l.owner).map(u => `<label class="chk"><input type="checkbox" data-u="${u.id}" ${l.shared.includes(u.id) ? "checked" : ""}> ${esc(u.username)} <span class="mut">(${t("role_" + u.role)})</span></label>`).join("") || `<p class="mut">${t("noUsers")}</p>`}
      <div class="sheet-row" style="margin-top:8px"><button class="btn small" data-act="adminShare">${t("saveShare")}</button><button class="btn red small" data-act="adminDelLesson">${t("del")}</button></div></details>`;
    el.innerHTML = `<div class="shell"><h1 style="margin:0">🛡️ ${t("adminT")}</h1>
      <div class="card"><h3>🤖 ${t("aiSettings")}</h3><p class="mut">${t("aiSettingsS")}</p><button class="btn blue" data-act="gear">${t("openSettings")}</button></div>
      <div class="card"><h3>➕ ${t("newUser")}</h3><input class="txt" id="nu_name" placeholder="${t("username")}" autocomplete="off" autocapitalize="none" maxlength="32"><input class="txt" id="nu_pw" type="text" placeholder="${t("password")}" autocomplete="off" style="margin-top:6px">
        <select class="txt-sel" id="nu_role" style="margin-top:6px"><option value="student">${t("role_student")}</option><option value="teacher">${t("role_teacher")}</option></select><p class="err-text" id="nu_err"></p><button class="btn" data-act="adminCreate">${t("createUser")}</button></div>
      <h3 style="margin:14px 0 4px">👥 ${t("users")}</h3>${A.users.map(urow).join("")}
      <h3 style="margin:14px 0 4px">📚 ${t("lessonsAdmin")}</h3>${A.lessons.map(lrow).join("") || `<p class="mut">${t("noLessons")}</p>`}
      <h3 style="margin:14px 0 4px">🎭 ${t("charsT")}</h3>${charList().map(charForm).join("")}${charForm(null)}
      <h3 style="margin:14px 0 4px">💬 ${t("phrasesT")}</h3>${phrasesHTML()}</div>`;
    el.querySelectorAll(".char-card").forEach(paintPreview);
  });
}

/* ---- teacher / admin monitor ---- */
function renderMonitor() {
  const root = $("#root"), M = V.mon; if (!M) { setIf(root, "monload", el => el.innerHTML = `<div class="shell center"><div class="spinner"></div></div>`); return; }
  if (root.contains(document.activeElement) && document.activeElement.tagName === "INPUT") return;
  setIf(root, ["mon", lang, JSON.stringify(M), JSON.stringify(ST.lessons.map(l => l.id))].join("|"), el => {
    const sc = a => a === null || a === undefined ? "p-none" : a >= 75 ? "p-good" : a >= 50 ? "p-mid" : "p-bad";
    const urow = u => `<details class="card urow"><summary><b>${esc(u.username)}</b> <span class="pill ${u.role === "teacher" ? "p-good" : "p-none"}">${t("role_" + u.role)}</span><span class="mut"> ⚡${u.xp} 🔥${u.streak} ❤️${u.hearts} · ${t("lastSeen")}: ${ago(u.last_active)}</span></summary>
      ${u.lessons.map(l => `<div class="mon-lesson"><div class="sheet-row"><b>${esc(l.title)}</b><span class="pill ${sc(l.avg)}">${l.avg === null ? "—" : l.avg + "%"}</span></div>
        <div class="bar-mini"><i style="width:${l.stages ? Math.round(l.passed / l.stages * 100) : 0}%"></i></div>
        <div class="mut">${t("stagesPassed", {a: l.passed, b: l.stages})} · ${l.answered}/${l.total_q} · ${l.attempts} ${t("attemptsL")}</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">${l.stage_list.map(s => `<span class="pill ${s.passed ? "p-good" : sc(s.avg)}" title="${esc(s.title)}">${esc(s.title.slice(0, 18))}: ${s.avg === null ? (s.answered ? "…" : "—") : s.avg + "%"}</span>`).join("")}</div></div>`).join("") || `<p class="mut">—</p>`}</details>`;
    const students = M.users.filter(u => u.role === "student"), mine = ST.me.is_teacher ? ST.lessons.filter(l => l.can_manage) : [];
    const lshare = l => `<details class="card lrow" data-lid="${l.id}"><summary><b>${esc(l.title)}</b></summary><p style="margin:8px 0 4px"><b>${t("visibleTo")}</b></p>
      ${students.map(u => `<label class="chk"><input type="checkbox" data-u="${u.id}" ${(V.sharedMap?.[l.id] || []).includes(u.id) ? "checked" : ""}> ${esc(u.username)}</label>`).join("") || `<p class="mut">${t("noStudents")}</p>`}
      <label class="chk"><input type="checkbox" data-all ${V.sharedAll?.[l.id] ? "checked" : ""}> ${t("everyone")}</label><div class="sheet-row" style="margin-top:8px"><button class="btn small" data-act="adminShare">${t("saveShare")}</button></div></details>`;
    el.innerHTML = `<div class="shell"><h1 style="margin:0">📊 ${t("monitorT")}</h1>${mine.length ? `<h3 style="margin:14px 0 4px">📚 ${t("myLessons")}</h3>${mine.map(lshare).join("")}` : ""}
      <h3 style="margin:14px 0 4px">👥 ${t("users")}</h3>${M.users.map(urow).join("") || `<p class="mut">${t("noStudents")}</p>`}</div>`;
  });
}

/* ---------- actions ---------- */
const val = (root, sel) => root.querySelector(sel)?.value;
Object.assign(ACT, {
  monitor: () => goView("monitor"),
  adminCreate: async () => { const err = $("#nu_err"), j = await api("/api/admin/users", {username: $("#nu_name").value.trim(), password: $("#nu_pw").value, role: $("#nu_role").value}); if (!j.ok) { err.textContent = t("err_" + j.error); return; } toast(t("userCreated")); SFX.play("chime"); loadAdmin(); },
  adminRole: async b => { const row = b.closest("[data-uid]"), j = await api(`/api/admin/users/${row.dataset.uid}/role`, {role: b.dataset.r}); if (!j.ok) return toast(t("err_" + (j.error || "forbidden"))); SFX.play("chime"); loadAdmin(); },
  charSave: async b => {
    const f = b.closest("[data-cid]"), cid = f.dataset.cid, builtin = !!CHAR_STATE.byId[cid]?.builtin, theme = readTheme(f);
    try {
      if (builtin) { const j = await api("/api/admin/theme", {char: cid, theme}); if (!j.ok) return toast(t("err_" + j.error)); }
      else {
        const body = {id: cid || undefined, name: val(f, ".c-name"), title: val(f, ".c-title"), anim: val(f, ".c-anim"), voice: val(f, ".c-voice"), persona: val(f, ".c-persona"), theme};
        const file = f.querySelector(".c-img").files[0]; if (file) body.image = await fileToDataURL(file);
        const j = await api("/api/admin/characters", body); if (!j.ok) return toast("⚠️ " + (t("err_" + j.error) !== "err_" + j.error ? t("err_" + j.error) : j.error));
      }
      toast(t("charSaved")); SFX.play("chime"); await loadChars(); V.adm && (V.adm = {...V.adm}); $("#root")._sig = null; render();
    } catch (e) { toast(t("err_bad_image")); }
  },
  charReset: async b => { const cid = b.closest("[data-cid]").dataset.cid; await api("/api/admin/theme", {char: cid, theme: null}); toast(t("charSaved")); await loadChars(); $("#root")._sig = null; render(); },
  charDelete: b => { const cid = b.closest("[data-cid]").dataset.cid; confirmBox(t("charDelAsk"), t("yes"), async () => { await api(`/api/admin/characters/${cid}`, undefined, "DELETE"); closePanel(); await loadChars(); $("#root")._sig = null; render(); refresh(); }); },
  phSave: async b => {
    const r = b.closest(".prow"), pid = r.dataset.pid, body = {action: pid ? "update" : "add", id: pid || undefined, text: val(r, ".p-text"), target: val(r, ".p-target"), lang: val(r, ".p-lang"), kind: val(r, ".p-kind")};
    const j = await api("/api/admin/phrases", body); if (!j.ok) return toast(t("err_" + j.error)); toast(t("charSaved")); SFX.play("pop"); await loadChars(); $("#root")._sig = null; render();
  },
  phDel: async b => { const pid = b.closest(".prow").dataset.pid; await api("/api/admin/phrases", {action: "delete", id: pid}); SFX.play("pop"); await loadChars(); $("#root")._sig = null; render(); },
});
document.addEventListener("input", e => { const f = e.target.closest?.(".char-card"); if (f && e.target.type === "color") paintPreview(f); });
document.addEventListener("change", async e => {
  const t0 = e.target;
  if (t0.classList.contains("pm")) { const j = await api("/api/admin/phrase_mode", {target: t0.dataset.target, mode: t0.value}); if (j.ok) { toast(t("charSaved")); SFX.play("toggle"); await loadChars(); } }
  else if (t0.classList.contains("p-filter")) { V.pfilter = t0.value; $("#root")._sig = null; render(); }
  else if (t0.classList.contains("c-img") && t0.files[0]) { const f = t0.closest(".char-card"); f.querySelector(".c-imgn").textContent = t0.files[0].name; try { const u = await fileToDataURL(t0.files[0]); f.querySelector(".c-prev").innerHTML = `<img src="${u}" alt="" style="max-height:90px">`; } catch (x) {} }
});
boot();
