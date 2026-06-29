import { MaskReveal } from "../../components/MaskReveal";
import type { ChapterStepProps } from "../../registry/types";
import "./OneMap.css";

/* ─── data drawn from outline source L21 / L23 ─── */
const MODELS = [
  { name: "Spiral Dynamics", domain: "Mind", en: "the mind" },
  { name: "Buddhism · Christianity", domain: "Meaning", en: "meaning" },
  { name: "Red Pill · Feminism", domain: "Dating", en: "dating" },
  { name: "eCommerce · Consulting", domain: "Money", en: "money" },
];

const DOMAINS = ["Mind", "Meaning", "Dating", "Money"];

const ARCHETYPES = [
  { who: "Spiritual Teacher", strongLabel: "Spirit", strong: 95, weakLabel: "Body", weak: 13, flaw: "frail body" },
  { who: "Businessman", strongLabel: "Wealth", strong: 92, weakLabel: "Relationships", weak: 16, flaw: "can't hold a relationship" },
  { who: "Alpha Male", strongLabel: "Presence", strong: 88, weakLabel: "Emotion", weak: 9, flaw: "emotional wreck" },
];

/* web nodes for the signature step-3 diagram (viewBox 760×600) */
const WEB_NODES = [
  { id: "Mind", x: 380, y: 84 },
  { id: "Dating", x: 118, y: 188 },
  { id: "Meaning", x: 648, y: 220 },
  { id: "Body", x: 96, y: 432 },
  { id: "Career", x: 600, y: 470 },
  { id: "Money", x: 322, y: 540 },
];
const WEB_EDGES: [string, string][] = [
  ["Mind", "Dating"], ["Mind", "Meaning"], ["Mind", "Career"], ["Mind", "Body"],
  ["Meaning", "Career"], ["Meaning", "Money"], ["Career", "Money"],
  ["Money", "Body"], ["Body", "Dating"], ["Dating", "Money"],
];

function nodeOf(id: string) {
  return WEB_NODES.find((n) => n.id === id)!;
}

export default function OneMapChapter({ step }: ChapterStepProps) {
  /* ───────────────────── step 0 — "tons of maps already" ──────────────── */
  if (step === 0) {
    const pins = Array.from({ length: 40 });
    return (
      <div className="om-scene om-s0 scene-pad">
        <div className="om-pinfield" aria-hidden>
          {pins.map((_, i) => (
            <span
              key={i}
              className={`om-pin${i % 5 === 0 ? " is-accent" : ""}`}
              style={{ animationDelay: `${(i % 9) * 40 + Math.floor(i / 9) * 70}ms` }}
            >
              <svg viewBox="0 0 24 32" width="24" height="32">
                <path
                  d="M12 0C5.4 0 0 5.2 0 11.6 0 20 12 32 12 32s12-12 12-20.4C24 5.2 18.6 0 12 0z"
                  fill="currentColor"
                />
                <circle cx="12" cy="11.5" r="4.4" fill="var(--surface)" />
              </svg>
            </span>
          ))}
        </div>

        <div className="om-s0-body">
          <div className="kicker">they already exist · existing maps</div>
          <h1 className="om-hero">
            <MaskReveal show duration={760}>
              <span className="serif-cn">Maps are&nbsp;</span>
            </MaskReveal>
            <MaskReveal show delay={360} duration={760}>
              <span className="serif-it om-em">everywhere</span>
            </MaskReveal>
            <MaskReveal show delay={680} duration={760}>
              <span className="serif-cn">.</span>
            </MaskReveal>
          </h1>
          <p className="om-s0-sub">
            <span className="om-em mono">tons of them</span> — every guru, every model
            hands you one.
          </p>
        </div>
      </div>
    );
  }

  /* ───────────── step 1 — progressive list: model → domain ledger ──────── */
  if (step === 1) {
    return (
      <div className="om-scene om-s1 scene-pad">
        <div className="om-head">
          <div className="kicker">existing models · one map per domain</div>
          <h2 className="om-head-h serif-cn">
            Each one <span className="om-em">maps only one square</span>
          </h2>
        </div>
        <hr className="rule" style={{ margin: "var(--space-5) 0 0" }} />

        <ul className="om-ledger">
          {MODELS.map((m, i) => (
            <li
              key={m.name}
              className="om-row"
              style={{ animationDelay: `${i * 900 + 200}ms` }}
            >
              <span className="om-row-no hero-num">{`0${i + 1}`}</span>
              <span className="om-row-name display-en">{m.name}</span>
              <span className="om-row-line" />
              <span className="om-row-domain">
                <span className="om-domain-cn serif-cn">{m.domain}</span>
                <span className="om-domain-en label-mono">for {m.en}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  /* ─────────── step 2 — punchline: truths, but locked to ONE domain ────── */
  if (step === 2) {
    return (
      <div className="om-scene om-s2 scene-pad">
        <div className="om-head">
          <div className="kicker">every one shares it · the same flaw</div>
          <h2 className="om-head-h serif-cn">
            All hold real truths,<br />
            but each is <span className="om-em">locked to one domain</span>
          </h2>
        </div>

        <div className="om-matrix-wrap">
          <div className="om-matrix" role="presentation">
            <div className="om-mx-corner label-mono">model · domain</div>
            {DOMAINS.map((d) => (
              <div key={`h${d}`} className="om-mx-colhead serif-cn">{d}</div>
            ))}
            {MODELS.map((m, ri) => (
              <div key={m.name} className="om-mx-rowwrap" style={{ animationDelay: `${ri * 220 + 150}ms` }}>
                <div className="om-mx-rowhead display-en">{m.name}</div>
                {DOMAINS.map((d) => (
                  <div
                    key={`${m.name}-${d}`}
                    className={`om-mx-cell${m.domain === d ? " is-on" : ""}`}
                  >
                    {m.domain === d && <span className="om-mx-dot" />}
                  </div>
                ))}
              </div>
            ))}
          </div>
          <p className="om-mx-note">
            Each row lights <span className="om-em">one cell</span> — the rest stay dark.
          </p>
        </div>
      </div>
    );
  }

  /* ───────── step 3 — SIGNATURE: sealed boxes vs interconnected web ────── */
  if (step === 3) {
    return (
      <div className="om-scene om-s3 scene-pad">
        <div className="om-head">
          <div className="kicker">not a stack of classes · knowledge is a web</div>
          <h2 className="om-head-h serif-cn">
            Taught as <span className="om-mute">sealed boxes</span> — it's actually <span className="om-em">a web</span>
          </h2>
        </div>

        <div className="om-split">
          {/* LEFT — sealed boxes */}
          <div className="om-boxes">
            <div className="om-panel-tag label-mono">how we're taught · sealed classes</div>
            <div className="om-box-col">
              {["Math", "English", "Science"].map((b, i) => (
                <div key={b} className="om-box" style={{ animationDelay: `${i * 180 + 100}ms` }}>
                  <span className="serif-cn">{b}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="om-vs serif-it">→</div>

          {/* RIGHT — web */}
          <div className="om-web">
            <div className="om-panel-tag label-mono">how it really works · one web</div>
            <svg className="om-web-svg" viewBox="0 0 760 600" preserveAspectRatio="xMidYMid meet">
              {WEB_EDGES.map(([a, b], i) => {
                const na = nodeOf(a);
                const nb = nodeOf(b);
                return (
                  <line
                    key={`${a}-${b}`}
                    className="om-edge"
                    x1={na.x} y1={na.y} x2={nb.x} y2={nb.y}
                    pathLength={1}
                    style={{ animationDelay: `${i * 130 + 500}ms` }}
                  />
                );
              })}
              {WEB_NODES.map((n, i) => (
                <g key={n.id} className="om-node" style={{ animationDelay: `${i * 120 + 150}ms` }}>
                  <circle cx={n.x} cy={n.y} r={46} className="om-node-disc" />
                  <text x={n.x} y={n.y} className="om-node-label">{n.id}</text>
                </g>
              ))}
            </svg>
          </div>
        </div>
      </div>
    );
  }

  /* ───────── step 4 — progressive list: three broken archetypes ────────── */
  if (step === 4) {
    return (
      <div className="om-scene om-s4 scene-pad">
        <div className="om-head">
          <div className="kicker">max one axis, lose the rest · developed on one axis</div>
          <h2 className="om-head-h serif-cn">
            One axis maxed, <span className="om-em">the rest empty</span>
          </h2>
        </div>

        <div className="om-arch-row">
          {ARCHETYPES.map((a, i) => (
            <div key={a.who} className="om-arch" style={{ animationDelay: `${i * 1200 + 200}ms` }}>
              <div className="om-arch-who display-en">{a.who}</div>
              <div className="om-bar">
                <span className="om-bar-k label-mono">{a.strongLabel}</span>
                <div className="om-bar-track">
                  <div
                    className="om-bar-fill is-strong"
                    style={{ width: `${a.strong}%`, animationDelay: `${i * 1200 + 500}ms` }}
                  />
                </div>
              </div>
              <div className="om-bar">
                <span className="om-bar-k label-mono">{a.weakLabel}</span>
                <div className="om-bar-track">
                  <div
                    className="om-bar-fill is-weak"
                    style={{ width: `${a.weak}%`, animationDelay: `${i * 1200 + 700}ms` }}
                  />
                </div>
              </div>
              <div className="om-arch-flaw serif-cn">{a.flaw}</div>
            </div>
          ))}
        </div>

        <p className="om-land" style={{ animationDelay: "4200ms" }}>
          Truly <span className="om-em">developed across the board</span> — extremely rare.
        </p>
      </div>
    );
  }

  /* ───────── step 5 — contrast: cross-domain models predate the web ────── */
  return (
    <div className="om-scene om-s5 scene-pad">
      <div className="om-head">
        <div className="kicker">links a few, but too old · before the internet</div>
        <h2 className="om-head-h serif-cn">
          Old models that link a few domains —<br />
          <span className="om-em">predate the internet, predate AI</span>
        </h2>
      </div>

      <div className="om-time">
        <div className="om-time-axis">
          <span className="om-time-line" />
          <span className="om-tick is-old" style={{ left: "6%", animationDelay: "200ms" }}>
            <span className="om-tick-dot" />
            <span className="om-tick-cn serif-cn">Greek Philosophy</span>
            <span className="om-tick-en label-mono">~400 BC</span>
          </span>
          <span className="om-tick" style={{ left: "70%", animationDelay: "900ms" }}>
            <span className="om-tick-dot" />
            <span className="om-tick-cn serif-cn">Internet</span>
            <span className="om-tick-en label-mono">1990s</span>
          </span>
          <span className="om-tick" style={{ left: "90%", animationDelay: "1200ms" }}>
            <span className="om-tick-dot" />
            <span className="om-tick-cn serif-cn">AI</span>
            <span className="om-tick-en label-mono">now</span>
          </span>
          <span className="om-bracket" style={{ animationDelay: "1500ms" }}>
            all came after it
          </span>
        </div>
      </div>

      <div className="om-money" style={{ animationDelay: "1900ms" }}>
        <span className="om-money-chip serif-cn">money</span>
        <span className="om-money-note">
          Barely touched — yet it <span className="om-em">runs most people's entire lives</span>.
        </span>
      </div>
    </div>
  );
}
