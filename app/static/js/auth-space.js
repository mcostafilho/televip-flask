/* ================================================================
   TeleVIP Auth - Warp Speed Starfield + Space Facts
   Shared between login.html and register.html
   ================================================================ */

(function() {
    'use strict';
    var container = document.querySelector('.auth-container');
    if (!container || typeof gsap === 'undefined') return;

    var isMobile = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent) || window.innerWidth < 768;
    var frameCount = 0;

    /* ================================================================
       WARP-SPEED CANVAS STARFIELD
       Stars fly outward from center, mouse controls vanishing point
       ================================================================ */
    var canvas = document.getElementById('starCanvas');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var W, H, cx, cy;
    var mouseX = 0.5, mouseY = 0.5; // normalized 0-1
    var STAR_COUNT = isMobile ? 80 : 300;
    var stars = [];
    var speed = 0.5; // base warp speed

    function resize() {
        W = canvas.width = window.innerWidth;
        H = canvas.height = window.innerHeight;
        cx = W / 2;
        cy = H / 2;
    }
    resize();
    window.addEventListener('resize', resize);

    // Mouse tracking for parallax
    container.addEventListener('mousemove', function(e) {
        mouseX = e.clientX / W;
        mouseY = e.clientY / H;
    });

    // Touch tracking
    container.addEventListener('touchmove', function(e) {
        if (e.touches.length > 0) {
            mouseX = e.touches[0].clientX / W;
            mouseY = e.touches[0].clientY / H;
        }
    }, { passive: true });

    function createStar() {
        return {
            x: (Math.random() - 0.5) * 2,  // -1 to 1
            y: (Math.random() - 0.5) * 2,
            z: Math.random() * 1.5 + 0.5,   // depth
            hue: Math.random() > 0.65 ? (190 + Math.random() * 70) : 0 // some blue/cyan
        };
    }

    for (var i = 0; i < STAR_COUNT; i++) {
        stars.push(createStar());
    }

    function drawFrame() {
        // Mobile: skip every other frame for performance
        frameCount++;
        if (isMobile && frameCount % 2 !== 0) {
            requestAnimationFrame(drawFrame);
            return;
        }

        // Semi-transparent clear for trails
        ctx.fillStyle = isMobile ? 'rgba(5, 7, 20, 0.45)' : 'rgba(5, 7, 20, 0.25)';
        ctx.fillRect(0, 0, W, H);

        // Vanishing point follows mouse
        var vpx = cx + (mouseX - 0.5) * W * 0.3;
        var vpy = cy + (mouseY - 0.5) * H * 0.3;

        for (var i = 0; i < stars.length; i++) {
            var s = stars[i];

            // Move star toward viewer (decrease z)
            s.z -= speed * 0.008;
            if (s.z <= 0.01) {
                stars[i] = createStar();
                stars[i].z = 1.5 + Math.random() * 0.5;
                continue;
            }

            // Project to screen
            var scale = 1 / s.z;
            var sx = vpx + s.x * scale * W * 0.5;
            var sy = vpy + s.y * scale * H * 0.5;

            // Skip if off screen
            if (sx < -50 || sx > W + 50 || sy < -50 || sy > H + 50) continue;

            var brightness = Math.min(1, (1.5 - s.z) / 1.2);
            var size = Math.max(0.5, (1.5 - s.z) * 1.8);

            // Trail line (skip on mobile)
            if (!isMobile) {
                var pz = s.z + speed * 0.008;
                var pscale = 1 / pz;
                var px = vpx + s.x * pscale * W * 0.5;
                var py = vpy + s.y * pscale * H * 0.5;
                ctx.beginPath();
                ctx.moveTo(px, py);
                ctx.lineTo(sx, sy);
                ctx.lineWidth = size * 0.7;
                if (s.hue > 0) {
                    ctx.strokeStyle = 'hsla(' + s.hue + ', 80%, 75%, ' + (brightness * 0.4) + ')';
                } else {
                    ctx.strokeStyle = 'rgba(200, 210, 255, ' + (brightness * 0.4) + ')';
                }
                ctx.stroke();
            }

            // Star dot
            ctx.beginPath();
            ctx.arc(sx, sy, size, 0, Math.PI * 2);
            if (s.hue > 0) {
                ctx.fillStyle = 'hsla(' + s.hue + ', 80%, 80%, ' + brightness + ')';
            } else {
                ctx.fillStyle = 'rgba(220, 230, 255, ' + brightness + ')';
            }
            ctx.fill();

            // Glow for close/bright stars (skip on mobile)
            if (!isMobile && size > 2) {
                ctx.beginPath();
                ctx.arc(sx, sy, size * 3, 0, Math.PI * 2);
                if (s.hue > 0) {
                    ctx.fillStyle = 'hsla(' + s.hue + ', 70%, 70%, ' + (brightness * 0.06) + ')';
                } else {
                    ctx.fillStyle = 'rgba(180, 200, 255, ' + (brightness * 0.06) + ')';
                }
                ctx.fill();
            }
        }

        requestAnimationFrame(drawFrame);
    }
    requestAnimationFrame(drawFrame);

    /* ================================================================
       NEBULA ORBS - Breathing + drifting
       ================================================================ */
    document.querySelectorAll('.nebula-orb').forEach(function(orb, idx) {
        if (isMobile) {
            // Static orbs on mobile — no animation, save GPU
            gsap.set(orb, { opacity: 0.3 });
            return;
        }
        gsap.to(orb, { opacity: 0.8, duration: 2.5, delay: 0.4 * idx, ease: 'power2.out' });
        gsap.to(orb, {
            x: function() { return (Math.random() - 0.5) * 80; },
            y: function() { return (Math.random() - 0.5) * 60; },
            duration: function() { return 8 + Math.random() * 6; },
            repeat: -1, yoyo: true, ease: 'sine.inOut', delay: idx * 0.8
        });
        gsap.to(orb, {
            scale: 1.15 + Math.random() * 0.1,
            duration: 4 + Math.random() * 3,
            repeat: -1, yoyo: true, ease: 'sine.inOut', delay: idx * 0.5
        });
    });

    /* ================================================================
       SHOOTING STARS - colored trails
       ================================================================ */
    function shootStar(el) {
        if (!el) return;
        var startX = -150;
        var startY = Math.random() * window.innerHeight * 0.5;
        var angle = -20 + Math.random() * 15;
        gsap.set(el, { x: startX, y: startY, rotation: angle, opacity: 0 });
        gsap.to(el, {
            x: window.innerWidth + 200,
            y: startY + Math.tan(angle * Math.PI / 180) * (window.innerWidth + 350),
            opacity: 1, duration: 0.6 + Math.random() * 0.4, ease: 'power1.in',
            onComplete: function() {
                gsap.to(el, { opacity: 0, duration: 0.15, onComplete: function() {
                    setTimeout(function() { shootStar(el); }, 2500 + Math.random() * 6000);
                }});
            }
        });
    }
    if (!isMobile) {
        setTimeout(function() { shootStar(document.getElementById('ss1')); }, 1500);
        setTimeout(function() { shootStar(document.getElementById('ss2')); }, 4500);
        setTimeout(function() { shootStar(document.getElementById('ss3')); }, 7500);
    }

    /* ================================================================
       FLOATING PARTICLES
       ================================================================ */
    var pColors = [
        'rgba(124,92,252,0.6)','rgba(0,240,255,0.5)',
        'rgba(240,147,251,0.5)','rgba(56,189,248,0.4)','rgba(255,255,255,0.3)'
    ];
    var particleCount = isMobile ? 4 : 15;
    for (var p = 0; p < particleCount; p++) {
        var dot = document.createElement('div');
        dot.className = 'particle';
        var sz = 2 + Math.random() * 3;
        dot.style.width = sz + 'px';
        dot.style.height = sz + 'px';
        dot.style.background = pColors[Math.floor(Math.random() * pColors.length)];
        dot.style.left = Math.random() * 100 + '%';
        dot.style.top = Math.random() * 100 + '%';
        dot.style.opacity = '0';
        container.appendChild(dot);
        gsap.to(dot, { opacity: 0.3 + Math.random() * 0.4, duration: 1 + Math.random(), delay: Math.random() * 2 });
        gsap.to(dot, {
            y: -60 - Math.random() * 100, x: (Math.random() - 0.5) * 80,
            duration: 10 + Math.random() * 12, repeat: -1, yoyo: true, ease: 'sine.inOut', delay: Math.random() * 3
        });
    }

    /* ================================================================
       SPACE CARDS - Rich floating info cards with multiple styles
       ================================================================ */

    // --- Type A: Space fact pill badges (original style) ---
    var facts = [
        { icon: 'bi-globe-americas', text: 'ISS orbita a', val: '27.600 km/h' },
        { icon: 'bi-rocket-takeoff', text: 'Distância à Lua:', val: '384.400 km' },
        { icon: 'bi-people-fill', text: 'Humanos no espaço:', val: '7 agora' },
        { icon: 'bi-sun-fill', text: '1M de Terras cabem', val: 'no Sol' },
        { icon: 'bi-stars', text: 'Via Láctea tem', val: '200 bi estrelas' },
        { icon: 'bi-arrow-up-right', text: 'ISS altitude:', val: '408 km' },
        { icon: 'bi-clock-history', text: 'Luz do Sol chega em', val: '8 min 20s' },
        { icon: 'bi-thermometer-snow', text: 'Espaço profundo:', val: '-270 °C' },
        { icon: 'bi-lightning-charge', text: 'Velocidade da luz:', val: '300.000 km/s' },
        { icon: 'bi-tsunami', text: 'Gravidade em Marte:', val: '38% da Terra' },
        { icon: 'bi-hourglass-split', text: 'Dia em Vênus:', val: '243 dias' },
        { icon: 'bi-gem', text: 'Diamante gigante:', val: 'BPM 37093' }
    ];

    // --- Type B: Dashboard stat cards ---
    var statCards = [
        { icon: 'bi-broadcast',           label: 'SINAL',        val: 'Online',     theme: 'green',  live: true },
        { icon: 'bi-shield-lock-fill',    label: 'CRIPTOGRAFIA', val: 'AES-256',    theme: 'cyan',   live: false },
        { icon: 'bi-speedometer2',        label: 'LATÊNCIA',     val: '12 ms',      theme: 'purple', live: true },
        { icon: 'bi-hdd-network-fill',    label: 'SERVIDORES',   val: '99.97% up',  theme: 'green',  live: true },
        { icon: 'bi-globe2',              label: 'COBERTURA',    val: '190 países',  theme: 'blue',   live: false },
        { icon: 'bi-cpu',                 label: 'PROCESSAMENTO',val: '< 50 ms',    theme: 'purple', live: false },
        { icon: 'bi-database-fill-check', label: 'DADOS',        val: 'Protegidos',  theme: 'cyan',   live: false },
        { icon: 'bi-ev-front-fill',       label: 'UPTIME',       val: '364 dias',   theme: 'green',  live: true },
        { icon: 'bi-lightning-charge-fill',label: 'VELOCIDADE',   val: '1.2 Gbps',   theme: 'amber',  live: false },
        { icon: 'bi-fingerprint',         label: 'AUTH',         val: '2FA Ativo',  theme: 'pink',   live: true },
        { icon: 'bi-cloud-check-fill',    label: 'BACKUP',       val: 'Automático', theme: 'blue',   live: false },
        { icon: 'bi-fire',                label: 'TRENDING',     val: '#1 Brasil',  theme: 'amber',  live: true }
    ];

    function createFactEl(fact) {
        var el = document.createElement('div');
        el.className = 'space-fact';
        el.innerHTML = '<i class="bi ' + fact.icon + '"></i> ' +
            fact.text + ' <span class="sf-val">' + fact.val + '</span>';
        return el;
    }

    function createStatCard(card) {
        var el = document.createElement('div');
        el.className = 'space-card space-card--' + card.theme;
        var liveHtml = card.live ? '<span class="live-dot"></span>' : '';
        el.innerHTML =
            '<div class="sc-icon"><i class="bi ' + card.icon + '"></i></div>' +
            '<div class="sc-body">' +
                '<span class="sc-label">' + card.label + '</span>' +
                '<span class="sc-value">' + liveHtml + card.val + '</span>' +
            '</div>';
        return el;
    }

    function shuffle(arr) {
        var a = arr.slice();
        for (var i = a.length - 1; i > 0; i--) {
            var j = Math.floor(Math.random() * (i + 1));
            var tmp = a[i]; a[i] = a[j]; a[j] = tmp;
        }
        return a;
    }

    function placeCard(el, pos, idx) {
        if (pos.left)   el.style.left   = pos.left;
        if (pos.right)  el.style.right  = pos.right;
        if (pos.top)    el.style.top    = pos.top;
        if (pos.bottom) el.style.bottom = pos.bottom;
        container.appendChild(el);

        // Entrance from random direction
        var angle = (idx / 8) * Math.PI * 2;
        var dist = 60 + Math.random() * 40;
        gsap.set(el, { x: Math.cos(angle) * dist, y: Math.sin(angle) * dist });
        gsap.to(el, { opacity: 1, x: 0, y: 0, duration: 1.0 + Math.random() * 0.5, delay: 1.2 + idx * 0.3, ease: 'back.out(1.2)' });

        // Continuous float — mix of patterns
        var pattern = idx % 3;
        if (pattern === 0) {
            // Drift
            gsap.to(el, {
                y: (Math.random() - 0.5) * 25, x: (Math.random() - 0.5) * 18,
                duration: 5 + Math.random() * 5, repeat: -1, yoyo: true, ease: 'sine.inOut',
                delay: 2 + idx * 0.2
            });
        } else if (pattern === 1) {
            // Ellipse orbit
            gsap.to(el, {
                motionPath: { path: [
                    { x: 12, y: -8 }, { x: 0, y: -16 }, { x: -12, y: -8 }, { x: 0, y: 0 }
                ], curviness: 2 },
                duration: 8 + Math.random() * 4, repeat: -1, ease: 'none', delay: 2 + idx * 0.3
            });
            // Fallback without motionPath plugin — just gentle wave
            gsap.to(el, {
                y: '+=' + ((Math.random() - 0.5) * 20), duration: 6 + Math.random() * 4,
                repeat: -1, yoyo: true, ease: 'sine.inOut', delay: 2
            });
        } else {
            // Wave (Lissajous)
            gsap.to(el, {
                x: (Math.random() - 0.5) * 22, duration: 7 + Math.random() * 3,
                repeat: -1, yoyo: true, ease: 'sine.inOut', delay: 2 + idx * 0.1
            });
            gsap.to(el, {
                y: (Math.random() - 0.5) * 18, duration: 5 + Math.random() * 4,
                repeat: -1, yoyo: true, ease: 'sine.inOut', delay: 2.5 + idx * 0.15
            });
        }
    }

    // Desktop: 8 cards (4 facts + 4 stat cards)
    if (window.innerWidth >= 1024) {
        var pickedFacts = shuffle(facts).slice(0, 4);
        var pickedStats = shuffle(statCards).slice(0, 4);

        var positions = [
            // Left side
            { left: '2%',  top: '8%' },
            { left: '1%',  top: '42%' },
            { left: '3%',  bottom: '12%' },
            { left: '1%',  bottom: '38%' },
            // Right side
            { right: '2%', top: '10%' },
            { right: '1%', top: '44%' },
            { right: '3%', bottom: '10%' },
            { right: '1%', bottom: '36%' }
        ];

        // Interleave: fact, stat, fact, stat, ...
        var allCards = [];
        for (var ci = 0; ci < 4; ci++) {
            allCards.push({ type: 'fact', data: pickedFacts[ci] });
            allCards.push({ type: 'stat', data: pickedStats[ci] });
        }

        allCards.forEach(function(c, idx) {
            var el = c.type === 'fact' ? createFactEl(c.data) : createStatCard(c.data);
            placeCard(el, positions[idx], idx);
        });

    } else if (window.innerWidth >= 769) {
        // Tablet: 4 cards (2 facts + 2 stat cards)
        var pickedFacts2 = shuffle(facts).slice(0, 2);
        var pickedStats2 = shuffle(statCards).slice(0, 2);
        var tpos = [
            { left: '2%', top: '6%' },
            { right: '2%', top: '10%' },
            { left: '2%', bottom: '8%' },
            { right: '2%', bottom: '6%' }
        ];
        var tabCards = [
            { type: 'fact', data: pickedFacts2[0] },
            { type: 'stat', data: pickedStats2[0] },
            { type: 'fact', data: pickedFacts2[1] },
            { type: 'stat', data: pickedStats2[1] }
        ];
        tabCards.forEach(function(c, idx) {
            var el = c.type === 'fact' ? createFactEl(c.data) : createStatCard(c.data);
            placeCard(el, tpos[idx], idx);
        });
    }

    /* ================================================================
       FOCUS GLOW on inputs
       ================================================================ */
    document.querySelectorAll('.form-control').forEach(function(inp) {
        inp.addEventListener('focus', function() {
            gsap.to(this.closest('.input-group'), {
                boxShadow: '0 0 25px rgba(0,240,255,0.12), 0 0 4px rgba(0,240,255,0.08)',
                duration: 0.3
            });
        });
        inp.addEventListener('blur', function() {
            gsap.to(this.closest('.input-group'), { boxShadow: 'none', duration: 0.3 });
        });
    });
})();
