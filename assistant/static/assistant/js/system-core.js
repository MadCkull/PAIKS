/* system-core.js - PAIKS System Core Background Animation */

window.IS_LOADING = true;

(function() {
  let C_BODY = "168, 85, 247"; // fallback
  let C_HEAD = "210, 140, 255"; // fallback
  let C_TEXT = "#ffffff"; // fallback

  function hexToRgb(hex, fallback) {
    if (!hex) return fallback;
    hex = hex.trim();
    if (hex.startsWith('#')) hex = hex.slice(1);
    if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
    if (hex.length !== 6) return fallback;
    const r = parseInt(hex.substring(0,2), 16);
    const g = parseInt(hex.substring(2,4), 16);
    const b = parseInt(hex.substring(4,6), 16);
    if (isNaN(r) || isNaN(g) || isNaN(b)) return fallback;
    return `${r}, ${g}, ${b}`;
  }

  function updateColors() {
    const cs = getComputedStyle(document.documentElement);
    const accent = cs.getPropertyValue('--accent');
    const accentHover = cs.getPropertyValue('--accent-hover');
    const textPrimary = cs.getPropertyValue('--text-primary');
    if (accent) {
      C_BODY = hexToRgb(accent, '168, 85, 247');
    }
    if (accentHover) {
      C_HEAD = hexToRgb(accentHover, '210, 140, 255');
    }
    if (textPrimary) {
      C_TEXT = textPrimary.trim() || "#ffffff";
    }
  }

  const IDLE = {
    SPEED_MIN: 6.5,
    SPEED_MAX: 11.0,
    TAIL_BASE: 200,
    TAIL_VAR: 0.35,
    BURST_MIN: 2,
    BURST_MAX: 4,
    STAGGER_MIN: 40,
    STAGGER_MAX: 130,
    PAUSE_MIN: 1800,
    PAUSE_MAX: 3600,
    POLL_MS: 100,
  };

  const LOAD = {
    PERIOD_FRAMES: 70,
    TAIL_FRAC: 0.26,
    GAP_MS: 0,
    POLL_MS: 16,
  };

  const SRC_W = 2560;
  const SRC_H = 1600;

  let canvas, ctx;
  let activePulses = [];
  let burstLock = false;
  let watchTimer = null;
  let colorUpdateFrame = 0;

  const RAW_PATHS = [
// ==========================================
        // BUS 1: TOP-RIGHT (Routes North, turns East)
        // ==========================================
        // Main Trunk
        "M 1280 760 L 1280 600 L 1380 500 L 1800 500 L 1900 400 L 2560 400",
        "M 1300 760 L 1300 620 L 1400 520 L 1820 520 L 1920 420 L 2560 420",
        "M 1320 760 L 1320 640 L 1420 540 L 1840 540 L 1940 440 L 2560 440",
        "M 1340 760 L 1340 660 L 1440 560 L 1860 560 L 1960 460 L 2560 460",
        // Splinter Group (Breaks off early East)
        "M 1360 760 L 1360 680 L 1460 580 L 2560 580",
        "M 1380 760 L 1380 700 L 1480 600 L 2560 600",
        "M 1400 760 L 1400 720 L 1500 620 L 2560 620",

        // ==========================================
        // BUS 2: TOP-LEFT (Routes North, turns West)
        // ==========================================
        // Main Trunk
        "M 1260 760 L 1260 600 L 1160 500 L 700 500 L 600 400 L 0 400",
        "M 1240 760 L 1240 620 L 1140 520 L 680 520 L 580 420 L 0 420",
        "M 1220 760 L 1220 640 L 1120 540 L 660 540 L 560 440 L 0 440",
        "M 1200 760 L 1200 660 L 1100 560 L 640 560 L 540 460 L 0 460",
        // Splinter Group (Breaks off early West)
        "M 1180 760 L 1180 680 L 1080 580 L 0 580",
        "M 1160 760 L 1160 700 L 1060 600 L 0 600",
        "M 1140 760 L 1140 720 L 1040 620 L 0 620",

        // ==========================================
        // BUS 3: RIGHT-TOP (Routes East, turns North)
        // ==========================================
        // Main Trunk
        "M 1400 780 L 1600 780 L 1700 680 L 1700 200 L 1900 0",
        "M 1400 800 L 1620 800 L 1720 700 L 1720 220 L 1940 0",
        "M 1400 820 L 1640 820 L 1740 720 L 1740 240 L 1980 0",
        // Splinter Group (Stays horizontal longer)
        "M 1400 760 L 1580 760 L 1680 660 L 2000 660 L 2100 560 L 2560 560",
        "M 1400 740 L 1560 740 L 1660 640 L 2020 640 L 2120 540 L 2560 540",

        // ==========================================
        // BUS 4: RIGHT-BOTTOM (Routes East, turns South)
        // ==========================================
        // Main Trunk
        "M 1400 840 L 1600 840 L 1700 940 L 1700 1400 L 1900 1600",
        "M 1400 860 L 1620 860 L 1720 960 L 1720 1420 L 1900 1600",
        "M 1400 880 L 1640 880 L 1740 980 L 1740 1440 L 1900 1600",
        // Splinter Group (Stays horizontal longer)
        "M 1400 900 L 1580 900 L 1680 1000 L 2000 1000 L 2100 1100 L 2560 1100",
        "M 1400 920 L 1560 920 L 1660 1020 L 2020 1020 L 2120 1120 L 2560 1120",

        // ==========================================
        // BUS 5: BOTTOM-RIGHT (Routes South, turns East)
        // ==========================================
        // Main Trunk
        "M 1280 840 L 1280 1000 L 1380 1100 L 1800 1100 L 1900 1200 L 2560 1200",
        "M 1280 840 L 1280 1020 L 1360 1100 L 1780 1100 L 1880 1200 L 2560 1200",
        "M 1300 840 L 1300 980 L 1400 1080 L 1820 1080 L 1920 1180 L 2560 1180",
        "M 1320 840 L 1320 960 L 1420 1060 L 1840 1060 L 1940 1160 L 2560 1160",
        "M 1340 840 L 1340 940 L 1440 1040 L 1860 1040 L 1960 1140 L 2560 1140",
        // Splinter Group (Drops straight South)
        "M 1360 840 L 1360 920 L 1460 1020 L 1460 1600",
        "M 1380 840 L 1380 900 L 1480 1000 L 1480 1600",
        "M 1400 840 L 1400 880 L 1500 980 L 1500 1600",

        // ==========================================
        // BUS 6: BOTTOM-LEFT (Routes South, turns West)
        // ==========================================
        // Main Trunk
        "M 1260 840 L 1260 1000 L 1160 1100 L 700 1100 L 600 1200 L 0 1200",
        "M 1260 840 L 1260 1020 L 1180 1100 L 720 1100 L 620 1200 L 0 1200",
        "M 1240 840 L 1240 980 L 1140 1080 L 680 1080 L 580 1180 L 0 1180",
        "M 1220 840 L 1220 960 L 1120 1060 L 660 1060 L 560 1160 L 0 1160",
        "M 1200 840 L 1200 940 L 1100 1040 L 640 1040 L 540 1140 L 0 1140",
        // Splinter Group (Drops straight South)
        "M 1180 840 L 1180 920 L 1080 1020 L 1080 1600",
        "M 1160 840 L 1160 900 L 1060 1000 L 1060 1600",
        "M 1140 840 L 1140 880 L 1040 980 L 1040 1600",

        // ==========================================
        // BUS 7: LEFT-TOP (Routes West, turns North)
        // ==========================================
        // Main Trunk
        "M 1160 780 L 960 780 L 860 680 L 860 200 L 660 0",
        "M 1160 800 L 940 800 L 840 700 L 840 220 L 620 0",
        "M 1160 820 L 920 820 L 820 720 L 820 240 L 580 0",
        // Splinter Group (Stays horizontal West)
        "M 1160 760 L 980 760 L 880 660 L 560 660 L 460 560 L 0 560",
        "M 1160 740 L 1000 740 L 900 640 L 540 640 L 440 540 L 0 540",

        // ==========================================
        // BUS 8: LEFT-BOTTOM (Routes West, turns South)
        // ==========================================
        // Main Trunk
        "M 1160 840 L 960 840 L 860 940 L 860 1400 L 660 1600",
        "M 1160 860 L 940 860 L 840 960 L 840 1420 L 660 1600",
        "M 1160 880 L 920 880 L 820 980 L 820 1440 L 660 1600",
        // Splinter Group (Stays horizontal West)
        "M 1160 900 L 980 900 L 880 1000 L 560 1000 L 460 1100 L 0 1100",
        "M 1160 920 L 1000 920 L 900 1020 L 540 1020 L 440 1120 L 0 1120",
  ];

  let PATHS = [];

  // Load Logo
  const logoImg = new Image();
  let logoLoaded = false;
  if (window.PAIKS_LOGO_URL) {
    logoImg.src = window.PAIKS_LOGO_URL;
    logoImg.onload = () => { logoLoaded = true; };
  }

  function parsePath(d, tgtW = 1920, tgtH = 1080, rate = 2) {
    const scale = Math.min(tgtW / SRC_W, tgtH / SRC_H);
    const offX = -(SRC_W * scale) / 2;
    const offY = -(SRC_H * scale) / 2;

    const el = document.createElementNS("http://www.w3.org/2000/svg", "path");
    el.setAttribute("d", d);
    const raw = el.getTotalLength();
    if (raw === 0) return null;

    const pts = [];
    for (let i = 0; i <= raw; i += rate) {
      const p = el.getPointAtLength(i);
      pts.push({ x: p.x * scale + offX, y: p.y * scale + offY });
    }
    const lp = el.getPointAtLength(raw);
    pts.push({ x: lp.x * scale + offX, y: lp.y * scale + offY });

    return { points: pts, length: raw * scale, inUse: false };
  }

  class Pulse {
    constructor(path) {
      this.path = path;
      path.inUse = true;

      if (window.IS_LOADING) {
        this.speed = path.length / LOAD.PERIOD_FRAMES;
        this.tailLen = path.length * LOAD.TAIL_FRAC;
      } else {
        this.speed = IDLE.SPEED_MIN + Math.random() * (IDLE.SPEED_MAX - IDLE.SPEED_MIN);
        this.tailLen = IDLE.TAIL_BASE * (1 - IDLE.TAIL_VAR + Math.random() * IDLE.TAIL_VAR * 2);
      }

      this.dist = 0;
      this.history = [];
      this.active = true;
      this.finishing = false;
    }

    coordAt(d) {
      let acc = 0;
      const pts = this.path.points;
      for (let i = 0; i < pts.length - 1; i++) {
        const dx = pts[i + 1].x - pts[i].x;
        const dy = pts[i + 1].y - pts[i].y;
        const s = Math.sqrt(dx * dx + dy * dy);
        if (acc + s >= d) {
          const t = (d - acc) / s;
          return { x: pts[i].x + dx * t, y: pts[i].y + dy * t };
        }
        acc += s;
      }
      return pts[pts.length - 1];
    }

    update() {
      if (!this.active) return;
      this.dist += this.speed;

      if (!this.finishing) {
        if (this.dist >= this.path.length) {
          this.finishing = true;
        } else {
          const pos = this.coordAt(this.dist);
          this.history.unshift({ x: pos.x, y: pos.y, d: this.dist });
        }
      }

      while (this.history.length > 0 && this.dist - this.history[this.history.length - 1].d > this.tailLen) {
        this.history.pop();
      }

      if (this.history.length === 0) {
        this.active = false;
        this.path.inUse = false;
      }
    }

    draw() {
      if (!this.active || this.history.length < 2) return;

      const len = this.history.length;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      for (let i = 0; i < len - 1; i++) {
        const p1 = this.history[i];
        const p2 = this.history[i + 1];
        const t = i / (len - 1);
        const alpha = Math.pow(1 - t, 2.4) * 0.86;
        const width = 0.85 + (1 - t) * 1.35;

        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.strokeStyle = `rgba(${C_BODY},${alpha.toFixed(3)})`;
        ctx.lineWidth = width;
        ctx.stroke();
      }

      if (this.finishing) return;

      const head = this.history[0];
      const neck = this.history[Math.min(2, len - 1)];

      ctx.beginPath();
      ctx.moveTo(neck.x, neck.y);
      ctx.lineTo(head.x, head.y);
      ctx.strokeStyle = `rgba(${C_HEAD},0.14)`;
      ctx.lineWidth = 14;
      ctx.shadowBlur = 0;
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(neck.x, neck.y);
      ctx.lineTo(head.x, head.y);
      ctx.strokeStyle = `rgba(${C_BODY},0.50)`;
      ctx.lineWidth = 5;
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(neck.x, neck.y);
      ctx.lineTo(head.x, head.y);
      ctx.strokeStyle = "rgba(242,218,255,0.93)";
      ctx.lineWidth = 1.8;
      ctx.shadowBlur = 20;
      ctx.shadowColor = `rgb(${C_HEAD})`;
      ctx.stroke();
      ctx.shadowBlur = 0;

      ctx.beginPath();
      ctx.arc(head.x, head.y, 2.4, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255,252,255,0.97)";
      ctx.shadowBlur = 26;
      ctx.shadowColor = `rgb(${C_HEAD})`;
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }

  function drawCenterLogo() {
    if (!logoLoaded) return;
    ctx.save();
    // No translation needed here if called inside the translated block of animate()
    // but wait, animate() restores context before calling renderTextLight. 
    // I will translate here.
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.globalAlpha = window.IS_LOADING ? 1.0 : 0.2;
    const logoW = 140;
    const logoH = (logoImg.height / logoImg.width) * logoW;
    ctx.drawImage(logoImg, -logoW / 2, -logoH / 2, logoW, logoH);
    ctx.restore();
  }

  function clearWatchTimer() {
    if (watchTimer !== null) {
      clearTimeout(watchTimer);
      watchTimer = null;
    }
  }

  function scheduleWatch(ms) {
    clearWatchTimer();
    watchTimer = setTimeout(watchForCompletion, ms);
  }

  function watchForCompletion() {
    watchTimer = null;
    if (activePulses.length > 0) {
      scheduleWatch(window.IS_LOADING ? LOAD.POLL_MS : IDLE.POLL_MS);
      return;
    }
    burstLock = false;
    const gap = window.IS_LOADING ? LOAD.GAP_MS : IDLE.PAUSE_MIN + Math.random() * (IDLE.PAUSE_MAX - IDLE.PAUSE_MIN);
    setTimeout(triggerBurst, gap);
  }

  function triggerBurst() {
    if (burstLock) return;

    const available = PATHS.filter((p) => !p.inUse);
    if (available.length === 0) {
      setTimeout(triggerBurst, 200);
      return;
    }

    burstLock = true;

    if (window.IS_LOADING) {
      available.forEach((p) => { p.inUse = true; });
      available.forEach((path) => activePulses.push(new Pulse(path)));
      scheduleWatch(LOAD.POLL_MS);
    } else {
      const n = IDLE.BURST_MIN + Math.floor(Math.random() * (IDLE.BURST_MAX - IDLE.BURST_MIN + 1));
      const chosen = available.sort(() => Math.random() - 0.5).slice(0, n);
      chosen.forEach((p) => { p.inUse = true; });

      let stagger = 0;
      let launched = 0;

      chosen.forEach((path) => {
        stagger += IDLE.STAGGER_MIN + Math.random() * (IDLE.STAGGER_MAX - IDLE.STAGGER_MIN);
        setTimeout(() => {
          activePulses.push(new Pulse(path));
          launched++;
          if (launched === chosen.length) scheduleWatch(IDLE.POLL_MS);
        }, stagger);
      });
    }
  }

  window.setLoading = function(state) {
    window.IS_LOADING = state;
    clearWatchTimer();

    for (const p of activePulses) {
      p.active = false;
      p.path.inUse = false;
    }
    activePulses = [];
    burstLock = false;
    PATHS.forEach((p) => { p.inUse = false; });

    setTimeout(triggerBurst, 0);
  };

  function animate() {
    // Clear canvas entirely instead of filling with black to support theming
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Update colors periodically to support theme/accent changes
    colorUpdateFrame++;
    if (colorUpdateFrame % 60 === 0) {
      updateColors();
    }

    ctx.save();
    ctx.translate(canvas.width / 2, canvas.height / 2);

    for (let i = activePulses.length - 1; i >= 0; i--) {
      activePulses[i].update();
      if (!activePulses[i].active) activePulses.splice(i, 1);
    }

    for (const p of activePulses) p.draw();

    ctx.restore();

    drawCenterLogo();
    requestAnimationFrame(animate);
  }

  function init() {
    canvas = document.getElementById("system-core-bg");
    if (!canvas) return; // Exit if not present in the DOM
    
    ctx = canvas.getContext("2d");

    function resize() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      PATHS = RAW_PATHS.map((d) => parsePath(d)).filter(Boolean);
    }
    window.addEventListener("resize", resize);
    
    // Initial color setup
    updateColors();
    resize();
    animate();
    triggerBurst();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
