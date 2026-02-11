/* ========================================
   TeleVIP Landing — Immersive Animations
   GSAP + ScrollTrigger + Lenis + Three.js
   ======================================== */
(function () {
  'use strict';

  // ── 1. CONFIG ──────────────────────────────────────────
  var isMobile = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent) || window.innerWidth < 768;
  var prefersReduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var isLanding = !!document.getElementById('home');
  var isPrecos = !!document.querySelector('.precos-hero');
  var isRecursos = !!document.querySelector('.recursos-hero');

  // Bail entirely when reduced motion is on
  if (prefersReduced) return;

  // ── 2. LENIS SMOOTH SCROLL ─────────────────────────────
  var lenis = null;
  function initLenis() {
    if (typeof Lenis === 'undefined') return;
    lenis = new Lenis({ duration: 1.2, easing: function (t) { return Math.min(1, 1.001 - Math.pow(2, -10 * t)); }, orientation: 'vertical', smoothWheel: true });

    // Sync Lenis with GSAP ticker
    gsap.ticker.add(function (time) {
      lenis.raf(time * 1000);
    });
    gsap.ticker.lagSmoothing(0);

    // Anchor links via Lenis
    document.querySelectorAll('a[href^="#"]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        var href = this.getAttribute('href');
        if (href === '#') return;
        var target = document.querySelector(href);
        if (target) {
          e.preventDefault();
          lenis.scrollTo(target, { offset: 0 });
        }
      });
    });
  }

  // ── 3. THREE.JS COSMIC PARTICLES (Hero, desktop only) ──
  function initCosmicParticles() {
    if (isMobile || typeof THREE === 'undefined') return;
    var canvas = document.getElementById('hero-canvas');
    if (!canvas) return;

    var heroSection = document.getElementById('home');
    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(75, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);
    camera.position.z = 5;

    var renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: false });
    renderer.setSize(canvas.clientWidth, canvas.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    // Particles
    var count = 3000;
    var positions = new Float32Array(count * 3);
    var colors = new Float32Array(count * 3);
    var sizes = new Float32Array(count);

    var colorWhite = new THREE.Color(0xffffff);
    var colorPurple = new THREE.Color(0x7c5cfc);
    var colorCyan = new THREE.Color(0x38bdf8);

    for (var i = 0; i < count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 30;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 30;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 20;
      sizes[i] = Math.random() * 3 + 1;

      var r = Math.random();
      var c = r < 0.7 ? colorWhite : r < 0.85 ? colorPurple : colorCyan;
      colors[i * 3] = c.r;
      colors[i * 3 + 1] = c.g;
      colors[i * 3 + 2] = c.b;
    }

    var geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

    var material = new THREE.PointsMaterial({
      size: 0.2,
      vertexColors: true,
      transparent: true,
      opacity: 0.95,
      sizeAttenuation: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false
    });

    var points = new THREE.Points(geometry, material);
    scene.add(points);

    // Mouse parallax
    var mouseX = 0, mouseY = 0;
    document.addEventListener('mousemove', function (e) {
      mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
      mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
    });

    // Track visibility for performance
    var heroVisible = true;
    ScrollTrigger.create({
      trigger: heroSection,
      start: 'top bottom',
      end: 'bottom top',
      onEnter: function () { heroVisible = true; },
      onLeave: function () { heroVisible = false; },
      onEnterBack: function () { heroVisible = true; },
      onLeaveBack: function () { heroVisible = false; }
    });

    // Render loop
    function animate() {
      requestAnimationFrame(animate);
      if (!heroVisible) return;

      points.rotation.y += 0.0006;
      points.rotation.x += 0.00025;

      // Breathing opacity — subtle pulse
      var breath = 0.85 + Math.sin(Date.now() * 0.001) * 0.1;
      material.opacity = breath;

      // Smooth camera follow — dramatic parallax
      camera.position.x += (mouseX * 2.0 - camera.position.x) * 0.035;
      camera.position.y += (-mouseY * 1.5 - camera.position.y) * 0.035;
      camera.lookAt(scene.position);

      renderer.render(scene, camera);
    }
    animate();

    // Resize
    window.addEventListener('resize', function () {
      if (!canvas.parentElement) return;
      var w = canvas.parentElement.clientWidth;
      var h = canvas.parentElement.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
  }

  // ── 4. TEXT SPLIT HELPER ───────────────────────────────
  function splitWords(element) {
    if (!element) return [];
    var html = element.innerHTML;
    // Wrap words while preserving existing <span> tags
    var words = [];
    var temp = document.createElement('div');
    temp.innerHTML = html;

    function processNode(node) {
      if (node.nodeType === 3) { // text node
        var textWords = node.textContent.split(/(\s+)/);
        var frag = document.createDocumentFragment();
        textWords.forEach(function (w) {
          if (w.trim() === '') {
            frag.appendChild(document.createTextNode(w));
          } else {
            var span = document.createElement('span');
            span.className = 'word';
            span.textContent = w;
            span.style.display = 'inline-block';
            frag.appendChild(span);
            words.push(span);
          }
        });
        node.parentNode.replaceChild(frag, node);
      } else if (node.nodeType === 1) { // element node
        // If it's a text-gradient span, wrap it as a word group
        if (node.classList && node.classList.contains('text-gradient')) {
          var innerWords = node.textContent.split(/(\s+)/);
          node.innerHTML = '';
          innerWords.forEach(function (w) {
            if (w.trim() === '') {
              node.appendChild(document.createTextNode(w));
            } else {
              var span = document.createElement('span');
              span.className = 'word';
              span.textContent = w;
              span.style.display = 'inline-block';
              // Inherit gradient styles
              span.style.background = 'inherit';
              span.style.webkitBackgroundClip = 'text';
              span.style.webkitTextFillColor = 'transparent';
              span.style.backgroundClip = 'text';
              node.appendChild(span);
              words.push(span);
            }
          });
        } else {
          // Process children in reverse order to maintain indices
          var children = Array.from(node.childNodes);
          children.forEach(processNode);
        }
      }
    }

    var children = Array.from(temp.childNodes);
    children.forEach(processNode);
    element.innerHTML = temp.innerHTML;
    return element.querySelectorAll('.word');
  }

  // ── 5. HERO ENTRANCE TIMELINE (landing.html only) ─────
  function initHeroEntrance() {
    if (!isLanding) return;
    var heroContent = document.querySelector('.hero-content');
    if (!heroContent) return;

    var h1 = heroContent.querySelector('h1');
    var lead = heroContent.querySelector('.lead');
    var alert = heroContent.querySelector('.alert');
    var stats = heroContent.querySelectorAll('.stat-card');
    var buttons = heroContent.querySelector('.hero-buttons');
    var subtext = heroContent.querySelector('.mt-4.text-muted');

    // Split H1 words
    var words = h1 ? splitWords(h1) : [];

    var tl = gsap.timeline({ defaults: { ease: 'power3.out' }, delay: 0.2 });

    // Words reveal — dramatic staggered from below with slight scale
    if (words.length) {
      gsap.set(words, { y: 80, opacity: 0, scale: 0.9, rotateX: 15 });
      tl.to(words, { y: 0, opacity: 1, scale: 1, rotateX: 0, duration: 0.9, stagger: 0.05, ease: 'back.out(1.2)' }, 0);
    }

    // Lead text — fade up with slight blur effect
    if (lead) {
      gsap.set(lead, { y: 40, opacity: 0 });
      tl.to(lead, { y: 0, opacity: 1, duration: 0.7 }, 0.5);
    }

    // Alert — scale bounce
    if (alert) {
      gsap.set(alert, { y: 20, opacity: 0, scale: 0.9 });
      tl.to(alert, { y: 0, opacity: 1, scale: 1, duration: 0.5, ease: 'back.out(1.5)' }, 0.7);
    }

    // Stats with dramatic bounce cascade
    if (stats.length) {
      gsap.set(stats, { scale: 0.3, opacity: 0, y: 30 });
      tl.to(stats, {
        scale: 1, opacity: 1, y: 0, duration: 0.7,
        stagger: 0.12, ease: 'back.out(2)'
      }, 0.8);
    }

    // Buttons — slide up with elastic
    if (buttons) {
      gsap.set(buttons, { y: 30, opacity: 0 });
      tl.to(buttons, { y: 0, opacity: 1, duration: 0.6, ease: 'back.out(1.3)' }, 1.1);
    }

    // Subtext
    if (subtext) {
      gsap.set(subtext, { opacity: 0 });
      tl.to(subtext, { opacity: 1, duration: 0.6 }, 1.3);
    }

    // Floating cards — stagger from different sides
    var floats = document.querySelectorAll('.floating-card');
    if (floats.length) {
      floats.forEach(function (card, i) {
        var fromX = i % 2 === 0 ? -60 : 60;
        gsap.set(card, { opacity: 0, x: fromX, y: 30, scale: 0.8 });
      });
      tl.to(floats, { opacity: 1, x: 0, y: 0, scale: 1, duration: 1, stagger: 0.25, ease: 'elastic.out(1, 0.6)' }, 1.2);
    }
  }

  // ── 6. SCROLL TRIGGER ANIMATIONS ──────────────────────
  function initScrollAnimations() {
    // Default reveal for section headers
    gsap.utils.toArray('.text-center.mb-5, [data-aos="fade-up"]:not(.hero-content)').forEach(function (el) {
      // Skip if already handled
      if (el.closest('.hero-content') || el.closest('.hero')) return;
      gsap.from(el, {
        scrollTrigger: { trigger: el, start: 'top 85%', once: true },
        y: 50, opacity: 0, duration: 0.8, ease: 'power3.out'
      });
    });

    // Feature cards — dramatic reveal with perspective flip
    gsap.utils.toArray('.feature-card, .feature-card-ext').forEach(function (card, i) {
      gsap.from(card, {
        scrollTrigger: { trigger: card, start: 'top 88%', once: true },
        y: 80, opacity: 0, rotateX: 12, scale: 0.9, duration: 0.8,
        delay: (i % 3) * 0.18,
        ease: 'back.out(1.2)',
        transformPerspective: 800
      });
    });

    // Pricing card
    gsap.utils.toArray('.pricing-card, .main-pricing-card').forEach(function (card) {
      gsap.from(card, {
        scrollTrigger: { trigger: card, start: 'top 85%', once: true },
        scale: 0.8, opacity: 0, duration: 0.8, ease: 'back.out(1.4)'
      });
    });

    // Testimonial cards — dramatic alternate slide-in with rotation
    gsap.utils.toArray('.testimonial-card').forEach(function (card, i) {
      var dir = i % 2 === 0 ? -80 : 80;
      var rot = i % 2 === 0 ? -5 : 5;
      gsap.from(card, {
        scrollTrigger: { trigger: card, start: 'top 88%', once: true },
        x: dir, opacity: 0, rotateY: rot, scale: 0.9, duration: 0.9,
        ease: 'back.out(1.1)',
        transformPerspective: 800
      });
    });

    // CTA section — dramatic clip-path reveal for h2
    var ctaH2 = document.querySelector('.cta h2');
    if (ctaH2) {
      gsap.from(ctaH2, {
        scrollTrigger: { trigger: ctaH2, start: 'top 88%', once: true },
        clipPath: 'inset(0 100% 0 0)', opacity: 0, duration: 1.2,
        scale: 0.95, y: 20,
        ease: 'power4.out'
      });
    }

    // CTA content (lead, btn, etc)
    gsap.utils.toArray('.cta .lead, .cta .btn-cta, .cta .alert').forEach(function (el, i) {
      gsap.from(el, {
        scrollTrigger: { trigger: el, start: 'top 90%', once: true },
        y: 30, opacity: 0, duration: 0.6, delay: i * 0.15,
        ease: 'power3.out'
      });
    });

    // Comparison cards
    gsap.utils.toArray('.comparison-card').forEach(function (card, i) {
      gsap.from(card, {
        scrollTrigger: { trigger: card, start: 'top 85%', once: true },
        y: 40, opacity: 0, duration: 0.6, delay: i * 0.1,
        ease: 'power3.out'
      });
    });

    // Parallax nebula glows
    gsap.utils.toArray('.nebula-glow').forEach(function (glow, i) {
      var speed = (i + 1) * 50;
      gsap.to(glow, {
        scrollTrigger: { trigger: 'body', start: 'top top', end: 'bottom bottom', scrub: 1 },
        y: speed, ease: 'none'
      });
    });

    // Step cards (recursos)
    gsap.utils.toArray('.step-card').forEach(function (card, i) {
      gsap.from(card, {
        scrollTrigger: { trigger: card, start: 'top 85%', once: true },
        y: 50, opacity: 0, duration: 0.6, delay: i * 0.15,
        ease: 'power3.out'
      });
    });

    // Detail blocks (recursos)
    gsap.utils.toArray('.detail-block').forEach(function (block) {
      gsap.from(block, {
        scrollTrigger: { trigger: block, start: 'top 80%', once: true },
        y: 60, opacity: 0, duration: 0.8,
        ease: 'power3.out'
      });
    });

    // Included items (precos)
    gsap.utils.toArray('.included-item').forEach(function (item, i) {
      gsap.from(item, {
        scrollTrigger: { trigger: item, start: 'top 90%', once: true },
        x: i % 2 === 0 ? -30 : 30, opacity: 0, duration: 0.5,
        delay: (i % 6) * 0.08,
        ease: 'power3.out'
      });
    });

    // Accordion items (FAQ)
    gsap.utils.toArray('.accordion-item').forEach(function (item, i) {
      gsap.from(item, {
        scrollTrigger: { trigger: item, start: 'top 90%', once: true },
        y: 30, opacity: 0, duration: 0.5, delay: i * 0.08,
        ease: 'power3.out'
      });
    });

    // Comparison table (precos)
    var compTable = document.querySelector('.comparison-table');
    if (compTable) {
      gsap.from(compTable, {
        scrollTrigger: { trigger: compTable, start: 'top 80%', once: true },
        y: 50, opacity: 0, duration: 0.8,
        ease: 'power3.out'
      });
    }

    // Calculator card (precos)
    var calcCard = document.querySelector('.calculator-card');
    if (calcCard) {
      gsap.from(calcCard, {
        scrollTrigger: { trigger: calcCard, start: 'top 85%', once: true },
        scale: 0.9, opacity: 0, duration: 0.7,
        ease: 'back.out(1.2)'
      });
    }

    // Sub-page hero entrance (precos, recursos)
    var subHero = document.querySelector('.precos-hero, .recursos-hero');
    if (subHero) {
      var h1 = subHero.querySelector('h1');
      var lead = subHero.querySelector('.lead');
      if (h1) {
        var words = splitWords(h1);
        if (words.length) {
          gsap.set(words, { y: 50, opacity: 0 });
          gsap.to(words, { y: 0, opacity: 1, duration: 0.7, stagger: 0.05, ease: 'power3.out' });
        }
      }
      if (lead) {
        gsap.set(lead, { y: 20, opacity: 0 });
        gsap.to(lead, { y: 0, opacity: 1, duration: 0.6, delay: 0.4, ease: 'power3.out' });
      }
    }

    // Footer reveal
    var footer = document.querySelector('.footer');
    if (footer) {
      gsap.from(footer.querySelectorAll('.col-lg-4, .col-lg-2, .col-md-4'), {
        scrollTrigger: { trigger: footer, start: 'top 90%', once: true },
        y: 30, opacity: 0, duration: 0.6, stagger: 0.1,
        ease: 'power3.out'
      });
    }
  }

  // ── 7. MAGNETIC BUTTONS (desktop only) ─────────────────
  function initMagneticButtons() {
    if (isMobile) return;
    var selectors = '.btn-hero-primary, .btn-hero-secondary, .btn-cta, .btn-pricing, .btn-nav-cta';
    document.querySelectorAll(selectors).forEach(function (btn) {
      btn.addEventListener('mousemove', function (e) {
        var rect = btn.getBoundingClientRect();
        var x = e.clientX - rect.left - rect.width / 2;
        var y = e.clientY - rect.top - rect.height / 2;
        gsap.to(btn, { x: x * 0.3, y: y * 0.3, duration: 0.3, ease: 'power2.out' });
      });
      btn.addEventListener('mouseleave', function () {
        gsap.to(btn, { x: 0, y: 0, duration: 0.5, ease: 'elastic.out(1, 0.5)' });
      });
    });
  }

  // ── 8. 3D TILT CARDS (desktop only) ────────────────────
  function initTiltCards() {
    if (isMobile) return;
    var selectors = '.feature-card, .feature-card-ext, .testimonial-card, .stat-card, .comparison-card, .pricing-card, .main-pricing-card';
    document.querySelectorAll(selectors).forEach(function (card) {
      card.style.transformStyle = 'preserve-3d';
      card.addEventListener('mousemove', function (e) {
        var rect = card.getBoundingClientRect();
        var x = (e.clientX - rect.left) / rect.width - 0.5;
        var y = (e.clientY - rect.top) / rect.height - 0.5;
        gsap.to(card, {
          rotateY: x * 10, rotateX: -y * 10,
          duration: 0.3, ease: 'power2.out',
          transformPerspective: 1000
        });
      });
      card.addEventListener('mouseleave', function () {
        gsap.to(card, {
          rotateY: 0, rotateX: 0,
          duration: 0.5, ease: 'power3.out'
        });
      });
    });
  }

  // ── 9. ENHANCED CURSOR (desktop only) ──────────────────
  function initCursor() {
    if (isMobile) return;
    var inner = document.querySelector('.cursor');
    var outer = document.querySelector('.cursor2');
    if (!inner || !outer) return;

    var mx = 0, my = 0;
    document.addEventListener('mousemove', function (e) {
      mx = e.clientX;
      my = e.clientY;
    });

    // Smooth follow via GSAP ticker
    gsap.ticker.add(function () {
      gsap.set(inner, { left: mx, top: my });
      // Outer ring with physical delay
      var outerRect = outer.getBoundingClientRect();
      var ox = outerRect.left + outerRect.width / 2;
      var oy = outerRect.top + outerRect.height / 2;
      gsap.set(outer, {
        left: ox + (mx - ox) * 0.15,
        top: oy + (my - oy) * 0.15
      });
    });

    // Hover states
    var interactiveSelectors = 'a, button, .feature-card, .feature-card-ext, .pricing-card, .main-pricing-card, .testimonial-card, .included-item, .step-card';
    document.querySelectorAll(interactiveSelectors).forEach(function (el) {
      el.addEventListener('mouseenter', function () {
        gsap.to(inner, { width: 20, height: 20, background: 'rgba(124, 92, 252, 0.5)', duration: 0.2 });
        gsap.to(outer, { width: 60, height: 60, borderColor: 'rgba(56, 189, 248, 0.4)', duration: 0.2 });
      });
      el.addEventListener('mouseleave', function () {
        gsap.to(inner, { width: 12, height: 12, background: '#7c5cfc', duration: 0.2 });
        gsap.to(outer, { width: 40, height: 40, borderColor: 'rgba(124, 92, 252, 0.4)', duration: 0.2 });
      });
    });
  }

  // ── 10. COUNTER ANIMATION (landing.html) ───────────────
  function initCounters() {
    if (!isLanding) return;
    var counters = document.querySelectorAll('.stat-number');
    counters.forEach(function (counter) {
      var text = counter.innerText;
      // Extract numeric part and formatting
      var raw = text.replace(/\D/g, '');
      var target = parseInt(raw, 10);
      if (isNaN(target) || target === 0) return;

      // Determine prefix/suffix
      var prefix = text.match(/^[^\d]*/)[0];
      var suffix = text.match(/[^\d]*$/)[0];

      ScrollTrigger.create({
        trigger: counter,
        start: 'top 85%',
        once: true,
        onEnter: function () {
          var obj = { val: 0 };
          gsap.to(obj, {
            val: target, duration: 1.5, ease: 'power2.out',
            onUpdate: function () {
              var num = Math.round(obj.val);
              // Format with dots for thousands
              var formatted = num.toLocaleString('pt-BR');
              counter.innerText = prefix + formatted + suffix;
            }
          });
        }
      });
    });
  }

  // ── 11. NAVBAR SCROLL EFFECT ───────────────────────────
  function initNavbar() {
    var navbar = document.querySelector('.navbar-custom');
    if (!navbar) return;
    ScrollTrigger.create({
      start: 'top -80',
      end: 99999,
      onUpdate: function (self) {
        if (self.direction === 1 && self.scroll() > 80) {
          navbar.classList.add('scrolled');
        }
        if (self.scroll() <= 80) {
          navbar.classList.remove('scrolled');
        }
      }
    });
  }

  // ── 12. STARFIELD (all pages) ──────────────────────────
  function initStarfield() {
    var starfield = document.getElementById('starfield');
    if (!starfield) return;
    var count = 200;
    for (var i = 0; i < count; i++) {
      var star = document.createElement('div');
      star.classList.add('star');
      star.style.left = Math.random() * 100 + '%';
      star.style.top = Math.random() * 100 + '%';
      star.style.setProperty('--duration', (1.5 + Math.random() * 4) + 's');
      star.style.setProperty('--max-opacity', (0.5 + Math.random() * 0.5).toFixed(2));
      star.style.animationDelay = (Math.random() * 5) + 's';
      var size = (1 + Math.random() * 3) + 'px';
      star.style.width = size;
      star.style.height = size;
      // Add colored stars (20%)
      if (Math.random() < 0.1) {
        star.style.background = '#7c5cfc';
        star.style.boxShadow = '0 0 6px rgba(124, 92, 252, 0.8)';
      } else if (Math.random() < 0.15) {
        star.style.background = '#38bdf8';
        star.style.boxShadow = '0 0 6px rgba(56, 189, 248, 0.8)';
      }
      starfield.appendChild(star);
    }
  }

  // ── 13. PAGE TRANSITIONS ──────────────────────────────
  function initPageTransitions() {
    // Intercept internal navigation links for smooth page exit
    document.addEventListener('click', function (e) {
      var link = e.target.closest('a[href]');
      if (!link) return;
      var href = link.getAttribute('href');
      // Skip anchors, external, new-tab, javascript
      if (!href || href.startsWith('#') || href.startsWith('javascript') || href.startsWith('mailto') || href.startsWith('http') || link.target === '_blank') return;
      // Skip if modifier key pressed
      if (e.metaKey || e.ctrlKey || e.shiftKey) return;

      e.preventDefault();
      document.body.style.animation = 'pageExit 0.35s ease-in forwards';
      setTimeout(function () { window.location.href = href; }, 300);
    });
  }

  // ── 14. INIT ORCHESTRATOR ──────────────────────────────
  function init() {
    // Register GSAP plugin
    if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
      gsap.registerPlugin(ScrollTrigger);
    } else {
      return; // Can't proceed without GSAP
    }

    initLenis();
    initStarfield();
    initCosmicParticles();
    initHeroEntrance();
    initScrollAnimations();
    initMagneticButtons();
    initTiltCards();
    initCursor();
    initCounters();
    initNavbar();
    initPageTransitions();
  }

  // Run on DOMContentLoaded if not ready, else immediately
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
