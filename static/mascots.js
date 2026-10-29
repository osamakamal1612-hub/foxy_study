const MASCOTS = {
fox: {name:"Foxy", svg:`<svg viewBox="0 0 120 120" aria-hidden="true">
 <g class="m-tail"><path d="M88 96C118 94 122 62 104 50 108 70 98 80 82 84Z" fill="#ff9600"/><path d="M104 50C113 56 115 66 111 74 109 66 107 58 104 50Z" fill="#fff"/></g>
 <ellipse cx="60" cy="100" rx="25" ry="17" fill="#ff9600"/><ellipse cx="60" cy="104" rx="13" ry="10" fill="#fff4e0"/>
 <ellipse cx="42" cy="114" rx="9" ry="5" fill="#8a4b00"/><ellipse cx="78" cy="114" rx="9" ry="5" fill="#8a4b00"/>
 <g class="m-head">
  <path d="M20 56 24 14 52 36Z" fill="#ff9600"/><path d="M100 56 96 14 68 36Z" fill="#ff9600"/>
  <path d="M27 40 28 26 40 36Z" fill="#7a3f00"/><path d="M93 40 92 26 80 36Z" fill="#7a3f00"/>
  <ellipse cx="60" cy="58" rx="40" ry="34" fill="#ff9600"/>
  <path d="M20 62Q40 94 60 86 80 94 100 62 80 69 60 67 40 69 20 62Z" fill="#fff"/>
  <g class="m-eyes"><ellipse cx="44" cy="54" rx="6" ry="8" fill="#2b2b2b"/><ellipse cx="76" cy="54" rx="6" ry="8" fill="#2b2b2b"/><circle cx="46" cy="51" r="2.4" fill="#fff"/><circle cx="78" cy="51" r="2.4" fill="#fff"/></g>
  <ellipse cx="60" cy="69" rx="6" ry="4.5" fill="#2b2b2b"/>
  <path class="m-mouth" d="M52 77Q60 85 68 77" stroke="#2b2b2b" stroke-width="2.6" fill="none" stroke-linecap="round"/>
 </g></svg>`},
panda: {name:"Pandi", svg:`<svg viewBox="0 0 120 120" aria-hidden="true">
 <ellipse cx="60" cy="100" rx="28" ry="18" fill="#fff" stroke="#e5e5e5" stroke-width="2"/>
 <ellipse cx="32" cy="98" rx="10" ry="14" fill="#2b2b2b" transform="rotate(20 32 98)"/><ellipse cx="88" cy="98" rx="10" ry="14" fill="#2b2b2b" transform="rotate(-20 88 98)"/>
 <ellipse cx="46" cy="114" rx="10" ry="6" fill="#2b2b2b"/><ellipse cx="74" cy="114" rx="10" ry="6" fill="#2b2b2b"/>
 <g class="m-head">
  <circle cx="28" cy="26" r="13" fill="#2b2b2b"/><circle cx="92" cy="26" r="13" fill="#2b2b2b"/>
  <ellipse cx="60" cy="58" rx="38" ry="34" fill="#fff" stroke="#e5e5e5" stroke-width="2"/>
  <ellipse cx="42" cy="54" rx="9" ry="12" fill="#2b2b2b" transform="rotate(-22 42 54)"/><ellipse cx="78" cy="54" rx="9" ry="12" fill="#2b2b2b" transform="rotate(22 78 54)"/>
  <g class="m-eyes"><circle cx="43" cy="53" r="4.2" fill="#fff"/><circle cx="77" cy="53" r="4.2" fill="#fff"/><circle cx="44" cy="54" r="2.2" fill="#2b2b2b"/><circle cx="76" cy="54" r="2.2" fill="#2b2b2b"/></g>
  <ellipse cx="60" cy="68" rx="6" ry="4.5" fill="#2b2b2b"/>
  <path class="m-mouth" d="M52 75Q60 83 68 75" stroke="#2b2b2b" stroke-width="2.6" fill="none" stroke-linecap="round"/>
  <circle cx="32" cy="70" r="5" fill="#ffb3c1" opacity=".7"/><circle cx="88" cy="70" r="5" fill="#ffb3c1" opacity=".7"/>
 </g></svg>`},
robot: {name:"Robo", svg:`<svg viewBox="0 0 120 120" aria-hidden="true">
 <rect x="36" y="88" width="48" height="26" rx="10" fill="#1899d6"/><circle cx="60" cy="101" r="5.5" fill="#ffc800"/>
 <rect x="22" y="92" width="12" height="18" rx="6" fill="#84d8ff"/><rect x="86" y="92" width="12" height="18" rx="6" fill="#84d8ff"/>
 <g class="m-head">
  <line x1="60" y1="30" x2="60" y2="14" stroke="#777" stroke-width="3"/><circle class="m-antenna" cx="60" cy="11" r="6" fill="#ff4b4b"/>
  <rect x="12" y="48" width="10" height="20" rx="5" fill="#84d8ff"/><rect x="98" y="48" width="10" height="20" rx="5" fill="#84d8ff"/>
  <rect x="22" y="28" width="76" height="62" rx="18" fill="#1cb0f6"/>
  <rect x="30" y="37" width="60" height="38" rx="12" fill="#0d3b52"/>
  <g class="m-eyes"><rect x="40" y="45" width="10" height="16" rx="5" fill="#8cff4d"/><rect x="70" y="45" width="10" height="16" rx="5" fill="#8cff4d"/></g>
  <path class="m-mouth" d="M50 68Q60 73 70 68" stroke="#8cff4d" stroke-width="2.6" fill="none" stroke-linecap="round"/>
  <circle cx="30" cy="84" r="2" fill="#fff" opacity=".6"/><circle cx="90" cy="84" r="2" fill="#fff" opacity=".6"/>
 </g></svg>`}
};
const CHAR_STATE = {list: [], byId: {}, phrases: [], modes: {}, v: 0};     // filled from /api/characters (built-in + admin-made characters)
const charInfo = k => CHAR_STATE.byId[k] || {id: k, name: (MASCOTS[k] || {}).name || k, builtin: true, voice: MASCOTS[k] ? k : "fox", anim: "bounce"};
const charName = k => charInfo(k).name;
const charList = () => CHAR_STATE.list.length ? CHAR_STATE.list : Object.keys(MASCOTS).map(id => ({id, name: MASCOTS[id].name, builtin: true}));
function mascotHTML(kind, cls = "") {
  if (MASCOTS[kind]) return `<div class="mascot ${kind} ${cls}" data-kind="${kind}">${MASCOTS[kind].svg}</div>`;
  const c = CHAR_STATE.byId[kind];
  if (c && c.image) return `<div class="mascot custom anim-${c.anim} ${cls}" data-kind="${c.id}"><img src="${c.image}" alt="" draggable="false"></div>`;
  return mascotHTML("fox", cls);
}
function reactMascot(el, anim){            // anim: celebrate | sad | talk
  if(!el) return; el.classList.remove("celebrate","sad"); void el.offsetWidth; el.classList.add(anim);
  setTimeout(()=>el.classList.remove(anim), 1300);
}

/* extra decoration + life: eyes follow the pointer, a book for the "reading" pose */
const BOOK_SVG = `<svg viewBox="0 0 100 60" class="book-svg" aria-hidden="true"><path d="M6 24 50 34 94 24 94 50 50 58 6 50Z" fill="#1899d6"/><path d="M8 20 50 30 50 54 8 46Z" fill="#fff"/><path d="M92 20 50 30 50 54 92 46Z" fill="#e8f6ff"/><path d="M16 28 44 34M16 34 44 40M16 40 44 46M84 28 56 34M84 34 56 40M84 40 56 46" stroke="#bcd" stroke-width="2"/></svg>`;
const STACK_SVG = `<svg viewBox="0 0 100 40" class="stack-svg" aria-hidden="true"><rect x="8" y="22" width="84" height="14" rx="5" fill="#ff7b7b"/><rect x="14" y="12" width="72" height="12" rx="5" fill="#ffc800"/><rect x="20" y="4" width="60" height="10" rx="4" fill="#ff9600" opacity=".0"/></svg>`;
let _eyeRaf = 0, _px = 0, _py = 0;
document.addEventListener("pointermove", e => {
  _px = e.clientX; _py = e.clientY; if (_eyeRaf) return;
  _eyeRaf = requestAnimationFrame(() => {
    _eyeRaf = 0;
    document.querySelectorAll(".mascot").forEach(m => {
      const eyes = m.querySelector(".m-eyes"); if (!eyes) return;
      const r = m.getBoundingClientRect(); if (r.width === 0) return;
      const dx = _px - (r.left + r.width / 2), dy = _py - (r.top + r.height * .45), d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 260) * 3.2;
      eyes.style.translate = `${(dx / d * k).toFixed(2)}px ${(dy / d * k * .8).toFixed(2)}px`;
    });
  });
});
