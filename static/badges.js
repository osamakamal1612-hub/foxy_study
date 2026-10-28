/* Realistic medal-style badge icons (vector, no emoji) */
const BADGES = {
  first_answer: {c1:"#9be22b", c2:"#3f9b00", icon:`<path d="M32 47V33" stroke="#fff" stroke-width="3.6" stroke-linecap="round"/><path d="M32 34C22 35 16.5 28 17.5 20.5 27 20.5 32.5 26 32 34Z" fill="#fff"/><path d="M32 37C41.500 37 46.500 31 45.500 23.500 37 23.500 32 29 32 37Z" fill="#eaffd0"/><ellipse cx="32" cy="48" rx="7" ry="2.4" fill="#2f6f00" opacity=".45"/>`},
  stage1:       {c1:"#59c8ff", c2:"#1466c0", icon:`<path d="M24 48V16.500" stroke="#fff" stroke-width="3.6" stroke-linecap="round"/><path d="M26 18h19.500l-5.200 7.200 5.200 7.200H26Z" fill="#fff"/><ellipse cx="24" cy="48.500" rx="7" ry="2.300" fill="#0d3f7a" opacity=".4"/>`},
  streak3:      {c1:"#ffbd4a", c2:"#e2520a", icon:`<path d="M32 12c2 8.500 11.500 11.500 11.500 23a11.500 11.500 0 0 1-23 0c0-6.500 4.200-9.500 5.500-14.800 2.200 2.200 4.300 3.200 6-8.200Z" fill="#fff"/><path d="M32 29.500c1.200 4.400 5.300 6.300 5.300 10.500a5.300 5.300 0 0 1-10.600 0c0-3.300 3.200-4.500 5.300-10.500Z" fill="#ffc83d"/>`},
  streak7:      {c1:"#ff8585", c2:"#bb1d3a", icon:`<path d="M32 13l5.600 11.400 12.500 1.800-9 8.800 2.100 12.500L32 41.700 20.800 47.500l2.100-12.500-9-8.800 12.500-1.800Z" fill="#fff"/><text x="32" y="38.500" text-anchor="middle" font-size="14" font-weight="900" fill="#bb1d3a" font-family="Nunito,Arial,sans-serif">7</text>`},
  xp100:        {c1:"#ffe56a", c2:"#dd9a00", icon:`<path d="M35.500 11 20.500 35h9.500l-3 18 17-26H34Z" fill="#fff"/>`},
  xp500:        {c1:"#dcaaff", c2:"#7433c8", icon:`<path d="M32 11c8.500 6 10.500 17 8.500 27.500h-17C21.500 28 23.500 17 32 11Z" fill="#fff"/><circle cx="32" cy="26" r="4.600" fill="#7433c8"/><path d="M23.500 38.500 17.500 47l8.500-2.500ZM40.500 38.500 46.500 47l-8.500-2.500Z" fill="#f2dcff"/><path d="M28.500 41.500h7L32 52Z" fill="#ffd34d"/>`},
  perfect:      {c1:"#ff91b5", c2:"#cf2058", icon:`<text x="32" y="39.500" text-anchor="middle" font-size="19" font-weight="900" font-style="italic" fill="#fff" font-family="Nunito,Arial,sans-serif" stroke="#a3123f" stroke-width=".6">100</text>`},
  exam:         {c1:"#ffe78f", c2:"#d6920a", icon:`<path d="M22 13h20v12.500a10 10 0 0 1-20 0Z" fill="#fff"/><path d="M22 17.500h-6.500c0 7.500 3.200 10.800 8.500 11.800M42 17.500h6.500c0 7.500-3.200 10.800-8.500 11.800" fill="none" stroke="#fff" stroke-width="3"/><rect x="29" y="35" width="6" height="8" fill="#fff"/><rect x="21.500" y="43" width="21" height="5.500" rx="2.200" fill="#fff"/>`}
};
function badgeSVG(id) {
  const b = BADGES[id], u = "bg" + id;
  return `<svg class="ico" viewBox="0 0 64 64" aria-hidden="true"><defs>
    <linearGradient id="${u}a" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${b.c1}"/><stop offset="1" stop-color="${b.c2}"/></linearGradient>
    <linearGradient id="${u}b" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${b.c2}"/><stop offset="1" stop-color="${b.c1}"/></linearGradient></defs>
    <circle cx="32" cy="32" r="29.500" fill="url(#${u}b)"/><circle cx="32" cy="32" r="24.500" fill="url(#${u}a)"/>
    <circle cx="32" cy="32" r="24.500" fill="none" stroke="rgba(255,255,255,.6)" stroke-width="1.500"/>
    <circle cx="32" cy="32" r="29" fill="none" stroke="rgba(0,0,0,.18)" stroke-width="1"/>${b.icon}
    <path d="M11 27C13 14.500 26 8 39 9 28 13.500 20 21 18 33Z" fill="#fff" opacity=".3"/></svg>`;
}
