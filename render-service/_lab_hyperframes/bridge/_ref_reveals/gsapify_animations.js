/* ============================================
   GSAP Animations Collection — 100 Effects
   ============================================ */
(function () {
  'use strict';

  /* Register core plugins */
  gsap.registerPlugin(ScrollTrigger, Flip, Draggable, Observer, MotionPathPlugin, TextPlugin);

  /* Register bonus plugins (graceful fallback if CDN hasn't loaded yet) */
  [
    'DrawSVGPlugin', 'MorphSVGPlugin', 'Physics2DPlugin', 'PhysicsPropsPlugin',
    'InertiaPlugin', 'ScrambleTextPlugin', 'SplitText',
    'CustomEase', 'CustomBounce', 'CustomWiggle'
  ].forEach(function (name) {
    if (typeof window[name] !== 'undefined') {
      gsap.registerPlugin(window[name]);
    }
  });

  /* ─── HELPER: split text into chars ─── */
  function splitChars(el) {
    const text = el.textContent;
    el.innerHTML = '';
    return [...text].map(ch => {
      const span = document.createElement('span');
      span.textContent = ch;
      span.style.display = 'inline-block';
      if (ch === ' ') span.style.width = '0.3em';
      el.appendChild(span);
      return span;
    });
  }
  function splitWords(el) {
    const words = el.textContent.trim().split(/\s+/);
    el.innerHTML = '';
    return words.map((w, i) => {
      const span = document.createElement('span');
      span.textContent = w;
      span.style.display = 'inline-block';
      span.style.marginRight = '0.3em';
      el.appendChild(span);
      return span;
    });
  }
  function splitLines(el) {
    const html = el.innerHTML;
    const parts = html.split(/<br\s*\/?>/gi);
    el.innerHTML = '';
    return parts.map(p => {
      const div = document.createElement('div');
      div.innerHTML = p.trim();
      div.style.overflow = 'hidden';
      el.appendChild(div);
      return div;
    });
  }

  /* ─── EFFECTS REGISTRY ─── */
  const effects = {

    /* ══════════════════════════════
       1. TEXT & TYPOGRAPHY
       ══════════════════════════════ */
    'stagger-letter-reveal': (container) => {
      const el = container.querySelector('.ga-text');
      const chars = splitChars(el);
      return gsap.from(chars, { opacity: 0, y: 30, duration: 0.5, stagger: 0.03, ease: 'back.out(1.7)' });
    },
    'typewriter': (container) => {
      const target = container.querySelector('.ga-type-target');
      target.textContent = '';
      return gsap.to(target, { text: { value: 'Hello, World!', delimiter: '' }, duration: 2, ease: 'none' });
    },
    'text-scramble': (container) => {
      const el = container.querySelector('.ga-text');
      const orig = el.textContent;
      el.textContent = orig;
      // Simulate scramble with random characters
      const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*';
      const tl = gsap.timeline();
      let iterations = 0;
      tl.to(el, {
        duration: 1.5, ease: 'none',
        onUpdate: function() {
          const progress = this.progress();
          const len = orig.length;
          const revealed = Math.floor(progress * len);
          let str = '';
          for (let i = 0; i < len; i++) {
            if (i < revealed) str += orig[i];
            else str += chars[Math.floor(Math.random() * chars.length)];
          }
          el.textContent = str;
        },
        onComplete: () => { el.textContent = orig; }
      });
      return tl;
    },
    'word-by-word-slide': (container) => {
      const el = container.querySelector('.ga-text');
      const words = splitWords(el);
      return gsap.from(words, { opacity: 0, y: 40, rotation: 5, duration: 0.6, stagger: 0.1, ease: 'power3.out' });
    },
    'kinetic-split-lines': (container) => {
      const el = container.querySelector('.ga-text');
      const lines = splitLines(el);
      const tl = gsap.timeline();
      lines.forEach((line, i) => {
        tl.from(line.firstChild || line, { x: i % 2 === 0 ? -100 : 100, opacity: 0, duration: 0.7, ease: 'power3.out' }, i * 0.15);
      });
      return tl;
    },
    'letter-3d-flip': (container) => {
      const el = container.querySelector('.ga-text');
      const chars = splitChars(el);
      return gsap.from(chars, { rotationY: -90, opacity: 0, duration: 0.6, stagger: 0.05, ease: 'back.out(1.4)', transformOrigin: '50% 50% -20px' });
    },
    'gradient-text-reveal': (container) => {
      const el = container.querySelector('.ga-gradient-text');
      return gsap.fromTo(el, { backgroundPosition: '200% 0' }, { backgroundPosition: '0% 0', duration: 2, ease: 'power2.inOut' });
    },
    'glitch-text': (container) => {
      const el = container.querySelector('.ga-glitch');
      el.classList.add('glitching');
      const tl = gsap.timeline();
      tl.to(el, { x: -3, duration: 0.05 })
        .to(el, { x: 3, duration: 0.05 })
        .to(el, { x: -1, duration: 0.05 })
        .to(el, { x: 0, duration: 0.05 })
        .to(el, { skewX: 2, duration: 0.05 })
        .to(el, { skewX: 0, duration: 0.05 })
        .add(() => { setTimeout(() => el.classList.remove('glitching'), 1000); }, '+=0.5');
      return tl;
    },
    'matrix-decode': (container) => {
      const el = container.querySelector('.ga-text');
      const orig = el.textContent;
      const matrix = 'ﾊﾐﾋｰｳｼﾅﾓﾆｻﾜﾂｵﾘ012345789ABCDEF';
      const tl = gsap.timeline();
      tl.to(el, {
        duration: 2.5, ease: 'none',
        onUpdate: function() {
          const p = this.progress();
          const len = orig.length;
          const revealed = Math.floor(p * len);
          let str = '';
          for (let i = 0; i < len; i++) {
            if (i < revealed) str += orig[i];
            else str += matrix[Math.floor(Math.random() * matrix.length)];
          }
          el.textContent = str;
        },
        onComplete: () => { el.textContent = orig; }
      });
      return tl;
    },
    'encryption-viz': (container) => {
      const el = container.querySelector('.ga-text');
      const orig = el.textContent;
      const cipher = 'ÆØÅ§¶•†‡';
      const tl = gsap.timeline();
      // Encrypt
      tl.to(el, {
        duration: 1, ease: 'none',
        onUpdate: function() {
          const p = this.progress();
          let str = '';
          for (let i = 0; i < orig.length; i++) {
            str += (Math.random() < p && orig[i] !== ' ') ? cipher[Math.floor(Math.random() * cipher.length)] : orig[i];
          }
          el.textContent = str;
        }
      });
      tl.to({}, { duration: 0.8 }); // Hold
      // Decrypt
      tl.to(el, {
        duration: 1, ease: 'none',
        onUpdate: function() {
          const p = this.progress();
          let str = '';
          for (let i = 0; i < orig.length; i++) {
            str += (Math.random() < p) ? orig[i] : cipher[Math.floor(Math.random() * cipher.length)];
          }
          el.textContent = str;
        },
        onComplete: () => { el.textContent = orig; }
      });
      return tl;
    },
    'per-char-physics': (container) => {
      const el = container.querySelector('.ga-text');
      const chars = splitChars(el);
      const tl = gsap.timeline();
      chars.forEach(ch => {
        tl.from(ch, {
          y: -200, opacity: 0,
          duration: 0.8,
          ease: 'bounce.out'
        }, Math.random() * 0.5);
      });
      return tl;
    },
    'liquid-text-wave': (container) => {
      const el = container.querySelector('.ga-text');
      const chars = splitChars(el);
      const tl = gsap.timeline({ repeat: 2 });
      chars.forEach((ch, i) => {
        tl.to(ch, { y: -15, duration: 0.3, ease: 'sine.inOut', yoyo: true, repeat: 1 }, i * 0.05);
      });
      return tl;
    },

    /* ══════════════════════════════
       2. SCROLL ANIMATIONS
       ══════════════════════════════ */
    'fade-up-scroll': (container) => {
      const boxes = container.querySelectorAll('.ga-box');
      return gsap.from(boxes, { opacity: 0, y: 40, duration: 0.6, stagger: 0.15, ease: 'power2.out' });
    },
    'parallax-layers': (container) => {
      const layers = container.querySelectorAll('.ga-parallax-layer');
      const tl = gsap.timeline();
      layers.forEach((l, i) => {
        tl.fromTo(l, { y: 30 + i * 10 }, { y: -30 - i * 10, duration: 2, ease: 'none' }, 0);
      });
      return tl;
    },
    'horizontal-scroll': (container) => {
      const track = container.querySelector('.ga-hscroll-track');
      return gsap.fromTo(track, { x: 0 }, { x: -160, duration: 2, ease: 'power1.inOut', yoyo: true, repeat: 1 });
    },
    'scroll-scrub': (container) => {
      const ring = container.querySelector('.ga-scrub-ring');
      return gsap.to(ring, { rotation: 360, duration: 2, ease: 'none', repeat: 1 });
    },
    'staggered-grid-reveal': (container) => {
      const cells = container.querySelectorAll('.ga-grid-cell');
      return gsap.from(cells, { scale: 0, opacity: 0, duration: 0.4, stagger: { amount: 0.6, from: 'center' }, ease: 'back.out(1.7)' });
    },
    'scroll-velocity-skew': (container) => {
      const bars = container.querySelectorAll('.ga-skew-bar');
      const tl = gsap.timeline();
      tl.to(bars, { skewX: 10, duration: 0.3, ease: 'power2.in' })
        .to(bars, { skewX: -5, duration: 0.2, ease: 'power2.out' })
        .to(bars, { skewX: 0, duration: 0.4, ease: 'elastic.out(1, 0.5)' });
      return tl;
    },
    'layered-zoom': (container) => {
      const layers = container.querySelectorAll('.ga-zoom-layer');
      const tl = gsap.timeline();
      layers.forEach((l, i) => {
        tl.fromTo(l, { scale: 0.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.6, ease: 'power2.out' }, i * 0.2);
      });
      return tl;
    },
    'velocity-blur': (container) => {
      const el = container.querySelector('.ga-text');
      const tl = gsap.timeline();
      tl.to(el, { filter: 'blur(8px)', y: -20, duration: 0.3, ease: 'power2.in' })
        .to(el, { filter: 'blur(0px)', y: 0, duration: 0.5, ease: 'power2.out' });
      return tl;
    },
    'tilt-parallax-card': (container) => {
      const card = container.querySelector('.ga-tilt-card');
      const layers = card.querySelectorAll('.ga-tilt-layer');
      card.addEventListener('mousemove', (e) => {
        const rect = card.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width - 0.5;
        const y = (e.clientY - rect.top) / rect.height - 0.5;
        gsap.to(card, { rotateY: x * 20, rotateX: -y * 20, duration: 0.3, ease: 'power2.out', transformPerspective: 600 });
        layers.forEach((l, i) => {
          gsap.to(l, { x: x * (i + 1) * 10, y: y * (i + 1) * 10, duration: 0.3 });
        });
      });
      card.addEventListener('mouseleave', () => {
        gsap.to(card, { rotateY: 0, rotateX: 0, duration: 0.5, ease: 'power2.out' });
        layers.forEach(l => gsap.to(l, { x: 0, y: 0, duration: 0.5 }));
      });
      return gsap.from(card, { opacity: 0, scale: 0.9, duration: 0.5 });
    },

    /* ══════════════════════════════
       3. CARDS & COMPONENTS
       ══════════════════════════════ */
    'card-hover-lift': (container) => {
      const card = container.querySelector('.ga-hover-card');
      card.addEventListener('mouseenter', () => {
        gsap.to(card, { y: -8, scale: 1.02, boxShadow: '0 20px 40px rgba(0,255,102,0.1)', duration: 0.3 });
      });
      card.addEventListener('mouseleave', () => {
        gsap.to(card, { y: 0, scale: 1, boxShadow: 'none', duration: 0.3 });
      });
      return gsap.from(card, { opacity: 0, y: 20, duration: 0.5 });
    },
    'card-3d-flip': (container) => {
      const inner = container.querySelector('.ga-flip-inner');
      let flipped = false;
      container.querySelector('.ga-flip-container').addEventListener('click', () => {
        flipped = !flipped;
        gsap.to(inner, { rotationY: flipped ? 180 : 0, duration: 0.6, ease: 'power2.inOut' });
      });
      return gsap.from(inner, { opacity: 0, scale: 0.8, duration: 0.5 });
    },
    'card-expand-detail': (container) => {
      const cards = container.querySelectorAll('.ga-expand-card');
      cards.forEach(card => {
        card.addEventListener('click', () => {
          const isExpanded = card.classList.contains('expanded');
          cards.forEach(c => c.classList.remove('expanded'));
          if (!isExpanded) card.classList.add('expanded');
        });
      });
      return gsap.from(cards, { opacity: 0, y: 20, stagger: 0.1, duration: 0.5 });
    },
    'stacked-card-fan': (container) => {
      const cards = container.querySelectorAll('.ga-stack-card');
      const spread = () => {
        cards.forEach((c, i) => {
          gsap.to(c, { x: (i - 2) * 25, rotation: (i - 2) * 8, duration: 0.5, ease: 'back.out(1.4)' });
        });
      };
      const collapse = () => {
        cards.forEach((c, i) => {
          gsap.to(c, { x: i * 2, y: -i * 2, rotation: 0, duration: 0.4, ease: 'power2.inOut' });
        });
      };
      const stack = container.querySelector('.ga-card-stack');
      stack.addEventListener('mouseenter', spread);
      stack.addEventListener('mouseleave', collapse);
      collapse();
      return gsap.from(cards, { opacity: 0, scale: 0, stagger: 0.05, duration: 0.4 });
    },
    'card-slide-stagger': (container) => {
      const cards = container.querySelectorAll('.ga-slide-card');
      return gsap.from(cards, { x: (i) => i % 2 === 0 ? -100 : 100, opacity: 0, duration: 0.6, stagger: 0.15, ease: 'power3.out' });
    },
    'card-bg-shift': (container) => {
      const card = container.querySelector('.ga-bg-shift-card');
      card.addEventListener('mouseenter', () => {
        gsap.to(card, { backgroundPosition: '100% 100%', duration: 0.8, ease: 'power2.out' });
      });
      card.addEventListener('mouseleave', () => {
        gsap.to(card, { backgroundPosition: '0% 0%', duration: 0.8, ease: 'power2.out' });
      });
      return gsap.from(card, { opacity: 0, duration: 0.5 });
    },
    'flip-grid-filter': (container) => {
      const btns = container.querySelectorAll('.ga-filter-btn');
      const items = container.querySelectorAll('.ga-filter-item');
      btns.forEach(btn => {
        btn.addEventListener('click', () => {
          btns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const filter = btn.dataset.filter;
          const state = Flip.getState(items);
          items.forEach(item => {
            item.style.display = (filter === 'all' || item.dataset.cat === filter) ? '' : 'none';
          });
          Flip.from(state, { duration: 0.5, ease: 'power2.inOut', stagger: 0.05, absolute: true });
        });
      });
      return gsap.from(items, { opacity: 0, scale: 0.5, stagger: 0.05, duration: 0.4 });
    },
    'shared-element-transition': (container) => {
      const thumbs = container.querySelectorAll('.ga-shared-thumb');
      thumbs.forEach(thumb => {
        thumb.addEventListener('click', () => {
          const wasActive = thumb.classList.contains('active');
          const state = Flip.getState(thumbs);
          thumbs.forEach(t => t.classList.remove('active'));
          if (!wasActive) thumb.classList.add('active');
          Flip.from(state, { duration: 0.4, ease: 'power2.inOut' });
        });
      });
      return gsap.from(thumbs, { scale: 0, stagger: 0.05, duration: 0.4 });
    },
    'accordion-motion': (container) => {
      const items = container.querySelectorAll('.ga-acc-item');
      items.forEach(item => {
        const header = item.querySelector('.ga-acc-header');
        header.addEventListener('click', () => {
          const wasActive = item.classList.contains('active');
          items.forEach(it => it.classList.remove('active'));
          if (!wasActive) item.classList.add('active');
        });
      });
      return gsap.from(items, { opacity: 0, y: 10, stagger: 0.1, duration: 0.4 });
    },

    /* ══════════════════════════════
       4. IMAGE & GALLERY
       ══════════════════════════════ */
    'clip-path-reveal': (container) => {
      const img = container.querySelector('.ga-clip-img');
      return gsap.to(img, { clipPath: 'polygon(0 0, 100% 0, 100% 100%, 0 100%)', duration: 1.2, ease: 'power3.inOut' });
    },
    'image-parallax-zoom': (container) => {
      const img = container.querySelector('.ga-parallax-img');
      return gsap.fromTo(img, { scale: 1.3, y: 30 }, { scale: 1, y: -30, duration: 2, ease: 'none' });
    },
    'before-after-slider': (container) => {
      const handle = container.querySelector('.ga-ba-handle');
      const before = container.querySelector('.ga-ba-before');
      const containerEl = container.querySelector('.ga-ba-container');
      if (containerEl) {
        containerEl.addEventListener('mousemove', (e) => {
          const rect = containerEl.getBoundingClientRect();
          const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
          gsap.to(handle, { left: x * 100 + '%', duration: 0.1 });
          gsap.to(before, { clipPath: `inset(0 ${(1 - x) * 100}% 0 0)`, duration: 0.1 });
        });
      }
      return gsap.from(handle, { opacity: 0, duration: 0.5 });
    },
    'grayscale-to-color': (container) => {
      const img = container.querySelector('.ga-grayscale-img');
      return gsap.to(img, { filter: 'grayscale(0%)', duration: 1.5, ease: 'power2.inOut' });
    },
    'masonry-cascade': (container) => {
      const items = container.querySelectorAll('.ga-masonry-item');
      return gsap.from(items, {
        opacity: 0, y: 60, scale: 0.8, rotation: () => gsap.utils.random(-10, 10),
        duration: 0.6, stagger: { amount: 0.8, from: 'random' }, ease: 'back.out(1.4)'
      });
    },
    'image-tilt-hover': (container) => {
      const wrap = container.querySelector('.ga-tilt-img');
      const inner = container.querySelector('.ga-tilt-inner');
      wrap.addEventListener('mousemove', (e) => {
        const rect = wrap.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width - 0.5;
        const y = (e.clientY - rect.top) / rect.height - 0.5;
        gsap.to(inner, { rotateY: x * 25, rotateX: -y * 25, duration: 0.3, transformPerspective: 600 });
      });
      wrap.addEventListener('mouseleave', () => {
        gsap.to(inner, { rotateY: 0, rotateX: 0, duration: 0.5, ease: 'power2.out' });
      });
      return gsap.from(wrap, { opacity: 0, scale: 0.9, duration: 0.5 });
    },

    /* ══════════════════════════════
       5. HOVER & INTERACTIONS
       ══════════════════════════════ */
    'magnetic-button': (container) => {
      const btn = container.querySelector('.ga-magnetic-btn');
      const preview = container.closest('.ga-preview');
      preview.addEventListener('mousemove', (e) => {
        const rect = btn.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const dx = e.clientX - cx;
        const dy = e.clientY - cy;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) {
          const pull = (120 - dist) / 120;
          gsap.to(btn, { x: dx * pull * 0.4, y: dy * pull * 0.4, duration: 0.3, ease: 'power2.out' });
        } else {
          gsap.to(btn, { x: 0, y: 0, duration: 0.5, ease: 'elastic.out(1, 0.5)' });
        }
      });
      preview.addEventListener('mouseleave', () => {
        gsap.to(btn, { x: 0, y: 0, duration: 0.5, ease: 'elastic.out(1, 0.5)' });
      });
      return gsap.from(btn, { opacity: 0, scale: 0.8, duration: 0.5 });
    },
    'underline-slide': (container) => {
      // CSS handles the underline animation
      return gsap.from(container.querySelectorAll('.ga-underline-link'), { opacity: 0, y: 20, stagger: 0.1, duration: 0.5 });
    },
    'hover-border-draw': (container) => {
      // CSS handles the border draw
      return gsap.from(container.querySelector('.ga-border-draw'), { opacity: 0, scale: 0.9, duration: 0.5 });
    },
    'ripple-click': (container) => {
      const btn = container.querySelector('.ga-ripple-btn');
      btn.addEventListener('click', (e) => {
        const rect = btn.getBoundingClientRect();
        const ripple = document.createElement('span');
        ripple.className = 'ga-ripple';
        const size = Math.max(rect.width, rect.height) * 2;
        ripple.style.width = ripple.style.height = size + 'px';
        ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
        ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
        btn.appendChild(ripple);
        gsap.to(ripple, { scale: 1, opacity: 0, duration: 0.8, ease: 'power2.out', onComplete: () => ripple.remove() });
      });
      return gsap.from(btn, { opacity: 0, scale: 0.9, duration: 0.5 });
    },
    'icon-morph': (container) => {
      const svg = container.querySelector('.ga-icon-morph');
      const top = svg.querySelector('.ga-burger-top');
      const mid = svg.querySelector('.ga-burger-mid');
      const bot = svg.querySelector('.ga-burger-bot');
      let open = false;
      svg.addEventListener('click', () => {
        open = !open;
        if (open) {
          gsap.to(mid, { opacity: 0, duration: 0.2 });
          gsap.to(top, { attr: { x1: 12, y1: 12, x2: 28, y2: 28 }, duration: 0.3, ease: 'power2.inOut' });
          gsap.to(bot, { attr: { x1: 12, y1: 28, x2: 28, y2: 12 }, duration: 0.3, ease: 'power2.inOut' });
        } else {
          gsap.to(mid, { opacity: 1, duration: 0.2, delay: 0.1 });
          gsap.to(top, { attr: { x1: 8, y1: 12, x2: 32, y2: 12 }, duration: 0.3, ease: 'power2.inOut' });
          gsap.to(bot, { attr: { x1: 8, y1: 28, x2: 32, y2: 28 }, duration: 0.3, ease: 'power2.inOut' });
        }
      });
      return gsap.from(svg, { opacity: 0, scale: 0.5, duration: 0.5 });
    },
    'button-shimmer': (container) => {
      const btn = container.querySelector('.ga-shimmer-btn');
      const shimmer = btn.querySelector('::before') || btn;
      btn.addEventListener('mouseenter', () => {
        gsap.fromTo(btn, { '--shimmer-x': '-100%' }, { '--shimmer-x': '200%', duration: 0.6, ease: 'power2.inOut' });
        // Fallback: animate a pseudo-like overlay
        const overlay = document.createElement('span');
        overlay.style.cssText = 'position:absolute;top:0;left:-100%;width:60%;height:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.3),transparent);pointer-events:none;';
        btn.appendChild(overlay);
        gsap.to(overlay, { left: '200%', duration: 0.6, ease: 'power2.inOut', onComplete: () => overlay.remove() });
      });
      return gsap.from(btn, { opacity: 0, y: 20, duration: 0.5 });
    },
    'elastic-stretch': (container) => {
      const el = container.querySelector('.ga-elastic-el');
      let startX;
      el.addEventListener('mousedown', (e) => { startX = e.clientX; });
      el.addEventListener('mousemove', (e) => {
        if (startX !== undefined) {
          const dx = e.clientX - startX;
          gsap.to(el, { scaleX: 1 + Math.abs(dx) / 200, x: dx * 0.3, duration: 0.1 });
        }
      });
      const release = () => {
        startX = undefined;
        gsap.to(el, { scaleX: 1, x: 0, duration: 0.8, ease: 'elastic.out(1, 0.3)' });
      };
      el.addEventListener('mouseup', release);
      el.addEventListener('mouseleave', release);
      return gsap.from(el, { opacity: 0, scale: 0.8, duration: 0.5 });
    },
    'scratch-off': (container) => {
      const canvas = container.querySelector('.ga-scratch-overlay');
      const cont = container.querySelector('.ga-scratch-container');
      if (!canvas || !cont) return gsap.timeline();
      const ctx = canvas.getContext('2d');
      const w = cont.offsetWidth, h = cont.offsetHeight;
      canvas.width = w; canvas.height = h;
      ctx.fillStyle = '#333';
      ctx.fillRect(0, 0, w, h);
      ctx.font = 'bold 14px sans-serif';
      ctx.fillStyle = '#555';
      ctx.textAlign = 'center';
      ctx.fillText('Scratch here!', w / 2, h / 2 + 5);
      let scratching = false;
      const scratch = (e) => {
        if (!scratching) return;
        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        ctx.globalCompositeOperation = 'destination-out';
        ctx.beginPath();
        ctx.arc(x, y, 20, 0, Math.PI * 2);
        ctx.fill();
      };
      canvas.addEventListener('mousedown', () => scratching = true);
      canvas.addEventListener('mousemove', scratch);
      canvas.addEventListener('mouseup', () => scratching = false);
      canvas.addEventListener('mouseleave', () => scratching = false);
      return gsap.from(cont, { opacity: 0, duration: 0.5 });
    },
    'card-deck-toss': (container) => {
      const cards = container.querySelectorAll('.ga-deck-card');
      cards.forEach((card, i) => {
        card.style.zIndex = cards.length - i;
        gsap.set(card, { y: -i * 3 });
      });
      const deck = container.querySelector('.ga-deck');
      deck.addEventListener('click', () => {
        const top = deck.querySelector('.ga-deck-card:last-child') || cards[0];
        gsap.to(top, {
          x: gsap.utils.random(-150, 150), y: -80, rotation: gsap.utils.random(-30, 30),
          opacity: 0, duration: 0.5, ease: 'power2.out',
          onComplete: () => {
            gsap.set(top, { x: 0, y: 0, rotation: 0, opacity: 1 });
            deck.prepend(top);
            deck.querySelectorAll('.ga-deck-card').forEach((c, i) => { c.style.zIndex = cards.length - i; });
          }
        });
      });
      return gsap.from(cards, { opacity: 0, y: -50, stagger: 0.1, duration: 0.4 });
    },
    'cube-drag-3d': (container) => {
      const cube = container.querySelector('.ga-cube');
      let rotX = -20, rotY = -30;
      const scene = container.querySelector('.ga-cube-scene');
      let dragging = false, lastX, lastY;
      scene.addEventListener('mousedown', (e) => { dragging = true; lastX = e.clientX; lastY = e.clientY; });
      scene.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        rotY += (e.clientX - lastX) * 0.5;
        rotX -= (e.clientY - lastY) * 0.5;
        gsap.to(cube, { rotateX: rotX, rotateY: rotY, duration: 0.3 });
        lastX = e.clientX; lastY = e.clientY;
      });
      scene.addEventListener('mouseup', () => dragging = false);
      scene.addEventListener('mouseleave', () => dragging = false);
      return gsap.from(cube, { opacity: 0, scale: 0.5, duration: 0.6 });
    },
    'wheel-spin': (container) => {
      const inner = container.querySelector('.ga-wheel-inner');
      const svg = container.querySelector('.ga-wheel');
      let rotation = 0;
      svg.style.cursor = 'pointer';
      svg.addEventListener('click', () => {
        const spin = gsap.utils.random(720, 1440);
        rotation += spin;
        gsap.to(inner, { rotation: rotation, duration: 3, ease: 'power4.out', transformOrigin: '100px 100px' });
      });
      return gsap.from(svg, { opacity: 0, scale: 0.5, duration: 0.5 });
    },

    /* ══════════════════════════════
       6. SVG & MORPHING
       ══════════════════════════════ */
    'svg-line-draw': (container) => {
      const paths = container.querySelectorAll('.ga-svg-draw path');
      const tl = gsap.timeline();
      paths.forEach(p => {
        const len = p.getTotalLength();
        gsap.set(p, { strokeDasharray: len, strokeDashoffset: len });
        tl.to(p, { strokeDashoffset: 0, duration: 1.5, ease: 'power2.inOut' }, 0);
      });
      return tl;
    },
    'shape-morph': (container) => {
      const path = container.querySelector('.ga-morph-path');
      const shapes = [
        'M100,10 L122,72 L190,72 L135,110 L155,172 L100,140 L45,172 L65,110 L10,72 L78,72 Z', // star
        'M100,20 A80,80 0 1,1 100,180 A80,80 0 1,1 100,20 Z', // circle
        'M20,20 H180 V180 H20 Z', // square
        'M100,20 L180,180 L20,180 Z', // triangle
      ];
      let idx = 0;
      const morph = () => {
        idx = (idx + 1) % shapes.length;
        gsap.to(path, { attr: { d: shapes[idx] }, duration: 0.8, ease: 'power2.inOut' });
      };
      container.querySelector('.ga-morph-svg').addEventListener('click', morph);
      return gsap.from(path, { opacity: 0, scale: 0.5, duration: 0.5, transformOrigin: 'center' });
    },
    'animated-blob': (container) => {
      const path = container.querySelector('.ga-blob-path');
      const shapes = [
        'M140,30 C180,40 190,90 175,120 C160,150 190,185 150,185 C110,185 40,170 25,130 C10,90 20,40 60,25 C100,10 120,20 140,30 Z',
        'M130,20 C170,30 195,80 180,130 C165,180 120,195 80,180 C40,165 5,130 15,80 C25,30 90,10 130,20 Z',
        'M150,25 C185,45 195,100 170,140 C145,180 100,190 60,170 C20,150 10,100 30,60 C50,20 115,5 150,25 Z',
      ];
      let idx = 0;
      const tl = gsap.timeline({ repeat: -1, repeatDelay: 0.5 });
      shapes.forEach((s, i) => {
        tl.to(path, { attr: { d: s }, duration: 2, ease: 'sine.inOut' }, i * 2);
      });
      return tl;
    },
    'logo-stroke-reveal': (container) => {
      const text = container.querySelector('.ga-logo-text');
      if (!text) return gsap.timeline();
      const len = 600; // approximate
      gsap.set(text, { strokeDasharray: len, strokeDashoffset: len, fill: 'transparent' });
      const tl = gsap.timeline();
      tl.to(text, { strokeDashoffset: 0, duration: 2, ease: 'power2.inOut' })
        .to(text, { fill: 'var(--gs-primary)', duration: 0.8, ease: 'power2.in' }, '-=0.3');
      return tl;
    },
    'floating-shapes': (container) => {
      const shapes = container.querySelectorAll('.ga-float-shape');
      shapes.forEach(s => {
        gsap.to(s, {
          y: gsap.utils.random(-20, 20),
          x: gsap.utils.random(-10, 10),
          rotation: gsap.utils.random(-15, 15),
          duration: gsap.utils.random(2, 4),
          ease: 'sine.inOut', yoyo: true, repeat: -1
        });
      });
      return gsap.from(shapes, { opacity: 0, scale: 0, stagger: 0.15, duration: 0.5 });
    },
    'liquid-button-morph': (container) => {
      const path = container.querySelector('.ga-liq-path');
      const wrap = container.querySelector('.ga-liquid-btn-wrap');
      const normal = 'M10,5 H190 Q195,5 195,10 V50 Q195,55 190,55 H10 Q5,55 5,50 V10 Q5,5 10,5 Z';
      const hover = 'M15,2 H185 Q198,8 195,15 V45 Q192,58 185,58 H15 Q2,52 5,45 V15 Q8,-2 15,2 Z';
      wrap.addEventListener('mouseenter', () => {
        gsap.to(path, { attr: { d: hover }, duration: 0.4, ease: 'elastic.out(1, 0.5)' });
      });
      wrap.addEventListener('mouseleave', () => {
        gsap.to(path, { attr: { d: normal }, duration: 0.4, ease: 'elastic.out(1, 0.5)' });
      });
      return gsap.from(wrap, { opacity: 0, scale: 0.8, duration: 0.5 });
    },
    'mood-face-morph': (container) => {
      const mouth = container.querySelector('.ga-mouth');
      const eyeL = container.querySelector('.ga-eye-l');
      const eyeR = container.querySelector('.ga-eye-r');
      const moods = [
        { mouth: 'M60,130 Q100,160 140,130', eyeR: 8, eyeL: 8 }, // happy
        { mouth: 'M60,140 Q100,120 140,140', eyeR: 8, eyeL: 8 }, // sad
        { mouth: 'M80,135 Q100,135 120,135', eyeR: 10, eyeL: 10 }, // surprised
        { mouth: 'M60,130 Q100,160 140,130', eyeR: 8, eyeL: 8 }, // back to happy
      ];
      let idx = 0;
      container.querySelector('.ga-face-svg').addEventListener('click', () => {
        idx = (idx + 1) % moods.length;
        const m = moods[idx];
        gsap.to(mouth, { attr: { d: m.mouth }, duration: 0.5, ease: 'power2.inOut' });
        gsap.to(eyeL, { attr: { r: m.eyeL }, duration: 0.3 });
        gsap.to(eyeR, { attr: { r: m.eyeR }, duration: 0.3 });
      });
      return gsap.from(container.querySelector('.ga-face-svg'), { opacity: 0, scale: 0.8, duration: 0.5 });
    },
    'animal-silhouette': (container) => {
      const path = container.querySelector('.ga-animal-path');
      const animals = [
        'M30,140 Q30,100 50,80 Q70,60 70,40 Q70,20 90,20 Q110,20 110,40 L110,50 Q130,30 150,40 Q170,50 170,80 Q170,110 150,120 L140,140 Z', // cat
        'M30,140 L30,100 Q40,60 70,50 L90,40 Q110,30 130,40 L160,60 Q180,80 170,110 L170,140 Q140,120 100,120 Q60,120 30,140 Z', // fish
        'M40,140 Q30,110 50,90 Q40,70 60,60 L80,50 Q100,40 120,50 L150,70 Q170,80 160,100 L170,140 Q120,130 80,130 Z', // bird
      ];
      let idx = 0;
      const tl = gsap.timeline({ repeat: -1, repeatDelay: 1 });
      animals.forEach((a, i) => {
        tl.to(path, { attr: { d: a }, duration: 1.2, ease: 'power2.inOut' }, i * 2);
      });
      return tl;
    },
    'day-night-scene': (container) => {
      const sky = container.querySelector('.ga-sky');
      const hills = container.querySelector('.ga-hills');
      const sun = container.querySelector('.ga-sun-moon');
      const tl = gsap.timeline({ yoyo: true, repeat: 1 });
      tl.to(sky, { fill: '#1a1a3e', duration: 2, ease: 'power2.inOut' }, 0)
        .to(hills, { fill: '#0a3d0a', duration: 2, ease: 'power2.inOut' }, 0)
        .to(sun, { fill: '#E8E8E8', attr: { cx: 60, cy: 40 }, duration: 2, ease: 'power2.inOut' }, 0);
      return tl;
    },
    'gooey-menu': (container) => {
      const links = container.querySelectorAll('.ga-gooey-link');
      const blob = container.querySelector('.ga-gooey-blob');
      const nav = container.querySelector('.ga-gooey-nav');
      function moveBlob(target) {
        const navRect = nav.getBoundingClientRect();
        const rect = target.getBoundingClientRect();
        gsap.to(blob, {
          left: rect.left - navRect.left - 8,
          width: rect.width + 16,
          duration: 0.4, ease: 'power2.out'
        });
      }
      links.forEach(link => {
        link.addEventListener('mouseenter', () => moveBlob(link));
        link.addEventListener('click', () => {
          links.forEach(l => l.classList.remove('active'));
          link.classList.add('active');
        });
      });
      nav.addEventListener('mouseleave', () => {
        const active = nav.querySelector('.ga-gooey-link.active');
        if (active) moveBlob(active);
      });
      // Init blob position
      requestAnimationFrame(() => {
        const active = nav.querySelector('.ga-gooey-link.active');
        if (active && blob) moveBlob(active);
      });
      return gsap.from(links, { opacity: 0, y: 10, stagger: 0.1, duration: 0.4 });
    },

    /* ══════════════════════════════
       7. LINE DRAWING
       ══════════════════════════════ */
    'blueprint-reveal': (container) => {
      const lines = container.querySelectorAll('.ga-bp-line');
      const tl = gsap.timeline();
      lines.forEach(line => {
        const len = line.tagName === 'line' ? Math.sqrt(Math.pow(line.x2.baseVal.value - line.x1.baseVal.value, 2) + Math.pow(line.y2.baseVal.value - line.y1.baseVal.value, 2)) : (line.width.baseVal.value + line.height.baseVal.value) * 2;
        gsap.set(line, { strokeDasharray: len, strokeDashoffset: len });
        tl.to(line, { strokeDashoffset: 0, duration: 0.8, ease: 'power2.inOut' }, tl.duration() * 0.6);
      });
      return tl;
    },
    'constellation-connect': (container) => {
      const stars = container.querySelectorAll('.ga-star');
      const conns = container.querySelectorAll('.ga-conn');
      const tl = gsap.timeline();
      // Stars appear
      tl.to(stars, { opacity: 1, scale: 1.5, duration: 0.3, stagger: 0.1 });
      tl.to(stars, { scale: 1, duration: 0.2, stagger: 0.1 }, '-=0.3');
      // Lines draw
      conns.forEach(conn => {
        const len = Math.sqrt(
          Math.pow(conn.x2.baseVal.value - conn.x1.baseVal.value, 2) +
          Math.pow(conn.y2.baseVal.value - conn.y1.baseVal.value, 2)
        );
        gsap.set(conn, { strokeDasharray: len, strokeDashoffset: len });
        tl.to(conn, { strokeDashoffset: 0, duration: 0.6, ease: 'power2.inOut' }, '-=0.3');
      });
      return tl;
    },
    'signature-draw': (container) => {
      const path = container.querySelector('.ga-sig-path');
      const len = path.getTotalLength();
      gsap.set(path, { strokeDasharray: len, strokeDashoffset: len });
      return gsap.to(path, { strokeDashoffset: 0, duration: 2, ease: 'power1.inOut' });
    },
    'circuit-trace': (container) => {
      const traces = container.querySelectorAll('.ga-trace');
      const nodes = container.querySelectorAll('.ga-node');
      const tl = gsap.timeline();
      traces.forEach(trace => {
        const len = trace.getTotalLength();
        gsap.set(trace, { strokeDasharray: len, strokeDashoffset: len });
        tl.to(trace, { strokeDashoffset: 0, duration: 1.2, ease: 'none' }, tl.duration() * 0.5);
      });
      tl.from(nodes, { opacity: 0, scale: 0, stagger: 0.15, duration: 0.3, ease: 'back.out(2)' }, '-=0.5');
      return tl;
    },
    'animated-infographic': (container) => {
      const line = container.querySelector('.ga-chart-line');
      const dots = container.querySelectorAll('.ga-chart-dot');
      const tl = gsap.timeline();
      const len = line.getTotalLength();
      gsap.set(line, { strokeDasharray: len, strokeDashoffset: len });
      tl.to(line, { strokeDashoffset: 0, duration: 1.5, ease: 'power2.inOut' });
      tl.to(dots, { opacity: 1, scale: 1.3, stagger: 0.1, duration: 0.3 }, '-=0.8');
      tl.to(dots, { scale: 1, stagger: 0.1, duration: 0.2 }, '-=0.3');
      return tl;
    },

    /* ══════════════════════════════
       8. MOTION PATHS
       ══════════════════════════════ */
    'satellite-orbit': (container) => {
      const sat = container.querySelector('.ga-satellite');
      const tl = gsap.timeline({ repeat: -1 });
      // Manual orbit
      tl.to(sat, {
        duration: 3, ease: 'none', repeat: -1,
        motionPath: {
          path: [
            { x: 90, y: -50 }, { x: 0, y: -50 }, { x: -90, y: 50 }, { x: 0, y: 50 }, { x: 90, y: -50 }
          ],
          curviness: 1.5
        }
      });
      return tl;
    },
    'conveyor-belt': (container) => {
      const items = container.querySelectorAll('.ga-belt-item');
      const tl = gsap.timeline();
      items.forEach((item, i) => {
        tl.to(item, {
          duration: 2.5, ease: 'none',
          motionPath: {
            path: '#belt-path',
            align: '#belt-path',
            alignOrigin: [0.5, 0.5],
            autoRotate: true
          }
        }, i * 0.8);
      });
      return tl;
    },
    'scroll-path-journey': (container) => {
      const dot = container.querySelector('.ga-journey-dot');
      const trail = container.querySelector('.ga-journey-trail');
      const len = trail.getTotalLength();
      gsap.set(trail, { strokeDasharray: len, strokeDashoffset: len });
      const tl = gsap.timeline();
      tl.to(trail, { strokeDashoffset: 0, duration: 2, ease: 'none' }, 0);
      tl.to(dot, {
        duration: 2, ease: 'none',
        motionPath: { path: '.ga-journey-trail', align: '.ga-journey-trail', alignOrigin: [0.5, 0.5] }
      }, 0);
      return tl;
    },
    'dna-helix': (container) => {
      const cont = container.querySelector('.ga-dna-container');
      if (!cont) return gsap.timeline();
      // Create DNA nodes dynamically
      cont.innerHTML = '';
      const nodes = 10;
      for (let i = 0; i < nodes; i++) {
        const a = document.createElement('div');
        a.className = 'ga-dna-strand ga-dna-a';
        a.style.top = (i * 18) + 'px';
        const b = document.createElement('div');
        b.className = 'ga-dna-strand ga-dna-b';
        b.style.top = (i * 18) + 'px';
        b.style.background = 'var(--gs-secondary)';
        cont.appendChild(a);
        cont.appendChild(b);
      }
      const strandsA = cont.querySelectorAll('.ga-dna-a');
      const strandsB = cont.querySelectorAll('.ga-dna-b');
      const tl = gsap.timeline({ repeat: -1 });
      strandsA.forEach((s, i) => {
        tl.to(s, { x: Math.sin(i * 0.6) * 30, duration: 2, ease: 'sine.inOut', yoyo: true, repeat: -1 }, i * 0.1);
      });
      strandsB.forEach((s, i) => {
        tl.to(s, { x: Math.sin(i * 0.6 + Math.PI) * 30, duration: 2, ease: 'sine.inOut', yoyo: true, repeat: -1 }, i * 0.1);
      });
      return tl;
    },
    'rollercoaster-stats': (container) => {
      const cart = container.querySelector('.ga-coaster-cart');
      const trail = container.querySelector('.ga-coaster-trail');
      if (!trail || !cart) return gsap.timeline();
      const len = trail.getTotalLength();
      gsap.set(trail, { strokeDasharray: len, strokeDashoffset: len });
      const tl = gsap.timeline();
      tl.to(trail, { strokeDashoffset: 0, duration: 2.5, ease: 'none' }, 0);
      tl.to(cart, {
        duration: 2.5, ease: 'none',
        motionPath: { path: '.ga-coaster-trail', align: '.ga-coaster-trail', alignOrigin: [0.5, 0.5] }
      }, 0);
      return tl;
    },

    /* ══════════════════════════════
       9. PHYSICS & PARTICLES
       ══════════════════════════════ */
    'confetti-cannon': (container) => {
      const area = container.querySelector('.ga-confetti-area');
      const btn = container.querySelector('.ga-confetti-trigger');
      const fire = () => {
        const colors = ['#00FF66', '#00CC88', '#00AA77', '#ffffff', '#00FF66'];
        for (let i = 0; i < 30; i++) {
          const piece = document.createElement('div');
          piece.className = 'ga-confetti-piece';
          piece.style.background = colors[Math.floor(Math.random() * colors.length)];
          piece.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px';
          piece.style.width = gsap.utils.random(6, 12) + 'px';
          piece.style.height = gsap.utils.random(6, 12) + 'px';
          piece.style.left = '50%'; piece.style.bottom = '40%';
          area.appendChild(piece);
          gsap.to(piece, {
            x: gsap.utils.random(-180, 180),
            y: gsap.utils.random(-200, -50),
            rotation: gsap.utils.random(-360, 360),
            duration: gsap.utils.random(0.6, 1.2),
            ease: 'power2.out'
          });
          gsap.to(piece, {
            y: 200, duration: gsap.utils.random(0.8, 1.5),
            delay: gsap.utils.random(0.4, 0.8),
            ease: 'power2.in',
            onComplete: () => piece.remove()
          });
        }
      };
      btn.addEventListener('click', fire);
      return gsap.from(btn, { opacity: 0, scale: 0.8, duration: 0.5 });
    },
    'gravity-card-drop': (container) => {
      const area = container.querySelector('.ga-gravity-area');
      const colors = ['var(--gs-primary)', 'var(--gs-secondary)', '#00AA77'];
      const tl = gsap.timeline();
      for (let i = 0; i < 5; i++) {
        const card = document.createElement('div');
        card.className = 'ga-gravity-card';
        card.style.background = colors[i % colors.length];
        card.style.left = (15 + i * 17) + '%';
        area.appendChild(card);
        tl.fromTo(card, { y: -80, rotation: gsap.utils.random(-20, 20) },
          { y: area.offsetHeight - 60, rotation: gsap.utils.random(-5, 5), duration: 1, ease: 'bounce.out' }, i * 0.2);
      }
      return tl;
    },
    'magnetic-repel': (container) => {
      const grid = container.querySelector('.ga-repel-grid');
      grid.innerHTML = '';
      const dots = [];
      for (let i = 0; i < 48; i++) {
        const dot = document.createElement('div');
        dot.className = 'ga-repel-dot';
        grid.appendChild(dot);
        dots.push(dot);
      }
      const preview = container.closest('.ga-preview');
      preview.addEventListener('mousemove', (e) => {
        const rect = preview.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        dots.forEach(dot => {
          const dr = dot.getBoundingClientRect();
          const dx = (dr.left + dr.width / 2 - rect.left) - mx;
          const dy = (dr.top + dr.height / 2 - rect.top) - my;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 80) {
            const force = (80 - dist) / 80;
            gsap.to(dot, { x: dx * force * 0.5, y: dy * force * 0.5, scale: 1 + force, duration: 0.3 });
          } else {
            gsap.to(dot, { x: 0, y: 0, scale: 1, duration: 0.5 });
          }
        });
      });
      preview.addEventListener('mouseleave', () => {
        dots.forEach(dot => gsap.to(dot, { x: 0, y: 0, scale: 1, duration: 0.5 }));
      });
      return gsap.from(dots, { opacity: 0, stagger: 0.01, duration: 0.3 });
    },
    'throw-and-snap': (container) => {
      const ball = container.querySelector('.ga-snap-ball');
      if (ball && typeof Draggable !== 'undefined') {
        Draggable.create(ball, {
          bounds: container.closest('.ga-preview'),
          inertia: true,
          onRelease: function() {
            gsap.to(ball, { x: 0, y: 0, duration: 0.8, ease: 'elastic.out(1, 0.4)' });
          }
        });
      }
      return gsap.from(ball, { opacity: 0, scale: 0, duration: 0.5 });
    },
    'popcorn-loader': (container) => {
      const kernels = container.querySelectorAll('.ga-popcorn-kernel');
      const tl = gsap.timeline({ repeat: 2 });
      kernels.forEach((k, i) => {
        tl.to(k, { y: gsap.utils.random(-80, -40), scale: 1.3, duration: 0.3, ease: 'power2.out' }, i * 0.15)
          .to(k, { y: 0, scale: 1, duration: 0.4, ease: 'bounce.out' }, i * 0.15 + 0.3);
      });
      return tl;
    },
    'jelly-button': (container) => {
      const btn = container.querySelector('.ga-jelly-btn');
      btn.addEventListener('click', () => {
        gsap.timeline()
          .to(btn, { scaleX: 1.2, scaleY: 0.8, duration: 0.1 })
          .to(btn, { scaleX: 0.9, scaleY: 1.1, duration: 0.1 })
          .to(btn, { scaleX: 1.05, scaleY: 0.95, duration: 0.1 })
          .to(btn, { scaleX: 1, scaleY: 1, duration: 0.3, ease: 'elastic.out(1, 0.4)' });
      });
      return gsap.from(btn, { opacity: 0, scale: 0.5, duration: 0.5 });
    },
    'notification-shake': (container) => {
      const el = container.querySelector('.ga-notification');
      const tl = gsap.timeline();
      tl.to(el, { x: -10, duration: 0.05 })
        .to(el, { x: 10, duration: 0.05 })
        .to(el, { x: -8, duration: 0.05 })
        .to(el, { x: 8, duration: 0.05 })
        .to(el, { x: -5, duration: 0.05 })
        .to(el, { x: 5, duration: 0.05 })
        .to(el, { x: -2, duration: 0.05 })
        .to(el, { x: 0, duration: 0.1 });
      return tl;
    },
    'wobble-card-enter': (container) => {
      const cards = container.querySelectorAll('.ga-wobble-card');
      return gsap.from(cards, {
        opacity: 0, y: 50, rotation: gsap.utils.random(-15, 15),
        duration: 0.8, stagger: 0.15, ease: 'elastic.out(1, 0.5)'
      });
    },
    'springboard-menu': (container) => {
      const items = container.querySelectorAll('.ga-spring-item');
      return gsap.from(items, {
        opacity: 0, x: -60,
        duration: 0.6, stagger: 0.1, ease: 'back.out(1.7)'
      });
    },
    'newtons-cradle': (container) => {
      const balls = container.querySelectorAll('.ga-cradle-ball');
      if (balls.length < 5) return gsap.timeline();
      const first = balls[0], last = balls[4];
      const tl = gsap.timeline({ repeat: 3 });
      tl.to(first, { rotation: -30, duration: 0.3, ease: 'power2.in', transformOrigin: 'center -40px' })
        .to(first, { rotation: 0, duration: 0.3, ease: 'power2.out' })
        .to(last, { rotation: 30, duration: 0.3, ease: 'power2.out' }, '-=0.05')
        .to(last, { rotation: 0, duration: 0.3, ease: 'power2.in' })
        .to(first, { rotation: -25, duration: 0.3, ease: 'power2.out' }, '-=0.05');
      return tl;
    },

    /* ══════════════════════════════
       10. CAROUSELS & SLIDERS
       ══════════════════════════════ */
    'infinite-loop': (container) => {
      const track = container.querySelector('.ga-inf-track');
      if (!track) return gsap.timeline();
      // Clone items for seamless loop
      const items = track.querySelectorAll('.ga-inf-item');
      items.forEach(item => track.appendChild(item.cloneNode(true)));
      const totalWidth = track.scrollWidth / 2;
      return gsap.to(track, { x: -totalWidth, duration: 8, ease: 'none', repeat: -1 });
    },
    'coverflow-3d': (container) => {
      const items = container.querySelectorAll('.ga-cov-item');
      let current = 2;
      const update = () => {
        items.forEach((item, i) => {
          const offset = i - current;
          item.classList.toggle('active', i === current);
          gsap.to(item, {
            rotateY: offset * -30,
            z: offset === 0 ? 50 : -Math.abs(offset) * 30,
            opacity: Math.abs(offset) > 1 ? 0.3 : 1,
            scale: offset === 0 ? 1.2 : 0.85,
            duration: 0.5, ease: 'power2.out'
          });
        });
      };
      container.querySelector('.ga-cov-prev')?.addEventListener('click', () => { current = Math.max(0, current - 1); update(); });
      container.querySelector('.ga-cov-next')?.addEventListener('click', () => { current = Math.min(items.length - 1, current + 1); update(); });
      update();
      return gsap.from(items, { opacity: 0, scale: 0.5, stagger: 0.1, duration: 0.5 });
    },
    'draggable-carousel': (container) => {
      const carousel = container.querySelector('.ga-drag-carousel');
      if (carousel && typeof Draggable !== 'undefined') {
        Draggable.create(carousel, {
          type: 'x',
          bounds: { minX: -(carousel.scrollWidth - carousel.parentElement.offsetWidth), maxX: 0 },
          inertia: true,
          edgeResistance: 0.85
        });
      }
      return gsap.from(carousel, { opacity: 0, x: 50, duration: 0.5 });
    },
    'vertical-card-stack': (container) => {
      const cards = container.querySelectorAll('.ga-vstack-card');
      cards.forEach((c, i) => {
        gsap.set(c, { y: -i * 5, scale: 1 - i * 0.05, zIndex: cards.length - i });
      });
      const stack = container.querySelector('.ga-vstack');
      let topIdx = 0;
      stack.addEventListener('click', () => {
        const top = cards[topIdx];
        gsap.to(top, {
          y: 120, opacity: 0, rotation: 10,
          duration: 0.4, ease: 'power2.in',
          onComplete: () => {
            gsap.set(top, { y: -(cards.length - 1) * 5, opacity: 1, rotation: 0, zIndex: 0 });
            cards.forEach((c, i) => {
              const idx = (i - topIdx - 1 + cards.length) % cards.length;
              gsap.to(c, { y: -idx * 5, scale: 1 - idx * 0.05, zIndex: cards.length - idx, duration: 0.3 });
            });
            topIdx = (topIdx + 1) % cards.length;
          }
        });
      });
      return gsap.from(cards, { opacity: 0, y: -50, stagger: 0.1, duration: 0.4 });
    },
    'parallax-slider': (container) => {
      const slides = container.querySelectorAll('.ga-par-slide');
      let current = 0;
      const go = (dir) => {
        const prev = current;
        current = (current + dir + slides.length) % slides.length;
        const tl = gsap.timeline();
        tl.to(slides[prev].querySelector('.ga-par-bg'), { x: dir * -50, duration: 0.5 });
        tl.to(slides[prev], { opacity: 0, duration: 0.3 }, 0);
        slides[current].classList.add('active');
        gsap.set(slides[current].querySelector('.ga-par-bg'), { x: dir * 50 });
        tl.to(slides[current], { opacity: 1, duration: 0.3 }, 0.2);
        tl.to(slides[current].querySelector('.ga-par-bg'), { x: 0, duration: 0.5 }, 0.2);
        tl.add(() => { slides[prev].classList.remove('active'); });
      };
      container.querySelector('.ga-par-prev')?.addEventListener('click', () => go(-1));
      container.querySelector('.ga-par-next')?.addEventListener('click', () => go(1));
      return gsap.from(slides[0], { opacity: 0, duration: 0.5 });
    },

    /* ══════════════════════════════
       11. LOADERS & TRANSITIONS
       ══════════════════════════════ */
    'staggered-blinds': (container) => {
      const blinds = container.querySelectorAll('.ga-blind');
      return gsap.to(blinds, { scaleX: 0, duration: 0.6, stagger: { amount: 0.4, from: 'edges' }, ease: 'power2.inOut' });
    },
    'counter-preloader': (container) => {
      const num = container.querySelector('.ga-preload-num');
      const fill = container.querySelector('.ga-preload-fill');
      const obj = { val: 0 };
      const tl = gsap.timeline();
      tl.to(obj, {
        val: 100, duration: 2.5, ease: 'power2.inOut',
        onUpdate: () => {
          num.textContent = Math.round(obj.val) + '%';
          fill.style.width = obj.val + '%';
        }
      });
      return tl;
    },
    'circle-wipe': (container) => {
      const circle = container.querySelector('.ga-wipe-circle');
      const tl = gsap.timeline();
      tl.to(circle, { width: 400, height: 400, duration: 0.8, ease: 'power2.in' })
        .set(container.querySelector('.ga-wipe-old'), { opacity: 0 })
        .to(circle, { width: 0, height: 0, duration: 0.6, ease: 'power2.out' });
      return tl;
    },
    'skeleton-to-content': (container) => {
      const lines = container.querySelectorAll('.ga-skel-line');
      const tl = gsap.timeline({ delay: 1 });
      tl.to(lines, { background: 'rgba(0,255,102,0.15)', backgroundImage: 'none', stagger: 0.1, duration: 0.3 })
        .to(lines, { scaleX: 1, borderRadius: 4, duration: 0.3 });
      return tl;
    },

    /* ══════════════════════════════
       12. COUNTERS & DATA VIZ
       ══════════════════════════════ */
    'count-up': (container) => {
      const counters = container.querySelectorAll('.ga-counter');
      const tl = gsap.timeline();
      counters.forEach(counter => {
        const target = parseInt(counter.dataset.target);
        const obj = { val: 0 };
        tl.to(obj, {
          val: target, duration: 2, ease: 'power2.out',
          onUpdate: () => { counter.textContent = Math.round(obj.val).toLocaleString(); }
        }, 0);
      });
      return tl;
    },
    'odometer': (container) => {
      const digits = container.querySelectorAll('.ga-odo-digit');
      const tl = gsap.timeline();
      digits.forEach(digit => {
        const target = parseInt(digit.dataset.target);
        const strip = digit.querySelector('.ga-odo-strip');
        tl.to(strip, { y: -target * 60, duration: 1.5 + target * 0.1, ease: 'power2.out' }, 0);
      });
      return tl;
    },
    'circular-progress': (container) => {
      const rings = container.querySelectorAll('.ga-ring-fill');
      const tl = gsap.timeline();
      rings.forEach(ring => {
        const target = parseInt(ring.dataset.target);
        const circumference = 2 * Math.PI * 52;
        gsap.set(ring, { strokeDasharray: circumference, strokeDashoffset: circumference });
        tl.to(ring, { strokeDashoffset: circumference * (1 - target / 100), duration: 1.5, ease: 'power2.out' }, 0);
      });
      return tl;
    },
    'animated-bar-chart': (container) => {
      const bars = container.querySelectorAll('.ga-bar');
      const tl = gsap.timeline();
      bars.forEach(bar => {
        const height = parseInt(bar.dataset.height);
        const fill = bar.querySelector('.ga-bar-fill');
        tl.to(fill, { height: height + '%', duration: 0.8, ease: 'power2.out' }, tl.duration() * 0.5);
      });
      return tl;
    },

    /* ══════════════════════════════
       13. BACKGROUNDS & ATMOSPHERE
       ══════════════════════════════ */
    'animated-gradient': (container) => {
      const bg = container.querySelector('.ga-gradient-bg');
      return gsap.to(bg, { backgroundPosition: '100% 100%', duration: 4, ease: 'sine.inOut', yoyo: true, repeat: 2 });
    },
    'particle-float': (container) => {
      const field = container.querySelector('.ga-particle-field');
      for (let i = 0; i < 20; i++) {
        const p = document.createElement('div');
        p.className = 'ga-particle';
        p.style.left = gsap.utils.random(5, 95) + '%';
        p.style.top = gsap.utils.random(70, 100) + '%';
        field.appendChild(p);
        gsap.to(p, {
          y: gsap.utils.random(-150, -50),
          x: gsap.utils.random(-30, 30),
          opacity: 0,
          duration: gsap.utils.random(3, 6),
          ease: 'none', repeat: -1,
          delay: gsap.utils.random(0, 3)
        });
      }
      return gsap.timeline();
    },
    'cursor-spotlight': (container) => {
      const area = container.querySelector('.ga-spotlight-area');
      const light = container.querySelector('.ga-spotlight-light');
      area.addEventListener('mouseenter', () => { light.style.display = 'block'; });
      area.addEventListener('mouseleave', () => { light.style.display = 'none'; });
      area.addEventListener('mousemove', (e) => {
        const rect = area.getBoundingClientRect();
        gsap.to(light, { left: e.clientX - rect.left, top: e.clientY - rect.top, duration: 0.2 });
      });
      return gsap.from(area.querySelector('.ga-spotlight-text'), { opacity: 0, duration: 0.5 });
    },

    /* ══════════════════════════════
       14. MULTI-PLUGIN SHOWCASES
       ══════════════════════════════ */
    'particle-text': (container) => {
      const canvas = container.querySelector('.ga-particle-canvas');
      if (!canvas) return gsap.timeline();
      const ctx = canvas.getContext('2d');
      const w = canvas.parentElement.offsetWidth;
      const h = canvas.parentElement.offsetHeight;
      canvas.width = w; canvas.height = h;
      // Draw text to get pixel data
      ctx.fillStyle = '#00FF66';
      ctx.font = 'bold 48px Schibsted Grotesk';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('GSAP', w / 2, h / 2);
      const imageData = ctx.getImageData(0, 0, w, h);
      const particles = [];
      for (let y = 0; y < h; y += 4) {
        for (let x = 0; x < w; x += 4) {
          if (imageData.data[(y * w + x) * 4 + 3] > 128) {
            particles.push({ x, y, originX: x, originY: y });
          }
        }
      }
      function draw() {
        ctx.clearRect(0, 0, w, h);
        particles.forEach(p => {
          ctx.fillStyle = `rgba(0,255,102,${0.8})`;
          ctx.fillRect(p.x, p.y, 2, 2);
        });
        requestAnimationFrame(draw);
      }
      draw();
      // Mouse interaction
      const preview = container.closest('.ga-preview');
      preview.addEventListener('mousemove', (e) => {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        particles.forEach(p => {
          const dx = p.x - mx, dy = p.y - my;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 50) {
            p.x += dx * 0.3;
            p.y += dy * 0.3;
          } else {
            p.x += (p.originX - p.x) * 0.1;
            p.y += (p.originY - p.y) * 0.1;
          }
        });
      });
      return gsap.timeline();
    },
    'scroll-storyteller': (container) => {
      const line = container.querySelector('.ga-story-line');
      const shape = container.querySelector('.ga-story-shape');
      const dot = container.querySelector('.ga-story-dot');
      const text = container.querySelector('.ga-story-text');
      const tl = gsap.timeline();
      if (line) {
        const len = line.getTotalLength();
        gsap.set(line, { strokeDasharray: len, strokeDashoffset: len });
        tl.to(line, { strokeDashoffset: 0, duration: 2, ease: 'power2.inOut' });
      }
      if (dot) tl.from(dot, { scale: 0, duration: 0.5, ease: 'back.out(2)' }, '-=0.5');
      if (shape) tl.from(shape, { scale: 0, rotation: 180, duration: 0.8, ease: 'back.out(1.7)', transformOrigin: 'center' }, '-=0.3');
      if (text) {
        const orig = text.textContent;
        const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
        tl.to(text, {
          duration: 1.5, ease: 'none',
          onUpdate: function() {
            const p = this.progress();
            const len = orig.length;
            const revealed = Math.floor(p * len);
            let str = '';
            for (let i = 0; i < len; i++) {
              str += (i < revealed) ? orig[i] : chars[Math.floor(Math.random() * chars.length)];
            }
            text.textContent = str;
          },
          onComplete: () => { text.textContent = orig; }
        }, '-=1');
      }
      return tl;
    },
    'gravity-form': (container) => {
      const inputs = container.querySelectorAll('.ga-grav-input');
      const submit = container.querySelector('.ga-grav-submit');
      const tl = gsap.timeline();
      inputs.forEach((input, i) => {
        tl.from(input, { y: -200, opacity: 0, duration: 0.8, ease: 'bounce.out' }, i * 0.3);
      });
      if (submit) {
        tl.from(submit, { y: -200, opacity: 0, duration: 0.8, ease: 'bounce.out' }, inputs.length * 0.3);
      }
      return tl;
    },

    /* 97 — Ken Burns Slideshow */
    'ken-burns-slideshow': (container) => {
      const slides = container.querySelectorAll('.ga-kb-slide');
      if (!slides.length) return gsap.timeline();
      const tl = gsap.timeline({ repeat: -1 });
      slides.forEach((slide, i) => {
        const dir = i % 2 === 0 ? 1.15 : 1.05;
        const xFrom = i % 2 === 0 ? '-5%' : '5%';
        tl.fromTo(slide, { opacity: 0, scale: 1, x: xFrom }, { opacity: 1, scale: dir, x: '0%', duration: 2, ease: 'power1.inOut' }, i * 3)
          .to(slide, { opacity: 0, duration: 1, ease: 'power1.in' }, i * 3 + 2.5);
      });
      return tl;
    },

    /* 98 — Curtain Reveal */
    'curtain-reveal': (container) => {
      const left = container.querySelector('.ga-curtain-left');
      const right = container.querySelector('.ga-curtain-right');
      const content = container.querySelector('.ga-curtain-content');
      const tl = gsap.timeline();
      if (left && right) {
        tl.to(left, { xPercent: -100, duration: 1, ease: 'power3.inOut' }, 0)
          .to(right, { xPercent: 100, duration: 1, ease: 'power3.inOut' }, 0);
      }
      if (content) {
        tl.from(content, { scale: 0.5, opacity: 0, duration: 0.6, ease: 'back.out(1.7)' }, 0.5);
      }
      return tl;
    },

    /* 99 — Aurora Borealis Waves */
    'aurora-waves': (container) => {
      const waves = container.querySelectorAll('.ga-aurora-wave');
      const tl = gsap.timeline({ repeat: -1, yoyo: true });
      waves.forEach((wave, i) => {
        tl.to(wave, {
          y: -20 + (i * 10), x: 30 - (i * 15), scaleX: 1.2 + (i * 0.1), opacity: 0.3 + (i * 0.15),
          duration: 3 + i, ease: 'sine.inOut'
        }, 0);
      });
      return tl;
    },

    /* 100 — Timeline Scroll Experience */
    'timeline-scroll-experience': (container) => {
      const line = container.querySelector('.ga-tl-line');
      const milestones = container.querySelectorAll('.ga-tl-milestone');
      const tl = gsap.timeline();
      if (line) {
        tl.from(line, { scaleY: 0, transformOrigin: 'top center', duration: 1.2, ease: 'power2.inOut' });
      }
      milestones.forEach((ms, i) => {
        const dot = ms.querySelector('.ga-tl-dot');
        if (dot) {
          tl.from(dot, { scale: 0, opacity: 0, duration: 0.4, ease: 'back.out(2)' }, 0.3 + i * 0.35);
        }
        tl.from(ms, { x: i % 2 === 0 ? -30 : 30, opacity: 0, duration: 0.5, ease: 'power2.out' }, 0.4 + i * 0.35);
      });
      return tl;
    },
  };

  /* ═══════════════════════════════════════════
     CODE SNIPPETS (for copy button)
     ═══════════════════════════════════════════ */
  const codeSnippets = {
    'stagger-letter-reveal': `// Split text into characters\nconst chars = SplitText.create(".text", { type: "chars" });\ngsap.from(chars.chars, {\n  opacity: 0, y: 30,\n  duration: 0.5, stagger: 0.03,\n  ease: "back.out(1.7)"\n});`,
    'typewriter': `gsap.to(".target", {\n  text: { value: "Hello, World!" },\n  duration: 2,\n  ease: "none"\n});`,
    'text-scramble': `gsap.to(".text", {\n  scrambleText: {\n    text: "Final Text",\n    chars: "ABCDEFGHIJKLMNOPQRSTUVWXYZ",\n    speed: 0.4\n  },\n  duration: 1.5\n});`,
    'word-by-word-slide': `const words = SplitText.create(".text", { type: "words" });\ngsap.from(words.words, {\n  opacity: 0, y: 40, rotation: 5,\n  duration: 0.6, stagger: 0.1,\n  ease: "power3.out"\n});`,
    'kinetic-split-lines': `const lines = SplitText.create(".text", { type: "lines" });\nlines.lines.forEach((line, i) => {\n  gsap.from(line, {\n    x: i % 2 === 0 ? -100 : 100,\n    opacity: 0, duration: 0.7,\n    ease: "power3.out",\n    scrollTrigger: line\n  });\n});`,
    'letter-3d-flip': `const chars = SplitText.create(".text", { type: "chars" });\ngsap.from(chars.chars, {\n  rotationY: -90, opacity: 0,\n  duration: 0.6, stagger: 0.05,\n  ease: "back.out(1.4)",\n  transformOrigin: "50% 50% -20px"\n});`,
    'gradient-text-reveal': `gsap.fromTo(".gradient-text",\n  { backgroundPosition: "200% 0" },\n  { backgroundPosition: "0% 0",\n    duration: 2, ease: "power2.inOut" }\n);`,
    'glitch-text': `// Add CSS for ::before/::after pseudo-elements\n// with clip-path keyframe animations\ngsap.to(".glitch", {\n  x: -3, duration: 0.05, yoyo: true,\n  repeat: 5, ease: "none"\n});`,
    'matrix-decode': `gsap.to(".text", {\n  scrambleText: {\n    text: "SYSTEM ONLINE",\n    chars: "ﾊﾐﾋｰｳｼﾅﾓﾆｻ012345789",\n    speed: 0.3\n  },\n  duration: 2.5\n});`,
    'encryption-viz': `const tl = gsap.timeline();\ntl.to(".text", {\n  scrambleText: { text: "§¶•†‡ÆØÅ", speed: 0.5 },\n  duration: 1\n})\n.to(".text", {\n  scrambleText: { text: "Original Text", speed: 0.3 },\n  duration: 1, delay: 0.8\n});`,
    'per-char-physics': `const chars = SplitText.create(".text", { type: "chars" });\nchars.chars.forEach(ch => {\n  gsap.from(ch, {\n    y: -200, opacity: 0,\n    duration: 0.8, ease: "bounce.out",\n    delay: Math.random() * 0.5\n  });\n});`,
    'liquid-text-wave': `const chars = SplitText.create(".text", { type: "chars" });\nchars.chars.forEach((ch, i) => {\n  gsap.to(ch, {\n    y: -15, duration: 0.3,\n    ease: "sine.inOut",\n    yoyo: true, repeat: -1,\n    delay: i * 0.05\n  });\n});`,
    'fade-up-scroll': `gsap.from(".element", {\n  opacity: 0, y: 40,\n  duration: 0.6,\n  scrollTrigger: {\n    trigger: ".element",\n    start: "top 80%"\n  }\n});`,
    'parallax-layers': `gsap.to(".layer", {\n  yPercent: -50,\n  ease: "none",\n  scrollTrigger: {\n    trigger: ".section",\n    scrub: true\n  }\n});`,
    'horizontal-scroll': `gsap.to(".panels", {\n  xPercent: -100 * (panels.length - 1),\n  ease: "none",\n  scrollTrigger: {\n    trigger: ".container",\n    pin: true,\n    scrub: 1,\n    end: () => "+=" + container.offsetWidth\n  }\n});`,
    'scroll-scrub': `gsap.to(".element", {\n  rotation: 360,\n  scrollTrigger: {\n    trigger: ".section",\n    scrub: true,\n    start: "top center",\n    end: "bottom center"\n  }\n});`,
    'staggered-grid-reveal': `gsap.from(".grid-item", {\n  scale: 0, opacity: 0,\n  duration: 0.4,\n  stagger: { amount: 0.6, from: "center" },\n  ease: "back.out(1.7)",\n  scrollTrigger: ".grid"\n});`,
    'scroll-velocity-skew': `ScrollTrigger.create({\n  onUpdate: (self) => {\n    const skew = self.getVelocity() / 300;\n    gsap.to(".element", {\n      skewX: skew, duration: 0.3\n    });\n  }\n});`,
    'layered-zoom': `gsap.from(".inner-layer", {\n  scale: 0.6, opacity: 0,\n  scrollTrigger: {\n    trigger: ".wrapper",\n    scrub: true\n  }\n});`,
    'velocity-blur': `ScrollTrigger.create({\n  onUpdate: (self) => {\n    const blur = Math.min(Math.abs(self.getVelocity()) / 200, 8);\n    gsap.to(".text", { filter: \`blur(\${blur}px)\`, duration: 0.1 });\n  }\n});`,
    'tilt-parallax-card': `card.addEventListener("mousemove", (e) => {\n  const x = (e.offsetX / card.width - 0.5);\n  const y = (e.offsetY / card.height - 0.5);\n  gsap.to(card, {\n    rotateY: x * 20, rotateX: -y * 20,\n    duration: 0.3, transformPerspective: 600\n  });\n});`,
    'card-hover-lift': `card.addEventListener("mouseenter", () => {\n  gsap.to(card, {\n    y: -8, scale: 1.02,\n    boxShadow: "0 20px 40px rgba(0,0,0,0.2)",\n    duration: 0.3\n  });\n});`,
    'card-3d-flip': `gsap.to(".card-inner", {\n  rotationY: 180,\n  duration: 0.6,\n  ease: "power2.inOut"\n});`,
    'card-expand-detail': `const state = Flip.getState(".cards");\ncard.classList.toggle("expanded");\nFlip.from(state, {\n  duration: 0.5,\n  ease: "power2.inOut"\n});`,
    'stacked-card-fan': `gsap.to(".card", {\n  x: (i) => (i - 2) * 25,\n  rotation: (i) => (i - 2) * 8,\n  duration: 0.5,\n  ease: "back.out(1.4)"\n});`,
    'card-slide-stagger': `gsap.from(".card", {\n  x: (i) => i % 2 === 0 ? -100 : 100,\n  opacity: 0, duration: 0.6,\n  stagger: 0.15,\n  ease: "power3.out"\n});`,
    'card-bg-shift': `gsap.to(".card", {\n  backgroundPosition: "100% 100%",\n  duration: 0.8,\n  ease: "power2.out"\n});`,
    'flip-grid-filter': `const state = Flip.getState(".items");\nitems.forEach(item => {\n  item.style.display = matches(item) ? "" : "none";\n});\nFlip.from(state, {\n  duration: 0.5, stagger: 0.05,\n  absolute: true\n});`,
    'shared-element-transition': `const state = Flip.getState(".thumb");\nthumb.classList.add("hero");\nFlip.from(state, {\n  duration: 0.4,\n  ease: "power2.inOut"\n});`,
    'accordion-motion': `const state = Flip.getState(".items");\npanel.classList.toggle("active");\nFlip.from(state, {\n  duration: 0.4,\n  ease: "power2.inOut"\n});`,
    'clip-path-reveal': `gsap.to(".image", {\n  clipPath: "polygon(0 0, 100% 0, 100% 100%, 0 100%)",\n  duration: 1.2,\n  ease: "power3.inOut",\n  scrollTrigger: ".image"\n});`,
    'image-parallax-zoom': `gsap.fromTo(".image",\n  { scale: 1.3, y: 30 },\n  { scale: 1, y: -30,\n    scrollTrigger: {\n      trigger: ".wrap",\n      scrub: true\n    }\n  }\n);`,
    'before-after-slider': `container.addEventListener("mousemove", (e) => {\n  const x = e.offsetX / container.offsetWidth;\n  gsap.to(handle, { left: x * 100 + "%", duration: 0.1 });\n  gsap.to(before, {\n    clipPath: \`inset(0 \${(1-x)*100}% 0 0)\`,\n    duration: 0.1\n  });\n});`,
    'grayscale-to-color': `gsap.to(".image", {\n  filter: "grayscale(0%)",\n  duration: 1.5,\n  scrollTrigger: {\n    trigger: ".image",\n    start: "top 80%"\n  }\n});`,
    'masonry-cascade': `gsap.from(".item", {\n  opacity: 0, y: 60, scale: 0.8,\n  rotation: () => gsap.utils.random(-10, 10),\n  stagger: { amount: 0.8, from: "random" },\n  ease: "back.out(1.4)"\n});`,
    'image-tilt-hover': `image.addEventListener("mousemove", (e) => {\n  const x = (e.offsetX / image.width - 0.5);\n  const y = (e.offsetY / image.height - 0.5);\n  gsap.to(image, {\n    rotateY: x * 25, rotateX: -y * 25,\n    duration: 0.3, transformPerspective: 600\n  });\n});`,
    'magnetic-button': `preview.addEventListener("mousemove", (e) => {\n  const dx = e.clientX - btnCenter.x;\n  const dy = e.clientY - btnCenter.y;\n  const dist = Math.sqrt(dx*dx + dy*dy);\n  if (dist < 120) {\n    const pull = (120 - dist) / 120;\n    gsap.to(btn, { x: dx * pull * 0.4, y: dy * pull * 0.4 });\n  }\n});`,
    'underline-slide': `/* CSS-only approach */\n.link::after {\n  transform: scaleX(0);\n  transform-origin: right;\n  transition: transform 0.3s;\n}\n.link:hover::after {\n  transform: scaleX(1);\n  transform-origin: left;\n}`,
    'hover-border-draw': `/* SVG stroke-dasharray approach */\nrect {\n  stroke-dasharray: 600;\n  stroke-dashoffset: 600;\n  transition: stroke-dashoffset 0.6s;\n}\n.box:hover rect {\n  stroke-dashoffset: 0;\n}`,
    'ripple-click': `btn.addEventListener("click", (e) => {\n  const ripple = document.createElement("span");\n  ripple.style.cssText = \`position:absolute; border-radius:50%; background:rgba(0,255,102,0.3);\`;\n  btn.appendChild(ripple);\n  gsap.to(ripple, { scale: 1, opacity: 0, duration: 0.8 });\n});`,
    'icon-morph': `// Hamburger → X morph\ngsap.to(topLine, {\n  attr: { x1: 12, y1: 12, x2: 28, y2: 28 },\n  duration: 0.3\n});\ngsap.to(bottomLine, {\n  attr: { x1: 12, y1: 28, x2: 28, y2: 12 },\n  duration: 0.3\n});\ngsap.to(midLine, { opacity: 0, duration: 0.2 });`,
    'button-shimmer': `btn.addEventListener("mouseenter", () => {\n  const overlay = document.createElement("span");\n  overlay.style.cssText = "position:absolute;top:0;left:-100%;width:60%;height:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.3),transparent);";\n  btn.appendChild(overlay);\n  gsap.to(overlay, { left: "200%", duration: 0.6, onComplete: () => overlay.remove() });\n});`,
    'elastic-stretch': `el.addEventListener("mousemove", (e) => {\n  const dx = e.clientX - startX;\n  gsap.to(el, { scaleX: 1 + Math.abs(dx)/200, x: dx*0.3 });\n});\nel.addEventListener("mouseup", () => {\n  gsap.to(el, { scaleX: 1, x: 0, ease: "elastic.out(1,0.3)" });\n});`,
    'scratch-off': `canvas.addEventListener("mousemove", (e) => {\n  if (!scratching) return;\n  ctx.globalCompositeOperation = "destination-out";\n  ctx.arc(e.offsetX, e.offsetY, 20, 0, Math.PI*2);\n  ctx.fill();\n});`,
    'card-deck-toss': `Draggable.create(".card", {\n  type: "x,y",\n  inertia: true,\n  onDragEnd: function() {\n    if (Math.abs(this.endX) > 100) {\n      gsap.to(this.target, { x: this.endX*3, opacity: 0 });\n    }\n  }\n});`,
    'cube-drag-3d': `scene.addEventListener("mousemove", (e) => {\n  rotY += (e.clientX - lastX) * 0.5;\n  rotX -= (e.clientY - lastY) * 0.5;\n  gsap.to(cube, {\n    rotateX: rotX, rotateY: rotY, duration: 0.3\n  });\n});`,
    'wheel-spin': `Draggable.create(".wheel", {\n  type: "rotation",\n  inertia: true,\n  snap: (val) => Math.round(val / 60) * 60\n});`,
    'svg-line-draw': `const path = document.querySelector("path");\nconst len = path.getTotalLength();\ngsap.set(path, { strokeDasharray: len, strokeDashoffset: len });\ngsap.to(path, {\n  strokeDashoffset: 0,\n  duration: 1.5,\n  scrollTrigger: path\n});`,
    'shape-morph': `gsap.to("#star", {\n  morphSVG: "#circle",\n  duration: 0.8,\n  ease: "power2.inOut"\n});`,
    'animated-blob': `const shapes = ["path1", "path2", "path3"];\nconst tl = gsap.timeline({ repeat: -1 });\nshapes.forEach(s => {\n  tl.to(".blob", { morphSVG: s, duration: 2, ease: "sine.inOut" });\n});`,
    'logo-stroke-reveal': `const tl = gsap.timeline();\ntl.from("text", { drawSVG: "0%", duration: 2, ease: "power2.inOut" })\n  .to("text", { fill: "#00FF66", duration: 0.8 }, "-=0.3");`,
    'floating-shapes': `gsap.to(".shape", {\n  y: "random(-20, 20)",\n  x: "random(-10, 10)",\n  rotation: "random(-15, 15)",\n  duration: "random(2, 4)",\n  ease: "sine.inOut",\n  yoyo: true, repeat: -1\n});`,
    'liquid-button-morph': `btn.addEventListener("mouseenter", () => {\n  gsap.to(path, {\n    morphSVG: hoverPath,\n    duration: 0.4,\n    ease: "elastic.out(1, 0.5)"\n  });\n});`,
    'mood-face-morph': `gsap.to(".mouth", {\n  morphSVG: sadMouthPath,\n  duration: 0.5,\n  ease: "power2.inOut"\n});`,
    'animal-silhouette': `const animals = [cat, fish, bird];\nconst tl = gsap.timeline({ repeat: -1 });\nanimals.forEach(a => {\n  tl.to(".animal", { morphSVG: a, duration: 1.2, ease: "power2.inOut" });\n});`,
    'day-night-scene': `const tl = gsap.timeline();\ntl.to(".sky", { fill: "#1a1a3e", duration: 2 })\n  .to(".sun", { morphSVG: ".moon", fill: "#E8E8E8", duration: 2 }, 0)\n  .to(".hills", { fill: "#0a3d0a", duration: 2 }, 0);`,
    'gooey-menu': `function moveBlob(target) {\n  const rect = target.getBoundingClientRect();\n  gsap.to(".blob", {\n    left: rect.left - nav.left,\n    width: rect.width + 16,\n    duration: 0.4,\n    ease: "power2.out"\n  });\n}`,
    'blueprint-reveal': `gsap.from(".line", {\n  drawSVG: "50% 50%",\n  duration: 0.8,\n  stagger: 0.2,\n  ease: "power2.inOut"\n});`,
    'constellation-connect': `const tl = gsap.timeline();\ntl.to(".star", { opacity: 1, stagger: 0.1 })\n  .from(".connection", { drawSVG: "0%", stagger: 0.2, duration: 0.6 });`,
    'signature-draw': `gsap.from(".signature-path", {\n  drawSVG: "0%",\n  duration: 2,\n  ease: "power1.inOut"\n});`,
    'circuit-trace': `const tl = gsap.timeline();\ntl.from(".trace", { drawSVG: "0%", stagger: 0.3, duration: 1.2 })\n  .from(".node", { scale: 0, stagger: 0.15, ease: "back.out(2)" });`,
    'animated-infographic': `const tl = gsap.timeline();\ntl.from(".chart-line", { drawSVG: "0%", duration: 1.5 })\n  .from(".data-dot", { opacity: 0, scale: 0, stagger: 0.1 }, "-=0.8");`,
    'satellite-orbit': `gsap.to(".satellite", {\n  motionPath: {\n    path: "#orbit",\n    align: "#orbit",\n    autoRotate: true\n  },\n  duration: 3, ease: "none", repeat: -1\n});`,
    'conveyor-belt': `gsap.to(".item", {\n  motionPath: {\n    path: "#belt-path",\n    align: "#belt-path",\n    alignOrigin: [0.5, 0.5]\n  },\n  duration: 2.5, stagger: 0.8\n});`,
    'scroll-path-journey': `const tl = gsap.timeline({ scrollTrigger: { scrub: true } });\ntl.from(".trail", { drawSVG: "0%" })\n  .to(".icon", { motionPath: { path: "#path", align: "#path" } }, 0);`,
    'dna-helix': `gsap.to(".strand-a", {\n  x: (i) => Math.sin(i * 0.6) * 30,\n  duration: 2, ease: "sine.inOut",\n  yoyo: true, repeat: -1, stagger: 0.1\n});`,
    'rollercoaster-stats': `const tl = gsap.timeline();\ntl.from(".track", { drawSVG: "0%", duration: 2.5 })\n  .to(".cart", {\n    motionPath: { path: "#track", align: "#track" },\n    duration: 2.5\n  }, 0);`,
    'confetti-cannon': `for (let i = 0; i < 30; i++) {\n  const piece = createConfetti();\n  gsap.to(piece, {\n    physics2D: {\n      velocity: gsap.utils.random(300, 600),\n      angle: gsap.utils.random(250, 290),\n      gravity: 400\n    }\n  });\n}`,
    'gravity-card-drop': `gsap.from(".card", {\n  y: -200, rotation: gsap.utils.random(-20, 20),\n  duration: 1, ease: "bounce.out",\n  stagger: 0.2\n});`,
    'magnetic-repel': `dots.forEach(dot => {\n  const dist = getDistance(dot, cursor);\n  if (dist < 80) {\n    const force = (80 - dist) / 80;\n    gsap.to(dot, { x: dx * force, y: dy * force });\n  }\n});`,
    'throw-and-snap': `Draggable.create(".ball", {\n  inertia: true,\n  liveSnap: {\n    x: (val) => Math.round(val / gridSize) * gridSize,\n    y: (val) => Math.round(val / gridSize) * gridSize\n  }\n});`,
    'popcorn-loader': `gsap.to(kernel, {\n  physics2D: {\n    velocity: gsap.utils.random(200, 400),\n    angle: gsap.utils.random(260, 280),\n    gravity: 300\n  }\n});`,
    'jelly-button': `btn.addEventListener("click", () => {\n  gsap.timeline()\n    .to(btn, { scaleX: 1.2, scaleY: 0.8, duration: 0.1 })\n    .to(btn, { scaleX: 0.9, scaleY: 1.1, duration: 0.1 })\n    .to(btn, { scaleX: 1, scaleY: 1, ease: "elastic.out(1, 0.4)" });\n});`,
    'notification-shake': `gsap.to(".notification", {\n  x: 10, duration: 0.05,\n  yoyo: true, repeat: 7,\n  ease: "power2.inOut",\n  onComplete: () => gsap.to(".notification", { x: 0 })\n});`,
    'wobble-card-enter': `gsap.from(".card", {\n  opacity: 0, y: 50,\n  rotation: gsap.utils.random(-15, 15),\n  duration: 0.8, stagger: 0.15,\n  ease: "elastic.out(1, 0.5)"\n});`,
    'springboard-menu': `gsap.from(".menu-item", {\n  opacity: 0, x: -60,\n  duration: 0.6, stagger: 0.1,\n  ease: "back.out(1.7)"\n});`,
    'newtons-cradle': `const tl = gsap.timeline({ repeat: -1 });\ntl.to(firstBall, { rotation: -30, duration: 0.3, transformOrigin: "top" })\n  .to(firstBall, { rotation: 0, duration: 0.3 })\n  .to(lastBall, { rotation: 30, duration: 0.3 }, "-=0.05")\n  .to(lastBall, { rotation: 0, duration: 0.3 });`,
    'infinite-loop': `const items = gsap.utils.toArray(".item");\nconst totalWidth = items.length * itemWidth;\ngsap.to(".track", {\n  x: -totalWidth, duration: 8,\n  ease: "none", repeat: -1,\n  modifiers: { x: gsap.utils.unitize(x => parseFloat(x) % totalWidth) }\n});`,
    'coverflow-3d': `items.forEach((item, i) => {\n  const offset = i - currentIndex;\n  gsap.to(item, {\n    rotateY: offset * -30,\n    z: offset === 0 ? 50 : -Math.abs(offset) * 30,\n    scale: offset === 0 ? 1.2 : 0.85,\n    duration: 0.5\n  });\n});`,
    'draggable-carousel': `Draggable.create(".carousel", {\n  type: "x",\n  inertia: true,\n  bounds: { minX: -maxScroll, maxX: 0 },\n  edgeResistance: 0.85,\n  snap: (val) => Math.round(val / slideWidth) * slideWidth\n});`,
    'vertical-card-stack': `gsap.to(topCard, {\n  y: 120, opacity: 0, rotation: 10,\n  duration: 0.4, ease: "power2.in",\n  onComplete: () => {\n    // Move card to bottom of stack\n    stack.prepend(topCard);\n    gsap.set(topCard, { y: 0, opacity: 1, rotation: 0 });\n  }\n});`,
    'parallax-slider': `const tl = gsap.timeline();\ntl.to(prevSlide, { opacity: 0, duration: 0.3 })\n  .to(prevBg, { x: -50, duration: 0.5 }, 0)\n  .to(nextSlide, { opacity: 1, duration: 0.3 }, 0.2)\n  .fromTo(nextBg, { x: 50 }, { x: 0, duration: 0.5 }, 0.2);`,
    'staggered-blinds': `gsap.to(".blind", {\n  scaleX: 0, duration: 0.6,\n  stagger: { amount: 0.4, from: "edges" },\n  ease: "power2.inOut"\n});`,
    'counter-preloader': `gsap.to(counter, {\n  val: 100, duration: 2.5,\n  ease: "power2.inOut",\n  onUpdate: () => {\n    display.textContent = Math.round(counter.val) + "%";\n    bar.style.width = counter.val + "%";\n  }\n});`,
    'circle-wipe': `gsap.to(".circle", {\n  width: "400px", height: "400px",\n  duration: 0.8, ease: "power2.in"\n});`,
    'skeleton-to-content': `gsap.to(".skeleton-line", {\n  background: "rgba(0,255,102,0.15)",\n  backgroundImage: "none",\n  stagger: 0.1, duration: 0.3\n});`,
    'count-up': `gsap.to(counter, {\n  val: 1248, duration: 2,\n  ease: "power2.out",\n  snap: { val: 1 },\n  onUpdate: () => {\n    el.textContent = Math.round(counter.val).toLocaleString();\n  },\n  scrollTrigger: el\n});`,
    'odometer': `gsap.to(".digit-strip", {\n  y: -targetDigit * digitHeight,\n  duration: 1.5,\n  ease: "power2.out"\n});`,
    'circular-progress': `const circumference = 2 * Math.PI * radius;\ngsap.set(ring, { strokeDasharray: circumference, strokeDashoffset: circumference });\ngsap.to(ring, {\n  strokeDashoffset: circumference * (1 - target/100),\n  duration: 1.5,\n  scrollTrigger: ring\n});`,
    'animated-bar-chart': `gsap.to(".bar-fill", {\n  height: (i) => data[i] + "%",\n  duration: 0.8, stagger: 0.1,\n  ease: "power2.out",\n  scrollTrigger: ".chart"\n});`,
    'animated-gradient': `gsap.to(".bg", {\n  backgroundPosition: "100% 100%",\n  duration: 4, ease: "sine.inOut",\n  yoyo: true, repeat: -1\n});`,
    'particle-float': `gsap.to(particle, {\n  y: gsap.utils.random(-150, -50),\n  x: gsap.utils.random(-30, 30),\n  opacity: 0,\n  duration: gsap.utils.random(3, 6),\n  repeat: -1\n});`,
    'cursor-spotlight': `area.addEventListener("mousemove", (e) => {\n  gsap.to(light, {\n    left: e.offsetX, top: e.offsetY,\n    duration: 0.2\n  });\n});`,
    'particle-text': `// Get text pixel data from canvas\nconst imageData = ctx.getImageData(0, 0, w, h);\n// Create particles at text pixel positions\n// On mousemove: scatter nearby particles\n// On frame: lerp particles back to origin\nparticles.forEach(p => {\n  p.x += (p.originX - p.x) * 0.1;\n  p.y += (p.originY - p.y) * 0.1;\n});`,
    'scroll-storyteller': `const tl = gsap.timeline({ scrollTrigger: { scrub: true } });\ntl.from(".line", { drawSVG: "0%", duration: 2 })\n  .from(".shape", { morphSVG: ".start-shape", duration: 1 })\n  .to(".text", { scrambleText: "Final text", duration: 1.5 });`,
    'gravity-form': `gsap.from(".input", {\n  y: -200, opacity: 0,\n  duration: 0.8, stagger: 0.3,\n  ease: "bounce.out"\n});`,
    'ken-burns-slideshow': `const tl = gsap.timeline({ repeat: -1 });\nslides.forEach((slide, i) => {\n  tl.fromTo(slide,\n    { opacity: 0, scale: 1 },\n    { opacity: 1, scale: 1.15, duration: 2 },\n    i * 3\n  ).to(slide, { opacity: 0, duration: 1 }, i * 3 + 2.5);\n});`,
    'curtain-reveal': `const tl = gsap.timeline();\ntl.to(".curtain-left", { xPercent: -100, duration: 1, ease: "power3.inOut" }, 0)\n  .to(".curtain-right", { xPercent: 100, duration: 1, ease: "power3.inOut" }, 0)\n  .from(".content", { scale: 0.5, opacity: 0, ease: "back.out(1.7)" }, 0.5);`,
    'aurora-waves': `const tl = gsap.timeline({ repeat: -1, yoyo: true });\nwaves.forEach((wave, i) => {\n  tl.to(wave, {\n    y: -20 + i * 10,\n    scaleX: 1.2,\n    opacity: 0.4,\n    duration: 3 + i,\n    ease: "sine.inOut"\n  }, 0);\n});`,
    'timeline-scroll-experience': `const tl = gsap.timeline({ scrollTrigger: { trigger: ".timeline", scrub: true } });\ntl.from(".line", { scaleY: 0, transformOrigin: "top center", duration: 1.2 });\nmilestones.forEach((ms, i) => {\n  tl.from(ms.querySelector(".dot"), { scale: 0, ease: "back.out(2)" }, 0.3 + i * 0.35);\n});`,
  };

  /* ═══════════════════════════════════════════
     INITIALIZATION
     ═══════════════════════════════════════════ */
  function init() {
    const demoSections = document.querySelectorAll('.ga-demo-section');
    let effectCount = 0;

    demoSections.forEach(section => {
      const effectId = section.dataset.effect;
      const preview = section.querySelector('.ga-preview');
      const replayBtn = section.querySelector('.replay-btn');
      let currentAnim = null;

      // ScrollTrigger to play effect on scroll into view
      ScrollTrigger.create({
        trigger: section,
        start: 'top 80%',
        once: true,
        onEnter: () => {
          if (effects[effectId] && preview) {
            try {
              currentAnim = effects[effectId](preview);
            } catch (e) {
              console.warn('Effect error:', effectId, e);
            }
          }
        }
      });

      // Replay button
      if (replayBtn) {
        replayBtn.addEventListener('click', () => {
          if (currentAnim && currentAnim.restart) {
            currentAnim.restart();
          } else if (effects[effectId] && preview) {
            try {
              currentAnim = effects[effectId](preview);
            } catch (e) {
              console.warn('Replay error:', effectId, e);
            }
          }
        });
      }

      // Populate code block
      const codeBlock = section.querySelector('.ga-code-block');
      if (codeBlock && codeSnippets[effectId]) {
        codeBlock.textContent = codeSnippets[effectId];
      }

      effectCount++;
    });

    // Copy code buttons
    document.querySelectorAll('.copy-code-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const effectId = btn.dataset.effect;
        const code = codeSnippets[effectId];
        if (code) {
          navigator.clipboard.writeText(code).then(() => {
            const icon = btn.querySelector('i');
            icon.className = 'bi bi-check2 small';
            setTimeout(() => { icon.className = 'bi bi-clipboard small'; }, 2000);
          });
        }
      });
    });

    // Category navigation — active state on scroll
    const catCards = document.querySelectorAll('.ga-cat-card');
    const catSections = document.querySelectorAll('.ga-category-section');
    catSections.forEach(section => {
      ScrollTrigger.create({
        trigger: section,
        start: 'top 40%',
        end: 'bottom 40%',
        onToggle: (self) => {
          if (self.isActive) {
            catCards.forEach(l => l.classList.remove('active'));
            const card = document.querySelector(`.ga-cat-card[data-cat="${section.id}"]`);
            if (card) card.classList.add('active');
          }
        }
      });
    });

    // Effect indicator
    const indicator = document.getElementById('effectIndicator');
    const indicatorName = indicator?.querySelector('.ga-indicator-name');
    const indicatorCount = indicator?.querySelector('.ga-indicator-count');

    demoSections.forEach((section, i) => {
      ScrollTrigger.create({
        trigger: section,
        start: 'top 60%',
        end: 'bottom 40%',
        onToggle: (self) => {
          if (self.isActive && indicator) {
            const title = section.querySelector('h3')?.textContent || '';
            indicatorName.textContent = title;
            indicatorCount.textContent = `${i + 1} / ${demoSections.length}`;
            indicator.classList.add('visible');
          }
        }
      });
    });

    // Hide indicator when not in demo area
    ScrollTrigger.create({
      trigger: demoSections[0],
      endTrigger: demoSections[demoSections.length - 1],
      start: 'top 70%',
      end: 'bottom 30%',
      onLeave: () => indicator?.classList.remove('visible'),
      onLeaveBack: () => indicator?.classList.remove('visible')
    });

    // Refresh ScrollTrigger
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        ScrollTrigger.refresh();
      });
    });
  }

  // Run when DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
