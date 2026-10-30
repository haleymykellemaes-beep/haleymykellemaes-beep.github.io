(function () {
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduce) document.documentElement.classList.add("js");

  /* Soft hero heading fade-in (title, then person) — skipped when reduce */
  (function initHeroTitleFade() {
    if (reduce) return;
    var title = document.querySelector(".cinematic-copy .hero-title");
    var person = document.querySelector(".cinematic-copy .hero-person");
    if (!title) return;
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        title.classList.add("is-in");
        if (person) {
          window.setTimeout(function () {
            person.classList.add("is-in");
          }, 180);
        }
      });
    });
  })();

  /* Cinematic scroll hero: silk champagne strands + scroll-driven reveal */
  (function initCinematicHero() {
    var stage = document.getElementById("hero-stage");
    if (!stage) return;
    var sticky = stage.querySelector(".hero-sticky");
    var network = document.getElementById("wave-layer");
    if (!sticky || !network) return;
    var NS = "http://www.w3.org/2000/svg";
    var STRANDS = ["strand-a", "strand-b", "strand-c"];
    var NODE_CLS = ["", "node-b", "node-c"];
    /* Five depth bands so threads scroll at different speeds (near → far) */
    var DEPTHS = 5;
    var DEPTH_DOWN = [0.48, 0.72, 1.0, 1.28, 1.55];
    var DEPTH_RIGHT = [0.62, 0.82, 1.0, 1.22, 1.48];
    var mobile = window.innerWidth <= 850;
    var pathCount = mobile ? 360 : 680;
    var nodeCount = mobile ? 230 : 520;

    function rnd(seed) {
      var x = Math.sin(seed * 127.1 + 311.7) * 43758.5453123;
      return x - Math.floor(x);
    }

    var depthGroups = [];
    var d;
    for (d = 0; d < DEPTHS; d++) {
      var g = document.createElementNS(NS, "g");
      g.setAttribute("class", "strand-depth depth-" + d);
      network.appendChild(g);
      depthGroups.push(g);
    }

    var ribbonPaths = [];
    var ribbonNodes = [];
    function ribbonD(values) {
      var v = values.map(function (value) { return value.toFixed(1); });
      return "M " + v[0] + " " + v[1] +
        " C " + v[2] + " " + v[3] + " " + v[4] + " " + v[5] + " " + v[6] + " " + v[7] +
        " S " + v[8] + " " + v[9] + " " + v[10] + " " + v[11] +
        " S " + v[12] + " " + v[13] + " " + v[14] + " " + v[15];
    }
    function blendRibbon(wide, tight, amount) {
      return wide.map(function (value, index) { return value + (tight[index] - value) * amount; });
    }

    var i;
    for (i = 0; i < pathCount; i++) {
      var r0 = rnd(i + 1);
      var r1 = rnd(i + 47);
      var r2 = rnd(i + 91);
      var r3 = rnd(i + 139);
      var r4 = rnd(i + 181);
      var t = i / Math.max(1, pathCount - 1);
      /* Keep luminous lead threads, with airy layers that fan out toward the end. */
      var atmosphere = i % 2 !== 0;
      var lane = t * 2 - 1;
      var spread = atmosphere ? lane * 470 : (r0 - 0.5) * (220 + r4 * 160);
      var endSpread = atmosphere ? lane * 780 : spread * 1.35;
      var wobble = (r3 - 0.5) * (atmosphere ? 110 : 80);
      var wide = [
        70 - r1 * 140, 440 + spread,
        270, 440 + spread * 0.95, 430, 345 + spread + wobble * 0.45,
        650, 375 + spread * (atmosphere ? 0.9 : 0.8),
        920, 475 + spread, 1110, 425 + endSpread * 0.9,
        1320, 345 + endSpread + wobble * 0.45, 1510, 425 + endSpread
      ];
      var tightSpread = (r0 - 0.5) * (100 + r4 * 100);
      var tightWobble = (r3 - 0.5) * 62;
      var tight = [
        70 - r1 * 140, 455 + tightSpread,
        270, 455 + tightSpread, 430, 355 + tightSpread + tightWobble * 0.45,
        570, 390 + tightSpread * 0.8,
        850, 490 + tightSpread, 1040, 440 + tightSpread * 0.9,
        1250, 360 + tightSpread + tightWobble * 0.45, 1510, 435 + tightSpread
      ];
      var pathD = ribbonD(wide);
      var path = document.createElementNS(NS, "path");
      path.setAttribute("d", pathD);
      var highlight = !atmosphere && i % 6 === 0;
      var medium = !atmosphere && !highlight;
      path.setAttribute("class", STRANDS[i % 3] + (highlight ? " strand-highlight" : medium ? " strand-mid" : " strand-atmosphere"));
      var sw = highlight ? 0.55 + r1 * 0.15 : medium ? 0.4 + r1 * 0.15 : 0.3 + r1 * 0.15;
      path.setAttribute("stroke-width", sw.toFixed(2));
      path.setAttribute("vector-effect", "non-scaling-stroke");
      var opacity = highlight ? 0.64 + r3 * 0.16 : medium ? 0.38 + r0 * 0.22 : 0.13 + r0 * 0.16;
      path.style.opacity = opacity.toFixed(3);
      ribbonPaths.push({ element: path, wide: wide, tight: tight, opacity: opacity, revealVisible: i < (mobile ? 140 : 240) });
      var dash = highlight ? 360 + r0 * 480 : medium ? 240 + r0 * 420 : 150 + r0 * 300;
      var gap = highlight ? 12 + r1 * 28 : medium ? 18 + r1 * 42 : 40 + r1 * 110;
      path.setAttribute("stroke-dasharray", dash.toFixed(1) + " " + gap.toFixed(1));
      path.setAttribute("stroke-dashoffset", String(Math.round(r2 * 280 + r4 * 90)));
      var depth = Math.min(DEPTHS - 1, Math.floor(r0 * DEPTHS));
      ribbonPaths[ribbonPaths.length - 1].depth = depth;
      depthGroups[depth].appendChild(path);
    }

    for (i = 0; i < nodeCount; i++) {
      var rn = rnd(i + 220);
      var rn2 = rnd(i + 340);
      var rn3 = rnd(i + 460);
      var cx = 60 + rn * 1320;
      var flowY = 540 - 190 * Math.sin((cx - 250) / 175);
      var cy = flowY + (rn2 - 0.5) * (145 + cx / 1440 * 300);
      var circle = document.createElementNS(NS, "circle");
      circle.setAttribute("cx", cx.toFixed(1));
      circle.setAttribute("cy", cy.toFixed(1));
      ribbonNodes.push({ element: circle, wide: cy, tight: flowY + (rn2 - 0.5) * 145 });
      var rad = 0.45 + rn3 * 0.65;
      var spark = i % 12 === 0;
      if (spark) rad = 0.95 + rn * 0.35;
      circle.setAttribute("r", rad.toFixed(2));
      var ncls = NODE_CLS[i % 3];
      if (spark) ncls = (ncls ? ncls + " " : "") + "spark";
      if (ncls) circle.setAttribute("class", ncls);
      circle.style.opacity = String(spark ? 0.72 + rn2 * 0.25 : 0.22 + rn * 0.32);
      var nodeDepth = Math.min(DEPTHS - 1, Math.floor(rn * DEPTHS));
      depthGroups[nodeDepth].appendChild(circle);
    }

    if (reduce) return;
    var clamp = function (n, a, b) {
      a = a === undefined ? 0 : a;
      b = b === undefined ? 1 : b;
      return Math.min(b, Math.max(a, n));
    };
    var smooth = function (t) {
      return t * t * (3 - 2 * t);
    };
    var scheduled = false;
    var revealEl = sticky.querySelector(".hero-reveal");
    var networkEl = sticky.querySelector(".hero-network");
    var metricsEl = sticky.querySelector(".hero-metrics");
    var introCopy = sticky.querySelector(".cinematic-copy");
    var mobileAction = sticky.querySelector(".pill-mobile-work");
    var needsMeasure = true;
    var sceneStart = 0;
    var sceneTravel = 1;
    var lastProgress = -1;

    var lastSceneBlend = -1;
    function update() {
      scheduled = false;
      var measured = needsMeasure;
      if (measured) {
        sceneStart = stage.getBoundingClientRect().top + window.scrollY;
        // Match the sticky scene's stable svh height, including mobile browser chrome.
        sceneTravel = Math.max(1, stage.offsetHeight - sticky.clientHeight);
        needsMeasure = false;
      }
      var p = clamp((window.scrollY - sceneStart) / sceneTravel);
      if (!measured && p === lastProgress) return;
      lastProgress = p;
      var reveal = smooth(clamp((p - 0.32) / 0.17));
      var exit = smooth(clamp((p - 0.69) / 0.29));
      // Only the opening scene fans out; the reveal returns to the original ribbon.
      if (Math.abs(reveal - lastSceneBlend) > 0.001 || reveal !== lastSceneBlend && (reveal === 0 || reveal === 1)) {
        ribbonPaths.forEach(function (strand) {
          strand.element.setAttribute("d", ribbonD(blendRibbon(strand.wide, strand.tight, reveal)));
          strand.element.style.opacity = (strand.opacity * (strand.revealVisible ? 1 : 1 - reveal)).toFixed(3);
        });
        ribbonNodes.forEach(function (node) {
          node.element.setAttribute("cy", (node.wide + (node.tight - node.wide) * reveal).toFixed(1));
        });
        lastSceneBlend = reveal;
      }
      sticky.style.setProperty("--scene-reveal", String(reveal));
      var baseDown = p * 55;
      var baseRight = exit * window.innerWidth * 1.65;
      sticky.style.setProperty("--hero-progress", String(p));
      /* Open with a shallow ribbon, then deepen its curve with the reveal. */
      sticky.style.setProperty("--wave-bend", String(0.82 + reveal * 0.18));
      /* Mid-depth values keep metrics aligned with the field */
      sticky.style.setProperty("--wave-down", Math.round(baseDown) + "px");
      sticky.style.setProperty("--wave-right", Math.round(baseRight) + "px");
      for (d = 0; d < DEPTHS; d++) {
        sticky.style.setProperty("--wave-down-" + d, Math.round(baseDown * DEPTH_DOWN[d]) + "px");
        sticky.style.setProperty("--wave-right-" + d, Math.round(baseRight * DEPTH_RIGHT[d]) + "px");
      }
      sticky.style.setProperty("--original-opacity", String(1 - smooth(clamp((p - 0.27) / 0.21))));
      sticky.style.setProperty("--original-rise", Math.round(-20 * smooth(clamp((p - 0.3) / 0.2))) + "px");
      sticky.style.setProperty("--reveal-opacity", String(reveal * (1 - exit * 0.52)));
      sticky.style.setProperty("--reveal-rise", Math.round((1 - reveal) * 28 - exit * 12) + "px");
      /* Metrics ride with the signal reveal, then exit with the wave sweep */
      sticky.style.setProperty("--metrics-opacity", String(reveal * (1 - exit)));
      sticky.style.setProperty("--metrics-rise", Math.round((1 - reveal) * 18 - exit * 8) + "px");
      if (revealEl) revealEl.style.pointerEvents = reveal > 0.9 ? "auto" : "none";
      if (revealEl) revealEl.inert = reveal < 0.9;
      if (introCopy) introCopy.inert = p > 0.48;
      if (mobileAction) mobileAction.inert = p > 0.48;
      if (networkEl) networkEl.style.opacity = String((0.82 + reveal * 0.18) * (1 - exit * 0.85));
      if (metricsEl) metricsEl.setAttribute("aria-hidden", reveal < 0.08 ? "true" : "false");
    }
    function request() {
      if (!scheduled) {
        scheduled = true;
        requestAnimationFrame(update);
      }
    }
    window.addEventListener("scroll", request, { passive: true });
    window.addEventListener("resize", function () {
      needsMeasure = true;
      request();
    });
    update();
  })();

  var played = typeof WeakSet === "function" ? new WeakSet() : null;

  function fmt(el, v) {
    if (el.getAttribute("data-commas")) return Math.round(v).toLocaleString("en-US");
    var d = el.getAttribute("data-decimals");
    var body = Number(v).toFixed(d ? +d : 0);
    if (el.hasAttribute("data-trim")) body = body.replace(/^0(?=\.)/, "");
    return (el.getAttribute("data-prefix") || "") + body + (el.getAttribute("data-suffix") || "");
  }

  function play(el) {
    if (!el || reduce || !window.gsap) return;
    if (played && played.has(el)) return;
    if (played) played.add(el);
    var end = parseFloat(el.getAttribute("data-count"));
    if (!isFinite(end)) return;
    var proxy = { v: 0 };
    el.textContent = fmt(el, 0);
    gsap.to(proxy, {
      v: end,
      duration: 1.15,
      ease: "power2.out",
      onUpdate: function () { el.textContent = fmt(el, proxy.v); }
    });
  }

  function playAll(root) {
    if (!root) return;
    var nodes = root.querySelectorAll("[data-count]");
    for (var i = 0; i < nodes.length; i++) play(nodes[i]);
  }

  /* Menu — mobile side drawer */
  var menuBtn = document.querySelector(".menu-btn");
  var navLinks = document.getElementById("nav-links");
  var label = menuBtn && menuBtn.querySelector(".menu-label");
  function setNav(open) {
    document.body.classList.toggle("nav-open", open);
    if (menuBtn) menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
    if (label) label.textContent = open ? "Close" : "Menu";
  }
  if (menuBtn) {
    menuBtn.addEventListener("click", function () {
      setNav(!document.body.classList.contains("nav-open"));
    });
  }
  if (navLinks) {
    navLinks.addEventListener("click", function (e) {
      if (e.target.closest("a")) setNav(false);
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setNav(false);
  });
  document.addEventListener("click", function (e) {
    if (!document.body.classList.contains("nav-open")) return;
    if (e.target.closest(".nav-links") || e.target.closest(".menu-btn")) return;
    setNav(false);
  });

  window.addEventListener("resize", function () {
    if (window.innerWidth > 1100 && document.body.classList.contains("nav-open")) setNav(false);
  });

  /* Cards draw in, including the horizontal row */
  var cards = document.querySelectorAll(".card");
  function armCard(card) {
    card.classList.add("is-in");
    playAll(card);
  }
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) armCard(entry.target);
      });
    }, { threshold: 0.35 });
    cards.forEach(function (card) { io.observe(card); });
  } else {
    cards.forEach(armCard);
  }
  cards.forEach(function (card) {
    card.addEventListener("touchstart", function () { card.classList.add("is-touch"); }, { passive: true });
    card.addEventListener("touchend", function () { card.classList.remove("is-touch"); });
    card.addEventListener("touchcancel", function () { card.classList.remove("is-touch"); });
  });

  /* Mobile snap dots. Scroll the row, not the page. */
  var row = document.getElementById("project-row");
  var dotsWrap = document.getElementById("snap-dots");
  if (row && dotsWrap) {
    var items = row.querySelectorAll(":scope > li");
    items.forEach(function (item, i) {
      var title = item.querySelector("h3");
      var dot = document.createElement("button");
      dot.type = "button";
      dot.setAttribute("aria-label", title ? title.textContent : "Project " + (i + 1));
      if (i === 0) dot.setAttribute("aria-current", "true");
      dot.addEventListener("click", function () {
        var left = item.getBoundingClientRect().left - row.getBoundingClientRect().left + row.scrollLeft;
        row.scrollTo({ left: left, behavior: reduce ? "auto" : "smooth" });
      });
      dotsWrap.appendChild(dot);
    });
    var dots = dotsWrap.querySelectorAll("button");
    row.addEventListener("scroll", function () {
      var best = 0;
      var bestDist = Infinity;
      var rowLeft = row.getBoundingClientRect().left;
      items.forEach(function (item, i) {
        var dist = Math.abs(item.getBoundingClientRect().left - rowLeft);
        if (dist < bestDist) { best = i; bestDist = dist; }
      });
      dots.forEach(function (dot, i) {
        if (i === best) dot.setAttribute("aria-current", "true");
        else dot.removeAttribute("aria-current");
      });
    }, { passive: true });
  }

  /* Scroll reveals */
  var rises = document.querySelectorAll(".rise");
  function showVisible() {
    rises.forEach(function (el) {
      if (el.getBoundingClientRect().top < window.innerHeight * 0.95) el.classList.add("is-in");
    });
  }
  if (reduce || !window.ScrollTrigger) {
    rises.forEach(function (el) { el.classList.add("is-in"); });
  } else {
    gsap.registerPlugin(ScrollTrigger);
    showVisible();
    ScrollTrigger.batch(".rise", {
      start: "top 90%",
      once: true,
      onEnter: function (els) { els.forEach(function (el) { el.classList.add("is-in"); }); }
    });
  }

  /* Impact: two states, then two single figures */
  var tablist = document.querySelector(".tabs");
  var tabs = tablist ? [].slice.call(tablist.querySelectorAll("[role='tab']")) : [];
  var panels = [].slice.call(document.querySelectorAll(".panel"));
  var arHost = document.getElementById("ar-chart");
  var arFallback = document.getElementById("ar-fallback");
  var arTip = document.getElementById("ar-tip");
  var arAnimated = false;
  var lastW = 0;

  function drawAr(animate) {
    if (!window.d3 || !arHost) return;
    var panel = document.getElementById("panel-ar");
    if (panel && panel.hidden) return;
    if (arFallback) arFallback.hidden = true;
    arHost.hidden = false;
    var width = arHost.clientWidth;
    if (!width) return;
    lastW = width;
    var height = 250;
    var margin = { top: 28, right: 8, bottom: 36, left: 48 };
    var data = [
      { key: "Earlier", value: 31.4, tip: "31.4% of open A/R in 90+" },
      { key: "Later", value: 18.7, tip: "18.7% of open A/R in 90+" }
    ];
    arHost.innerHTML = "";
    var svg = d3.select(arHost).append("svg")
      .attr("viewBox", "0 0 " + width + " " + height)
      .attr("role", "img")
      .attr("aria-label", "Two bars. Earlier extract 31.4 percent. Later extract 18.7 percent. Not a time series.");
    var x = d3.scaleBand().domain(data.map(function (d) { return d.key; })).range([margin.left, width - margin.right]).padding(0.45);
    var y = d3.scaleLinear().domain([0, 40]).range([height - margin.bottom, margin.top]);
    var band = Math.min(x.bandwidth(), 64);
    function xPos(d) { return x(d.key) + (x.bandwidth() - band) / 2; }

    svg.append("g")
      .attr("transform", "translate(" + margin.left + ",0)")
      .call(d3.axisLeft(y).tickValues([0, 20, 40]).tickFormat(function (d) { return d + "%"; }).tickSize(0))
      .call(function (g) { g.select(".domain").remove(); })
      .selectAll("text").attr("font-size", 12).attr("fill", "#F4F1EA");

    var grow = animate && !reduce;
    var bars = svg.selectAll("rect").data(data).join("rect")
      .attr("x", xPos)
      .attr("width", band)
      .attr("y", grow ? y(0) : function (d) { return y(d.value); })
      .attr("height", grow ? 0 : function (d) { return y(0) - y(d.value); })
      .attr("fill", "#F4F1EA")
      .attr("tabindex", "0")
      .style("cursor", "default");

    svg.append("g")
      .attr("transform", "translate(0," + (height - margin.bottom) + ")")
      .call(d3.axisBottom(x).tickSize(0))
      .call(function (g) { g.select(".domain").attr("stroke", "#F4F1EA").attr("stroke-opacity", 0.35); })
      .selectAll("text").attr("font-size", 13).attr("fill", "#F4F1EA").attr("dy", "1.2em");

    function show(event, d) {
      if (!arTip) return;
      var pt = d3.pointer(event, arHost);
      arTip.textContent = d.tip;
      arTip.hidden = false;
      var tw = arTip.offsetWidth || 180;
      var left = Math.max(0, Math.min(pt[0] - tw / 2, width - tw));
      arTip.style.left = left + "px";
      arTip.style.top = Math.max(0, pt[1] - 36) + "px";
    }
    function hide() { if (arTip) arTip.hidden = true; }
    bars.on("mouseenter", show).on("mousemove", show).on("mouseleave", hide).on("focus", show).on("blur", hide);

    if (grow) {
      bars.transition().duration(900).ease(d3.easeCubicOut)
        .attr("y", function (d) { return y(d.value); })
        .attr("height", function (d) { return y(0) - y(d.value); });
      arAnimated = true;
    }
  }

  function select(id) {
    tabs.forEach(function (tab) {
      var on = tab.getAttribute("data-panel") === id;
      tab.setAttribute("aria-selected", on ? "true" : "false");
      tab.tabIndex = on ? 0 : -1;
    });
    panels.forEach(function (panel) {
      var on = panel.getAttribute("data-panel") === id;
      panel.hidden = !on;
      if (on && id === "r") requestAnimationFrame(function () { panel.classList.add("is-on"); });
    });
    var panel = document.getElementById("panel-" + id);
    if (id === "ar") drawAr(!arAnimated);
    playAll(panel);
  }

  if (tablist) {
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () { select(tab.getAttribute("data-panel")); });
    });
    tablist.addEventListener("keydown", function (e) {
      var i = tabs.indexOf(document.activeElement);
      if (i < 0) return;
      var n = null;
      if (e.key === "ArrowRight") n = (i + 1) % tabs.length;
      if (e.key === "ArrowLeft") n = (i - 1 + tabs.length) % tabs.length;
      if (e.key === "Home") n = 0;
      if (e.key === "End") n = tabs.length - 1;
      if (n === null) return;
      e.preventDefault();
      tabs[n].focus();
      select(tabs[n].getAttribute("data-panel"));
    });
  }

  var impact = document.getElementById("impact");
  function armImpact() {
    var arPanel = document.getElementById("panel-ar");
    if (arPanel && !arPanel.hidden) {
      drawAr(!arAnimated);
      playAll(arPanel);
    }
  }
  if (impact && "IntersectionObserver" in window) {
    var impactIO = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) {
        armImpact();
        impactIO.disconnect();
      }
    }, { threshold: 0.12 });
    impactIO.observe(impact);
  } else {
    armImpact();
  }

  if (arHost && "ResizeObserver" in window) {
    new ResizeObserver(function () {
      var panel = document.getElementById("panel-ar");
      if (!panel || panel.hidden || !arHost.clientWidth) return;
      if (Math.abs(arHost.clientWidth - lastW) < 8) return;
      drawAr(false);
    }).observe(arHost);
  }
})();

