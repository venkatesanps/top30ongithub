/*
 * motion_probe.js: find out HOW a page's motion is built before trying to copy it.
 *
 * Paste into the browser console on the page (or run through a browser tool's
 * "execute JavaScript"), wait for it to finish, and save the printed JSON as probe.json.
 * Then: python3 motion_report.py probe.json
 *
 * Read-only, with two deliberate interactions: it scrolls the page a little and back,
 * and it waits ~1.5 s to see what changes on its own. It NEVER calls getContext() on a
 * canvas: doing so on a canvas the page hasn't initialised yet would claim it for the
 * wrong context type and break the page's own drawing.
 *
 * Part of the top30-ui plugin (github.com/venkatesanps/top30ongithub). MIT.
 */
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const frames = (n) => new Promise((r) => { let k = 0; const f = () => (++k >= n ? r() : requestAnimationFrame(f)); requestAnimationFrame(f); });
  const count = (s, re) => (s.match(re) || []).length;
  const sel = (el) => {
    if (!el || !el.tagName) return '';
    const cls = (el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className || '').toString().trim().split(/\s+/).filter(Boolean).slice(0, 2).join('.');
    return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (cls ? '.' + cls : '');
  };

  // ---- libraries and frameworks -------------------------------------------
  const GLOBALS = ['gsap', 'ScrollTrigger', 'TweenMax', 'anime', 'Motion', 'Lenis', 'lenis', 'LocomotiveScroll', 'THREE', 'PIXI',
    'lottie', 'bodymovin', 'rive', 'Webflow', 'Barba', 'barba', 'Swup', 'SplitType', 'Splitting', 'p5', 'Matter', 'Spline', '__NEXT_DATA__', '__NUXT__'];
  const globals = GLOBALS.filter((k) => { try { return k in window; } catch (e) { return false; } });
  const scripts = [...document.scripts].map((s) => ({ src: s.src || null, inlineBytes: s.src ? 0 : s.textContent.length, type: s.type || '' }));
  const srcText = scripts.map((s) => s.src || '').join(' ').toLowerCase();
  const SRC_HINTS = { gsap: /gsap|greensock|scrolltrigger/, three: /three(\.module)?(\.min)?\.js|\/three@/, lottie: /lottie|bodymovin/, rive: /rive/,
    framer: /framer|framerusercontent/, webflow: /webflow/, lenis: /lenis/, pixi: /pixi/, spline: /splinetool|spline/, swiper: /swiper/, motion: /framer-motion|motion@/ };
  const fromSrc = Object.keys(SRC_HINTS).filter((k) => SRC_HINTS[k].test(srcText));
  const domHints = {
    framer: !!document.querySelector('[data-framer-name],[data-framer-component-type]'),
    webflow: /\bw-mod-js\b/.test(document.documentElement.className) || !!document.querySelector('[data-wf-page]'),
    lottie: !!document.querySelector('lottie-player,dotlottie-player,[data-animation-path]'),
    rive: !!document.querySelector('canvas[data-rive],rive-canvas'),
    spline: !!document.querySelector('spline-viewer,iframe[src*="spline"]'),
    modelViewer: !!document.querySelector('model-viewer'),
  };

  // ---- CSS: running animations and stylesheet features ---------------------
  const anims = document.getAnimations().map((a) => {
    const t = a.effect && a.effect.getTiming ? a.effect.getTiming() : {};
    return { kind: a.constructor.name, name: a.animationName || a.transitionProperty || a.id || '', target: sel(a.effect && a.effect.target),
      duration: typeof t.duration === 'number' ? t.duration : null, delay: t.delay || 0, easing: t.easing, iterations: t.iterations === Infinity ? 'infinite' : t.iterations,
      timeline: a.timeline && a.timeline.constructor ? a.timeline.constructor.name : null };
  });
  let cssText = '';
  const crossOriginSheets = [];
  for (const sh of document.styleSheets) {
    try { cssText += [...sh.cssRules].map((r) => r.cssText).join('\n'); }
    catch (e) { crossOriginSheets.push(sh.href); }
  }
  const css = {
    bytes: cssText.length, crossOriginSheets,
    keyframes: [...new Set([...cssText.matchAll(/@keyframes\s+([\w-]+)/g)].map((m) => m[1]))],
    cubicBeziers: [...new Set(cssText.match(/cubic-bezier\([^)]*\)/g) || [])],
    linearEasing: count(cssText, /linear\([^)]*,/g),
    scrollDriven: count(cssText, /animation-timeline|view-timeline|scroll-timeline|\bview\(\)|\bscroll\(\)/g),
    viewTransitions: count(cssText, /view-transition/g), atProperty: count(cssText, /@property/g),
    transitions: count(cssText, /transition:/g), reducedMotion: count(cssText, /prefers-reduced-motion/g),
    willChange: count(cssText, /will-change/g), backdrop: count(cssText, /backdrop-filter/g), sticky: count(cssText, /position:\s*sticky/g),
  };

  // ---- media ----------------------------------------------------------------
  const vw = innerWidth, vh = innerHeight;
  const canvases = [...document.querySelectorAll('canvas')].map((c) => {
    const r = c.getBoundingClientRect();
    return { el: sel(c), parent: sel(c.parentElement), cssW: Math.round(r.width), cssH: Math.round(r.height), backingW: c.width, backingH: c.height,
      position: getComputedStyle(c).position, coversViewport: r.width >= vw * 0.8 && r.height >= vh * 0.6, hidden: c.hidden || getComputedStyle(c).display === 'none',
      dataset: Object.assign({}, c.dataset) };
  });
  const videos = [...document.querySelectorAll('video')].map((v) => ({ el: sel(v), src: (v.currentSrc || v.src || '').slice(0, 120), autoplay: v.autoplay, loop: v.loop, muted: v.muted,
    cssW: Math.round(v.getBoundingClientRect().width) }));
  const media = { canvases, videos, svgs: document.querySelectorAll('svg').length, iframes: [...document.querySelectorAll('iframe')].map((f) => (f.src || '').slice(0, 100)) };

  // ---- same-origin scripts: what the code does --------------------------------
  const bodies = [];
  for (const s of scripts) {
    if (!s.src) continue;
    try {
      const u = new URL(s.src, location.href);
      if (u.origin !== location.origin) continue;
      const t = await fetch(u.href).then((r) => r.text());
      bodies.push({ src: u.pathname, bytes: t.length, lines: t.split('\n').length, text: t });
    } catch (e) { /* unreadable: skip */ }
  }
  [...document.scripts].filter((s) => !s.src && s.textContent.length > 200 && !/^\s*[[{]/.test(s.textContent)).forEach((s, i) => bodies.push({ src: 'inline#' + i, bytes: s.textContent.length, lines: s.textContent.split('\n').length, text: s.textContent }));
  const all = bodies.map((b) => b.text).join('\n');
  const code = {
    files: bodies.map((b) => ({ src: b.src, bytes: b.bytes, lines: b.lines, minified: b.lines < 30 && b.bytes > 20000 })),
    raf: count(all, /requestAnimationFrame/g), intersectionObserver: count(all, /IntersectionObserver/g), resizeObserver: count(all, /ResizeObserver/g),
    scrollListeners: count(all, /addEventListener\(\s*['"]scroll['"]/g), scrollYMath: count(all, /scrollY|pageYOffset|scrollTop/g),
    wheelOrTouchHijack: count(all, /['"](wheel|touchmove)['"][^)]*passive\s*:\s*false|preventDefault\(\)[^;]*wheel/g),
    pointer: count(all, /pointermove|mousemove/g), ctx2d: count(all, /getContext\(\s*['"]2d['"]/g),
    webgl: count(all, /getContext\(\s*['"](webgl2?|experimental-webgl)['"]/g), shaders: count(all, /createShader|gl_FragColor|gl_Position|#version 300 es|precision (high|medium)p float/g),
    seededRandom: count(all, /1664525|16807|mulberry32|xorshift|sfc32|\bseed\b/gi), customEasing: count(all, /function\s+ease\w*|ease(In|Out|InOut)\w*\s*[=(]|Math\.pow\(\s*-?2\s*\*\s*t/g),
    lerp: count(all, /\b(lerp|mix|damp)\s*\(/g), springs: count(all, /stiffness|damping|spring/gi),
    waapi: count(all, /\.animate\(\s*\[/g), viewTransitionApi: count(all, /startViewTransition/g), devicePixelRatio: count(all, /devicePixelRatio/g),
    reducedMotion: count(all, /prefers-reduced-motion/g), layoutAnchors: count(all, /getBoundingClientRect|offsetTop|querySelector\([^)]*data-phase/g),
    dataAttrsForTests: count(all, /setAttribute\(\s*['"]data-/g),
  };

  // ---- behaviour: does it move by itself, with scroll, or both? ----------------
  const hashCanvas = (c) => { try { const d = c.toDataURL('image/png'); let h = 0; for (let i = 0; i < d.length; i += 97) h = (h * 31 + d.charCodeAt(i)) | 0; return d.length + ':' + h; } catch (e) { return 'unreadable'; } };
  const watched = [...document.querySelectorAll('canvas')].filter((c) => c.width && c.height);
  const domMovers = [...document.querySelectorAll('[style*="transform"],[style*="opacity"],[style*="translate"]')].slice(0, 200);
  const domState = () => domMovers.map((e) => e.getAttribute('style')).join('|').length + ':' + domMovers.map((e) => e.getAttribute('style')).join('|').slice(0, 2000);
  const startY = scrollY;
  const t0 = { canvas: watched.map(hashCanvas), dom: domState(), anims: document.getAnimations().length };
  await sleep(1200);
  const t1 = { canvas: watched.map(hashCanvas), dom: domState(), anims: document.getAnimations().length };
  const step = Math.min(600, Math.max(0, document.documentElement.scrollHeight - innerHeight - startY));
  scrollTo(0, startY + step); await frames(3); await sleep(120);
  const t2 = { canvas: watched.map(hashCanvas), dom: domState(), anims: document.getAnimations().length };
  scrollTo(0, startY); await frames(3);
  const behaviour = {
    scrolledBy: step,
    canvasesChangeOverTime: t0.canvas.filter((h, i) => h !== 'unreadable' && h !== t1.canvas[i]).length,
    canvasesChangeWithScroll: t1.canvas.filter((h, i) => h !== 'unreadable' && h !== t2.canvas[i]).length,
    canvasesUnreadable: t0.canvas.filter((h) => h === 'unreadable').length,
    canvasesWatched: watched.length,
    inlineStylesChangeOverTime: t0.dom !== t1.dom, inlineStylesChangeWithScroll: t1.dom !== t2.dom,
    animationsStartedOnScroll: Math.max(0, t2.anims - t1.anims),
  };

  const out = {
    probe: 'motion_probe/1', url: location.href, at: new Date().toISOString(), viewport: [vw, vh], dpr: devicePixelRatio,
    pageHeight: document.documentElement.scrollHeight, hidden: document.hidden,
    htmlClass: document.documentElement.className, prefersReducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
    libraries: { globals, fromScriptUrls: fromSrc, domHints }, scripts: scripts.slice(0, 40), css, cssAnimations: anims.slice(0, 60),
    media, code, behaviour,
  };
  const json = JSON.stringify(out, null, 1);
  console.log(json);
  window.__motionProbe = out;
  return out;
})();
