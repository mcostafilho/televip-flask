/* ================================================================
   TeleVIP Auth - Warp Speed Starfield + Space Facts
   Shared between login.html and register.html
   ================================================================ */

(function() {
    'use strict';
    var container = document.querySelector('.auth-container');
    if (!container || typeof gsap === 'undefined') return;

    /* ================================================================
       WARP-SPEED CANVAS STARFIELD
       Stars fly outward from center, mouse controls vanishing point
       ================================================================ */
    var canvas = document.getElementById('starCanvas');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var W, H, cx, cy;
    var mouseX = 0.5, mouseY = 0.5; // normalized 0-1
    var STAR_COUNT = 300;
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
        // Semi-transparent clear for trails
        ctx.fillStyle = 'rgba(5, 7, 20, 0.25)';
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

            // Previous position for trail
            var pz = s.z + speed * 0.008;
            var pscale = 1 / pz;
            var px = vpx + s.x * pscale * W * 0.5;
            var py = vpy + s.y * pscale * H * 0.5;

            // Skip if off screen
            if (sx < -50 || sx > W + 50 || sy < -50 || sy > H + 50) continue;

            var brightness = Math.min(1, (1.5 - s.z) / 1.2);
            var size = Math.max(0.5, (1.5 - s.z) * 1.8);

            // Trail line
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

            // Star dot
            ctx.beginPath();
            ctx.arc(sx, sy, size, 0, Math.PI * 2);
            if (s.hue > 0) {
                ctx.fillStyle = 'hsla(' + s.hue + ', 80%, 80%, ' + brightness + ')';
            } else {
                ctx.fillStyle = 'rgba(220, 230, 255, ' + brightness + ')';
            }
            ctx.fill();

            // Glow for close/bright stars
            if (size > 2) {
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
    setTimeout(function() { shootStar(document.getElementById('ss1')); }, 1500);
    setTimeout(function() { shootStar(document.getElementById('ss2')); }, 4500);
    setTimeout(function() { shootStar(document.getElementById('ss3')); }, 7500);

    /* ================================================================
       FLOATING PARTICLES
       ================================================================ */
    var pColors = [
        'rgba(124,92,252,0.6)','rgba(0,240,255,0.5)',
        'rgba(240,147,251,0.5)','rgba(56,189,248,0.4)','rgba(255,255,255,0.3)'
    ];
    for (var p = 0; p < 15; p++) {
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
       SPACE FACTS - floating data badges
       ================================================================ */
    var facts = [
        { icon: 'bi-globe-americas', text: 'ISS orbita a', val: '27.600 km/h' },
        { icon: 'bi-rocket-takeoff', text: 'Distância à Lua:', val: '384.400 km' },
        { icon: 'bi-people-fill', text: 'Humanos no espaço:', val: '7 agora' },
        { icon: 'bi-sun-fill', text: '1M de Terras cabem', val: 'no Sol' },
        { icon: 'bi-stars', text: 'Via Láctea tem', val: '200 bi estrelas' },
        { icon: 'bi-arrow-up-right', text: 'ISS altitude:', val: '408 km' },
        { icon: 'bi-clock-history', text: 'Luz do Sol chega em', val: '8 min 20s' },
        { icon: 'bi-thermometer-snow', text: 'Espaço profundo:', val: '-270 °C' }
    ];

    // Only show on desktop
    if (window.innerWidth >= 1024) {
        // Pick 4 random facts
        var shuffled = facts.sort(function() { return 0.5 - Math.random(); });
        var selected = shuffled.slice(0, 4);

        // Position facts in corners/sides, avoiding center card area
        var positions = [
            { left: '3%', top: '12%' },
            { right: '3%', top: '18%' },
            { left: '4%', bottom: '15%' },
            { right: '4%', bottom: '12%' }
        ];

        selected.forEach(function(fact, idx) {
            var el = document.createElement('div');
            el.className = 'space-fact';
            el.innerHTML = '<i class="bi ' + fact.icon + '"></i> ' +
                fact.text + ' <span class="sf-val">' + fact.val + '</span>';

            var pos = positions[idx];
            if (pos.left) el.style.left = pos.left;
            if (pos.right) el.style.right = pos.right;
            if (pos.top) el.style.top = pos.top;
            if (pos.bottom) el.style.bottom = pos.bottom;

            container.appendChild(el);

            // Entrance
            gsap.to(el, { opacity: 1, duration: 1.2, delay: 1.5 + idx * 0.4, ease: 'power2.out' });
            // Subtle float
            gsap.to(el, {
                y: (Math.random() - 0.5) * 20,
                x: (Math.random() - 0.5) * 15,
                duration: 5 + Math.random() * 4,
                repeat: -1, yoyo: true, ease: 'sine.inOut',
                delay: 2 + idx * 0.3
            });
        });
    } else if (window.innerWidth >= 769) {
        // Tablet: 2 facts
        var shuffled2 = facts.sort(function() { return 0.5 - Math.random(); });
        var sel2 = shuffled2.slice(0, 2);
        var tpos = [
            { left: '3%', top: '8%' },
            { right: '3%', bottom: '8%' }
        ];
        sel2.forEach(function(fact, idx) {
            var el = document.createElement('div');
            el.className = 'space-fact';
            el.innerHTML = '<i class="bi ' + fact.icon + '"></i> ' +
                fact.text + ' <span class="sf-val">' + fact.val + '</span>';
            var pos = tpos[idx];
            if (pos.left) el.style.left = pos.left;
            if (pos.right) el.style.right = pos.right;
            if (pos.top) el.style.top = pos.top;
            if (pos.bottom) el.style.bottom = pos.bottom;
            container.appendChild(el);
            gsap.to(el, { opacity: 1, duration: 1.2, delay: 1.5 + idx * 0.5, ease: 'power2.out' });
            gsap.to(el, {
                y: (Math.random() - 0.5) * 15, duration: 6 + Math.random() * 3,
                repeat: -1, yoyo: true, ease: 'sine.inOut', delay: 2
            });
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
