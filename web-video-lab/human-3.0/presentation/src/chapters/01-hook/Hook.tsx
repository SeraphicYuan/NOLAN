import type { CSSProperties } from "react";
import { MaskReveal } from "../../components/MaskReveal";
import type { ChapterStepProps } from "../../registry/types";
import "./Hook.css";

/**
 * Chapter 01 — "钩子 · 我不想当 NPC"
 *
 * Theme: bold-signal (high-contrast, heavy, manifesto). Each step is a
 * full-screen takeover with one content-driven dominant motion:
 *   0 hook      — looping "someone else's script" backdrop + NPC strike
 *   1 thesis    — five life-stat bars maxing out (staggered grow)
 *   2 level 100 — map grid unlocking in a diagonal sweep
 *   3 chases    — three pursuits revealed one-by-one (MaskReveal staggered)
 *   4 stat      — 15 / 5 hero numbers stamp in + repeating pattern echo
 *   5 punchline — HUMAN 3.0 letter-slam + mediocrity → potential arrow
 *
 * Color + font come ONLY from the active theme's semantic tokens.
 */

const NPC_SCRIPT = [
  "06:30   alarm()  // not yours",
  "08:00   commute  →  cubicle",
  "12:00   same lunch, same seat",
  "18:00   commute  →  couch",
  "23:00   scroll. sleep.",
  "goto:   tomorrow  // forever",
];

const STATS = [
  { label: "MIND", to: 100 },
  { label: "BODY", to: 100 },
  { label: "SPIRIT", to: 100 },
  { label: "RELATIONSHIPS", to: 100 },
  { label: "MONEY", to: 100 },
];

const FIELDS = [
  "psychology",
  "philosophy",
  "money",
  "religion",
  "startups",
  "the internet",
];

export default function HookChapter({ step }: ChapterStepProps) {
  /* ── Step 0 · hook + contrast backdrop ───────────────────────────── */
  if (step === 0) {
    return (
      <div key="hk0" className="hk-scene hk-s0 center">
        <div className="hk-loop" aria-hidden>
          {[0, 1, 2].map((block) =>
            NPC_SCRIPT.map((line, i) => (
              <div
                key={`${block}-${i}`}
                className="hk-loop-row"
                style={{ animationDelay: `${(block * NPC_SCRIPT.length + i) * 80}ms` }}
              >
                {line}
              </div>
            )),
          )}
        </div>

        <div className="hk-s0-fore">
          <div className="kicker hk-src">Dan Koe · HUMAN 3.0</div>
          <h1 className="hk-h0">
            <MaskReveal show duration={700}>
              <span>I never wanted to be an&nbsp;</span>
            </MaskReveal>
            <span className="hk-npc">
              NPC<span className="hk-strike" />
            </span>
            <span>.</span>
          </h1>
          <p className="hk-s0-sub">
            Running on a script someone else wrote. Same loop, every day,
            until it&rsquo;s over.
          </p>
        </div>
      </div>
    );
  }

  /* ── Step 1 · counter-thesis: max out every stat ─────────────────── */
  if (step === 1) {
    return (
      <div key="hk1" className="hk-scene hk-s1 scene-pad">
        <div className="hk-s1-head">
          <div className="kicker">I wanted the opposite</div>
          <h2 className="hk-h1">
            <MaskReveal show duration={600}>
              <span>Max out&nbsp;</span>
            </MaskReveal>
            <MaskReveal show delay={260} duration={600}>
              <span className="hk-accent">every stat</span>
            </MaskReveal>
            <span>.</span>
          </h2>
        </div>

        <div className="hk-bars">
          {STATS.map((s, i) => (
            <div className="hk-bar" key={s.label}>
              <span className="hk-bar-label label-mono">{s.label}</span>
              <span className="hk-bar-track">
                <span
                  className="hk-bar-fill"
                  style={{
                    width: `${s.to}%`,
                    animationDelay: `${300 + i * 130}ms`,
                  }}
                />
              </span>
              <span
                className="hk-bar-max"
                style={{ animationDelay: `${900 + i * 130}ms` }}
              >
                MAX
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  /* ── Step 2 · level 100 player / map unlocked ────────────────────── */
  if (step === 2) {
    const COLS = 7;
    const ROWS = 4;
    const tiles = Array.from({ length: COLS * ROWS }, (_, idx) => {
      const col = idx % COLS;
      const row = Math.floor(idx / COLS);
      return { idx, delay: (col + row) * 70 };
    });
    return (
      <div key="hk2" className="hk-scene hk-s2 scene-pad">
        <div className="hk-s2-top">
          <div className="hk-lvl-wrap">
            <span className="kicker">Level</span>
            <span className="hero-num hk-lvl">100</span>
          </div>
          <div className="hk-s2-tag">
            <MaskReveal show duration={650}>
              <span>Every area of the map&nbsp;</span>
            </MaskReveal>
            <MaskReveal show delay={300} duration={650}>
              <span className="hk-accent">unlocked.</span>
            </MaskReveal>
          </div>
        </div>

        <div className="hk-grid" style={{ "--cols": COLS } as CSSProperties}>
          {tiles.map((t) => (
            <span
              key={t.idx}
              className="hk-tile"
              style={{ animationDelay: `${500 + t.delay}ms` }}
            />
          ))}
        </div>

        <div className="hk-s2-caps">
          <span className="label-mono">
            Not jacked in one place &mdash;{" "}
            <span className="hk-accent">jacked everywhere</span>
          </span>
          <span className="label-mono">Bank overflowing with gold</span>
        </div>
      </div>
    );
  }

  /* ── Step 3 · progressive list: the three chases ─────────────────── */
  if (step === 3) {
    const chases = [
      { n: "01", title: "FITNESS", note: "obsessed as a teenager" },
      { n: "02", title: "KNOWLEDGE", note: "absorb every bit I could find" },
    ];
    return (
      <div key="hk3" className="hk-scene hk-s3 scene-pad">
        <div className="kicker">So I chased it</div>

        <div className="hk-chases">
          {chases.map((c, i) => (
            <div
              className="hk-chase"
              key={c.n}
              style={{ animationDelay: `${i * 1500}ms` }}
            >
              <span className="hk-chase-num hero-num">{c.n}</span>
              <span className="hk-chase-rule" style={{ animationDelay: `${i * 1500 + 200}ms` }} />
              <div className="hk-chase-body">
                <MaskReveal show delay={i * 1500 + 150} duration={650}>
                  <span className="hk-chase-title">{c.title}</span>
                </MaskReveal>
                <span className="hk-chase-note">{c.note}</span>
              </div>
            </div>
          ))}

          {/* third chase: business after business until one worked */}
          <div className="hk-chase" style={{ animationDelay: "3000ms" }}>
            <span className="hk-chase-num hero-num">03</span>
            <span className="hk-chase-rule" style={{ animationDelay: "3200ms" }} />
            <div className="hk-chase-body">
              <MaskReveal show delay={3150} duration={650}>
                <span className="hk-chase-title">FREEDOM</span>
              </MaskReveal>
              <div className="hk-attempts">
                {[0, 1, 2, 3].map((m) => (
                  <span
                    key={m}
                    className="hk-attempt hk-attempt-fail"
                    style={{ animationDelay: `${3500 + m * 380}ms` }}
                  >
                    <span
                      className="hk-attempt-x"
                      style={{ animationDelay: `${3650 + m * 380}ms` }}
                    />
                  </span>
                ))}
                <span
                  className="hk-attempt hk-attempt-win"
                  style={{ animationDelay: "5100ms" }}
                />
                <span className="hk-attempt-note" style={{ animationDelay: "5400ms" }}>
                  until one finally worked
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  /* ── Step 4 · credibility stat ───────────────────────────────────── */
  if (step === 4) {
    return (
      <div key="hk4" className="hk-scene hk-s4 scene-pad">
        <div className="hk-s4-nums">
          <div className="hk-stat">
            <span className="hero-num hk-bignum">15</span>
            <div className="hk-stat-meta">
              <span className="label-mono">years digging</span>
              <div className="hk-fields">
                {FIELDS.map((f, i) => (
                  <span
                    className="hk-field"
                    key={f}
                    style={{ animationDelay: `${500 + i * 90}ms` }}
                  >
                    {f}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <span className="hk-s4-plus">+</span>

          <div className="hk-stat">
            <span className="hero-num hk-bignum">5</span>
            <div className="hk-stat-meta">
              <span className="label-mono">years writing</span>
              <span className="hk-stat-sub">in public</span>
            </div>
          </div>
        </div>

        <div className="hk-echo-band">
          <MaskReveal show delay={700} duration={700}>
            <span className="hk-echo-text">
              The same patterns kept showing up&hellip;
            </span>
          </MaskReveal>
          <div className="hk-echo">
            {Array.from({ length: 9 }, (_, i) => (
              <span
                key={i}
                className="hk-echo-mark"
                style={{ animationDelay: `${1100 + i * 110}ms` }}
              />
            ))}
            <span className="hk-echo-label" style={{ animationDelay: "2200ms" }}>
              over and over
            </span>
          </div>
        </div>
      </div>
    );
  }

  /* ── Step 5 · punchline: HUMAN 3.0 ───────────────────────────────── */
  const title = "HUMAN".split("");
  return (
    <div key="hk5" className="hk-scene hk-s5 center">
      <div className="hk-s5-inner">
        <div className="kicker">Those patterns became one thing</div>

        <h1 className="hk-title letter-stagger">
          {title.map((ch, i) => (
            <span className="letter" key={i} style={{ "--i": i } as CSSProperties}>
              {ch}
            </span>
          ))}
          <span
            className="letter hk-ver"
            style={{ "--i": title.length + 1 } as CSSProperties}
          >
            3.0
          </span>
        </h1>

        <div className="hk-map">
          <span className="hk-map-from">escape mediocrity</span>
          <span className="hk-arrow">
            <span className="hk-arrow-line" />
            <span className="hk-arrow-head" />
          </span>
          <span className="hk-map-to">reach your potential</span>
        </div>
      </div>
    </div>
  );
}
