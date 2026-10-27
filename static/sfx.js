/* Synthesised sound effects (Web Audio) - no audio files needed */
const SFX = (() => {
  let ctx = null, master = null, on = true, vol = 0.7, thinkT = null, lastBlip = 0, flip = false;
  try { const v = localStorage.getItem("foxy_vol"); if (v !== null && v !== "") vol = Math.min(1, Math.max(0, +v)); } catch (e) {}
  function ac() {
    if (!ctx) { try { ctx = new (window.AudioContext || window.webkitAudioContext)(); master = ctx.createGain(); master.gain.value = vol; master.connect(ctx.destination); } catch (e) { return null; } }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }
  function tone(f, d = .12, o = {}) {
    const c = ac(); if (!c || !on || vol <= 0) return;
    const t = c.currentTime + (o.at || 0), osc = c.createOscillator(), g = c.createGain();
    osc.type = o.type || "sine"; osc.frequency.setValueAtTime(f, t);
    if (o.to) osc.frequency.exponentialRampToValueAtTime(o.to, t + d);
    const v = o.v ?? .2; g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(v, t + (o.a || .006)); g.gain.exponentialRampToValueAtTime(.0001, t + d);
    osc.connect(g); g.connect(master); osc.start(t); osc.stop(t + d + .03);
  }
  function noise(d = .2, o = {}) {
    const c = ac(); if (!c || !on || vol <= 0) return;
    const t = c.currentTime + (o.at || 0), n = Math.floor(c.sampleRate * d), buf = c.createBuffer(1, n, c.sampleRate), data = buf.getChannelData(0);
    for (let i = 0; i < n; i++) data[i] = Math.random() * 2 - 1;
    const src = c.createBufferSource(); src.buffer = buf;
    const f = c.createBiquadFilter(); f.type = "bandpass"; f.Q.value = 1.2; f.frequency.setValueAtTime(o.f0 || 600, t); f.frequency.exponentialRampToValueAtTime(o.f1 || 3000, t + d);
    const g = c.createGain(); g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(o.v ?? .18, t + d * .3); g.gain.exponentialRampToValueAtTime(.0001, t + d);
    src.connect(f); f.connect(g); g.connect(master); src.start(t); src.stop(t + d + .02);
  }
  const seq = (notes, step, o = {}) => notes.forEach((f, i) => tone(f, o.d || step * 1.6, {...o, at: i * step}));
  const R = x => x * (0.94 + Math.random() * .12);
  const S = {
    click: () => { tone(R(720), .05, {type: "triangle", v: .16}); tone(R(1100), .04, {at: .02, type: "triangle", v: .08}); },
    tap: () => tone(R(520), .08, {type: "square", v: .07, to: 800}),
    key: () => tone(R(1500), .02, {type: "square", v: .025}),
    send: () => { noise(.2, {f0: 400, f1: 2800, v: .12}); tone(660, .08, {at: .12, type: "triangle", v: .1, to: 990}); },
    flip: () => noise(.12, {f0: 1500, f1: 600, v: .1}),
    whoosh: () => noise(.25, {f0: 300, f1: 3000, v: .1}),
    good: () => seq([523, 659, 784, 1047], .09, {type: "triangle", v: .2}),
    perfect: () => { seq([523, 659, 784, 1047, 1319], .08, {type: "triangle", v: .2}); seq([2093, 2637], .09, {type: "sine", v: .08, at: .35}); },
    mid: () => seq([440, 554], .12, {type: "triangle", v: .18}),
    bad: () => { tone(300, .3, {type: "sawtooth", v: .1, to: 140}); tone(220, .3, {at: .16, type: "triangle", v: .12, to: 110}); },
    fanfare: () => { seq([523, 523, 523, 659, 784, 659, 784, 1047], .11, {type: "triangle", v: .2, d: .16}); tone(1047, .5, {at: .88, type: "triangle", v: .22}); tone(523, .5, {at: .88, type: "sine", v: .12}); },
    sad: () => { [392, 370, 349].forEach((f, i) => tone(f, .28, {at: i * .26, type: "sawtooth", v: .09})); tone(311, .7, {at: .78, type: "sawtooth", v: .09, to: 250}); },
    ding: () => { tone(988, .14, {v: .16}); tone(1319, .3, {at: .1, v: .16}); },
    boing: () => { tone(160, .35, {type: "sine", v: .26, to: 520}); tone(520, .2, {at: .3, type: "sine", v: .12, to: 300}); },
    pop: () => tone(900, .07, {v: .22, to: 280}),
    sparkle: () => seq([1047, 1319, 1568, 2093], .06, {type: "sine", v: .12, d: .2}),
    chest: () => { noise(.35, {f0: 200, f1: 500, v: .1}); seq([1319, 1760, 1319, 1760, 2349], .07, {type: "square", v: .06, d: .1, at: .1}); },
    oops: () => { tone(392, .14, {type: "triangle", v: .18}); tone(311, .3, {at: .14, type: "triangle", v: .18, to: 262}); },
    chime: () => seq([784, 988, 1175, 1568], .1, {type: "sine", v: .15, d: .3}),
    giggle: () => seq([880, 1100, 940, 1250], .06, {type: "triangle", v: .13, d: .08}),
    toggle: () => tone(flip ? 500 : 800, .08, {type: "triangle", v: .15}),
    tick: () => tone(1000, .03, {type: "square", v: .04}),
    tock: () => tone(720, .04, {type: "square", v: .04}),
    blip: kind => {
      const now = performance.now(); if (now - lastBlip < 55) return; lastBlip = now;
      if (kind === "panda") tone(R(280), .07, {type: "sine", v: .17});
      else if (kind === "robot") tone(R(420 + Math.floor(Math.random() * 4) * 90), .04, {type: "square", v: .05});
      else tone(R(700), .05, {type: "triangle", v: .1});
    }
  };
  return {
    play(name, arg) { try { (S[name] || (() => {}))(arg); } catch (e) {} },
    unlock: ac,
    setOn(v) { on = !!v; if (!on) this.think(false); },
    get vol() { return vol; },
    setVol(v) { vol = Math.min(1, Math.max(0, v)); if (master) master.gain.value = vol; try { localStorage.setItem("foxy_vol", String(vol)); } catch (e) {} },
    think(v) {                                   // soft tick-tock while we wait for the AI
      if (v && !thinkT) { thinkT = setInterval(() => { flip = !flip; S[flip ? "tick" : "tock"](); }, 750); }
      if (!v && thinkT) { clearInterval(thinkT); thinkT = null; }
    }
  };
})();
document.addEventListener("pointerdown", () => SFX.unlock(), {once: true});
