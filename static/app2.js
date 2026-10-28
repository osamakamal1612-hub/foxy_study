"use strict";
/* ---------- login / first-run setup / navigation / shop / profile / admin ---------- */
function authLang() { return localStorage.getItem("foxy_lang") || ((navigator.language || "").toLowerCase().startsWith("ar") ? "ar" : "tr"); }
function setAuthLang(l) { try { localStorage.setItem("foxy_lang", l); } catch (e) {} lang = l; document.documentElement.lang = l; document.documentElement.dir = l === "ar" ? "rtl" : "ltr"; }

async function boot() {
  setAuthLang(authLang());
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) navigator.serviceWorker.register("/sw.js").catch(() => {});
  try {
    const s = await fetch("/api/session").then(r => r.json());
    $("#banner").hidden = true; AUTH.user = s.user;
    if (s.setup) return showAuth("setup");
    if (!s.user) return showAuth("login");
    startApp();
  } catch (e) { const b = $("#banner"); b.hidden = false; b.textContent = t("offline"); setTimeout(boot, 3000); }
}
function startApp() {
  document.body.removeAttribute("data-auth"); ["#root", "#top", "#widget", "#layer", "#nav"].forEach(x => { const e = $(x); if (e) e._sig = null; });
  panel = null; $("#layer").innerHTML = ""; resetViewCache(); V.view = "map"; ST = null; PREV = null; failN = 0; refresh();
}
function onAuthLost() {
  if (!AUTH.user && document.body.dataset.auth) return;
  AUTH.user = null; clearTimeout(pollT); ST = null; PREV = null; SFX.think(false); chatHist = []; showAuth("login");
}
function showAuth(mode) {
  document.body.dataset.auth = "1"; document.documentElement.dataset.theme = "fox"; setAuthLang(authLang()); panel = null; $("#layer").innerHTML = ""; $("#nav").innerHTML = ""; document.body.classList.remove("has-nav");
  const setup = mode === "setup"; const root = $("#root"); root._sig = null; root._shell = null;
  root.innerHTML = `<div class="auth"><div class="auth-card big-mascot">${mascotHTML("fox")}<h1>${setup ? t("setupT") : t("loginT")}</h1>${setup ? `<p>${t("setupS")}</p>` : ""}
    <form id="authform" autocomplete="on"><input class="txt" id="au" name="username" autocomplete="username" placeholder="${t("username")}" required maxlength="32" autocapitalize="none" spellcheck="false">
    <input class="txt" id="ap" name="password" type="password" autocomplete="${setup ? "new-password" : "current-password"}" placeholder="${t("password")}" required>
    ${setup ? `<input class="txt" id="ap2" type="password" autocomplete="new-password" placeholder="${t("password2")}" required>` : ""}
    <p class="err-text" id="aerr" role="alert"></p><button class="btn" id="abtn" type="submit" style="width:100%">${setup ? t("createAdmin") : t("loginBtn")}</button></form>
    <div class="seg" style="margin-top:14px"><button data-act="authLang" data-v="tr" class="${lang === "tr" ? "on" : ""}">Türkçe</button><button data-act="authLang" data-v="ar" class="${lang === "ar" ? "on" : ""}">العربية</button></div></div></div>`;
  $("#authform").onsubmit = async e => {
    e.preventDefault(); const err = $("#aerr"); err.textContent = "";
    const u = $("#au").value.trim(), p = $("#ap").value;
    if (setup && p !== $("#ap2").value) { err.textContent = t("err_mismatch"); return; }
    $("#abtn").disabled = true;
    try {
      const j = await api(setup ? "/api/setup" : "/api/login", {username: u, password: p});
      if (!j.ok) { err.textContent = t("err_" + j.error) !== "err_" + j.error ? t("err_" + j.error) : t("err_generic"); $("#abtn").disabled = false; return; }
      const s = await fetch("/api/session").then(r => r.json()); AUTH.user = s.user; SFX.play("chime"); startApp();
    } catch (x) { err.textContent = t("offline"); $("#abtn").disabled = false; }
  };
  $("#au").focus();
}

/* ---------- bottom navigation (phone) ---------- */
function renderNav() {
  const nav = $("#nav"), show = ["map", "profile", "shop", "admin"].includes(V.view) && !document.body.dataset.auth;
  document.body.classList.toggle("has-nav", show);
  if (!show) { nav._sig = null; nav.innerHTML = ""; return; }
  const tabs = [["map", "🗺️", t("tabLearn")], ["profile", "🏅", t("tabProfile")], ["shop", "🛒", t("tabShop")]];
  if (ST.me.is_admin) tabs.push(["admin", "🛡️", t("tabAdmin")]);
  setIf(nav, [V.view, lang, ST.me.is_admin].join("|"), el => {
    el.innerHTML = tabs.map(([v, i, l]) => `<button class="${V.view === v ? "on" : ""}" data-act="tab" data-v="${v}"><span class="ti">${i}</span><span>${l}</span></button>`).join("");
  });
}
function goView(v) {
  V.view = v; resetViewCache(); $("#layer")._sig = null; if (panel) closePanel();
  if (v === "admin") loadAdmin(); window.scrollTo({top: 0}); render();
}

/* ---------- profile ---------- */
function renderProfile() {
  const root = $("#root"), st = ST.stats, me = ST.me;
  setIf(root, ["profile", lang, JSON.stringify(st), ST.settings.mascot].join("|"), el => {
    el.innerHTML = `<div class="shell"><div class="card profile-head">${mascotHTML(ST.settings.mascot)}<div><h2 style="margin:0">${esc(me.username)}${me.is_admin ? " 🛡️" : ""}</h2><div class="mut">${t("level")} ${Math.floor(st.xp / 100) + 1}</div></div></div>
      <div class="stat-grid"><div class="card"><b>🔥 ${st.streak}</b><small>${t("streak")}</small></div><div class="card"><b>⚡ ${st.xp}</b><small>${t("xp")}</small></div><div class="card"><b>💎 ${st.gems}</b><small>${t("gems")}</small></div><div class="card"><b>❤️ ${me.is_admin ? "∞" : st.hearts}</b><small>${t("hearts")}</small></div></div>
      ${sideHTML().replace('<aside class="side">', '<div class="side-in">').replace(/<\/aside>$/, "</div>")}</div>`;
  });
}

/* ---------- shop ---------- */
function renderShop() {
  const root = $("#root"), st = ST.stats, me = ST.me, price = ST.constants.heart_price;
  if (root.contains(document.activeElement) && document.activeElement.tagName === "INPUT") return;
  setIf(root, ["shop", lang, st.gems, st.hearts, st.xp, me.is_admin].join("|"), el => {
    const hearts = me.is_admin ? "❤️❤️❤️❤️❤️ ∞" : Array.from({length: 5}, (_, i) => i < st.hearts ? "❤️" : "🖤").join("");
    const item = (id, icon, title, cost, n) => { const full = st.hearts >= 5, poor = !me.is_admin && st.gems < cost;
      return `<div class="card shop-item"><div class="shop-ico">${icon}</div><div class="grow"><b>${title}</b><div class="mut">+${n} ❤️</div></div><button class="btn ${full || poor ? "" : "blue"}" data-act="buy" data-item="${id}" ${full || poor ? "disabled" : ""}>${me.is_admin ? t("free") : cost + " 💎"}</button></div>`; };
    el.innerHTML = `<div class="shell"><h1 style="margin:0">🛒 ${t("shopT")}</h1><p class="mut">${t("shopS")}</p>
      <div class="card center"><div class="hearts-row">${hearts}</div><div style="margin-top:6px">💎 <b>${st.gems}</b> · ⚡ <b>${st.xp}</b></div></div>
      ${item("heart", "❤️", t("buyHeart"), price, 1)}${item("hearts_full", "💖", t("buyFull"), price * 4, 5)}
      <p class="mut">${t("heartRegen")}</p>
      ${me.is_admin ? `<div class="card"><h3>🛡️ ${t("adminTools")}</h3><div class="grant-row" data-uid="${me.id}"><label>${t("addGems")}<input class="txt g-gems" type="number" value="10"></label><label>${t("addXp")}<input class="txt g-xp" type="number" value="0"></label><label>${t("addHearts")}<input class="txt g-hearts" type="number" value="0"></label></div><button class="btn" data-act="adminGrant" style="margin-top:10px">${t("give")}</button></div>` : ""}</div>`;
  });
}

/* ---------- admin dashboard ---------- */
async function loadAdmin() { const j = await api("/api/admin/overview").catch(() => null); if (j?.ok) { V.adm = j; $("#root")._sig = null; if (V.view === "admin") render(); } }
function renderAdmin() {
  const root = $("#root"), A = V.adm; if (!A) { setIf(root, "admload", el => el.innerHTML = `<div class="shell center"><div class="spinner"></div></div>`); return; }
  setIf(root, ["adm", lang, JSON.stringify(A)].join("|"), el => {
    const friends = A.users.filter(u => !u.is_admin);
    const urow = u => `<details class="card urow" data-uid="${u.id}"><summary><b>${esc(u.username)}</b> ${u.is_admin ? `<span class="pill p-wait">${t("adminBadge")}</span>` : ""}${u.has_key ? `<span class="pill p-mid">🔑 ${t("ownKeyBadge")}</span>` : ""}${u.disabled ? `<span class="pill p-bad">${t("disabledB")}</span>` : ""}<span class="mut"> ⚡${u.xp} 💎${u.gems} ❤️${u.hearts} · 📚${u.lessons}</span></summary>
      <div class="grant-row"><label>${t("addGems")}<input class="txt g-gems" type="number" value="0"></label><label>${t("addXp")}<input class="txt g-xp" type="number" value="0"></label><label>${t("addHearts")}<input class="txt g-hearts" type="number" value="0"></label></div>
      <div class="sheet-row" style="margin:8px 0"><button class="btn small" data-act="adminGrant">${t("give")}</button></div>
      ${u.is_admin ? "" : `<input class="txt g-pw" type="password" autocomplete="new-password" placeholder="${t("newPw")}"><div class="sheet-row" style="margin:8px 0"><button class="btn ghost small" data-act="adminPw">${t("resetPw")}</button><button class="btn ghost small" data-act="adminDisable" data-d="${u.disabled ? 0 : 1}">${u.disabled ? t("enable") : t("disable")}</button><button class="btn red small" data-act="adminDelete">${t("delUser")}</button></div>`}</details>`;
    const lrow = l => `<details class="card lrow" data-lid="${l.id}"><summary><b>${esc(l.title)}</b> <span class="pill ${l.shared_all || l.shared.length ? "p-good" : "p-wait"}">${l.shared_all ? t("everyone") : l.shared.length ? t("sharedLbl") + " (" + l.shared.length + ")" : t("private")}</span><span class="mut"> ${t("ownerL")}: ${esc(l.owner_name)}</span></summary>
      <p style="margin:8px 0 4px"><b>${t("visibleTo")}</b></p><label class="chk"><input type="checkbox" data-all ${l.shared_all ? "checked" : ""}> ${t("everyone")}</label>
      ${friends.filter(u => u.id !== l.owner).map(u => `<label class="chk"><input type="checkbox" data-u="${u.id}" ${l.shared.includes(u.id) ? "checked" : ""}> ${esc(u.username)}</label>`).join("") || `<p class="mut">${t("noUsers")}</p>`}
      <div class="sheet-row" style="margin-top:8px"><button class="btn small" data-act="adminShare">${t("saveShare")}</button><button class="btn red small" data-act="adminDelLesson">${t("del")}</button></div></details>`;
    el.innerHTML = `<div class="shell"><h1 style="margin:0">🛡️ ${t("adminT")}</h1>
      <div class="card"><h3>🤖 ${t("aiSettings")}</h3><p class="mut">${t("aiSettingsS")}</p><button class="btn blue" data-act="gear">${t("openSettings")}</button></div>
      <div class="card"><h3>➕ ${t("newUser")}</h3><input class="txt" id="nu_name" placeholder="${t("username")}" autocomplete="off" autocapitalize="none" maxlength="32"><input class="txt" id="nu_pw" type="text" placeholder="${t("password")}" autocomplete="off" style="margin-top:6px"><p class="err-text" id="nu_err"></p><button class="btn" data-act="adminCreate">${t("createUser")}</button></div>
      <h3 style="margin:14px 0 4px">👥 ${t("users")}</h3>${A.users.map(urow).join("")}
      <h3 style="margin:14px 0 4px">📚 ${t("lessonsAdmin")}</h3>${A.lessons.map(lrow).join("") || `<p class="mut">${t("noLessons")}</p>`}</div>`;
  });
}

/* ---------- actions ---------- */
const rowNum = (row, c) => parseInt(row.querySelector(c)?.value || "0", 10) || 0;
Object.assign(ACT, {
  authLang: b => { setAuthLang(b.dataset.v); showAuth($("#ap2") ? "setup" : "login"); },
  tab: b => goView(b.dataset.v), shop: () => goView("shop"), admin: () => goView("admin"), profile: () => goView("profile"),
  logout: async () => { await api("/api/logout", {}).catch(() => {}); AUTH.user = null; clearTimeout(pollT); ST = null; closePanel(); showAuth("login"); },
  savePw: async () => { const err = $("#pwerr"), j = await api("/api/password", {old: $("#pwold").value, new: $("#pwnew").value}); if (!j.ok) { err.textContent = t("err_" + j.error); return; } err.textContent = ""; $("#pwold").value = ""; $("#pwnew").value = ""; toast(t("pwChanged")); SFX.play("chime"); },
  buy: async b => { const j = await api("/api/shop/buy", {item: b.dataset.item}); if (!j.ok) { toast(t("err_" + j.error)); SFX.play("bad"); return; } toast(t("bought")); SFX.play("chest"); reactMascot($(".brand .mascot"), "celebrate"); await refresh(); },
  adminGrant: async b => { const row = b.closest("[data-uid]") || b.closest(".card").querySelector("[data-uid]"), uid = row.dataset.uid;
    const j = await api(`/api/admin/users/${uid}/grant`, {gems: rowNum(row, ".g-gems"), xp: rowNum(row, ".g-xp"), hearts: rowNum(row, ".g-hearts")}); if (!j.ok) return toast(t("err_" + j.error)); toast(t("granted")); SFX.play("chest"); await refresh(); if (V.view === "admin") loadAdmin(); },
  adminCreate: async () => { const err = $("#nu_err"), j = await api("/api/admin/users", {username: $("#nu_name").value.trim(), password: $("#nu_pw").value}); if (!j.ok) { err.textContent = t("err_" + j.error); return; } toast(t("userCreated")); SFX.play("chime"); loadAdmin(); },
  adminPw: async b => { const row = b.closest("[data-uid]"), j = await api(`/api/admin/users/${row.dataset.uid}/password`, {password: row.querySelector(".g-pw").value}); if (!j.ok) return toast(t("err_" + j.error)); toast(t("pwChanged")); row.querySelector(".g-pw").value = ""; },
  adminDisable: async b => { const row = b.closest("[data-uid]"); await api(`/api/admin/users/${row.dataset.uid}/disable`, {disabled: b.dataset.d === "1"}); loadAdmin(); },
  adminDelete: b => { const row = b.closest("[data-uid]"); confirmBox(t("delUserAsk"), t("yes"), async () => { await api(`/api/admin/users/${row.dataset.uid}`, undefined, "DELETE"); closePanel(); loadAdmin(); }); },
  adminShare: async b => { const row = b.closest("[data-lid]"), users = [...row.querySelectorAll("input[data-u]:checked")].map(i => +i.dataset.u), all = row.querySelector("input[data-all]").checked;
    const j = await api(`/api/admin/lessons/${row.dataset.lid}/share`, {users, all}); if (j.ok) { toast(t("shared")); SFX.play("chime"); loadAdmin(); refresh(); } },
  adminDelLesson: b => { const row = b.closest("[data-lid]"); confirmBox(t("delAsk"), t("yes"), async () => { await api(`/api/lessons/${row.dataset.lid}`, undefined, "DELETE"); closePanel(); loadAdmin(); refresh(); }); },
});
boot();
