// Cover.tsx — HUMAN 3.0 cover, bodoni (Didone broadsheet): hairline rules, the
// four-quadrant map as the visual hook, big Playfair title. All --ra-* tokens.
export function Cover() {
  return (
    <section
      className="ra-cover"
      aria-label="Article cover"
      data-ra-cover=""
      style={{
        position: "relative",
        width: "100%",
        maxWidth: "min(100%, 48rem, calc((100vh - 8rem) * 3 / 4))",
        margin: "0 auto var(--ra-space-7, 3rem) auto",
        aspectRatio: "3 / 4",
        overflow: "hidden",
        background: "transparent",
        color: "var(--ra-color-fg, inherit)",
        border: "1px solid var(--ra-color-heading, #0a0908)",
        isolation: "isolate",
      }}
    >
      <CoverArt />
    </section>
  );
}

const ink = "var(--ra-color-heading, #0a0908)";
const muted = "var(--ra-color-muted, #6b6860)";
const serif = "var(--ra-font-heading, 'Playfair Display', Georgia, serif)";
const label = "var(--ra-font-label, var(--ra-font-body, serif))";

function CoverArt() {
  const cells: { q: string; tag: string }[] = [
    { q: "Mind", tag: "personal · mental" },
    { q: "Spirit", tag: "collective · mental" },
    { q: "Body", tag: "personal · physical" },
    { q: "Vocation", tag: "collective · physical" },
  ];
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "grid",
        gridTemplateRows: "auto 1fr auto",
        padding: "var(--ra-space-6, 2rem) var(--ra-space-6, 2rem) var(--ra-space-7, 3rem)",
        gap: "var(--ra-space-4, 1rem)",
      }}
    >
      {/* masthead: double rule + small-caps kicker */}
      <div style={{ display: "grid", gap: "var(--ra-space-2, .5rem)" }}>
        <div style={{ borderTop: `3px solid ${ink}`, borderBottom: `1px solid ${ink}`, height: "5px" }} />
        <span
          style={{
            fontFamily: label,
            fontSize: "var(--ra-text-xs, .74rem)",
            letterSpacing: "0.28em",
            textTransform: "uppercase",
            color: muted,
            textAlign: "center",
          }}
        >
          A Map To The Top 1%
        </span>
      </div>

      {/* the four-quadrant map — hairline cross, labelled cells */}
      <div style={{ display: "grid", placeItems: "center" }}>
        <div
          style={{
            width: "min(92%, 22rem)",
            aspectRatio: "1 / 1",
            border: `1.5px solid ${ink}`,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gridTemplateRows: "1fr 1fr",
          }}
        >
          {cells.map((c, i) => (
            <div
              key={c.q}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: "0.2rem",
                textAlign: "center",
                padding: "var(--ra-space-3, .75rem)",
                borderRight: i % 2 === 0 ? `1px solid ${ink}` : "none",
                borderBottom: i < 2 ? `1px solid ${ink}` : "none",
              }}
            >
              <span style={{ fontFamily: serif, fontSize: "var(--ra-text-2xl, 1.9rem)", fontWeight: 900, color: ink, lineHeight: 1 }}>
                {c.q}
              </span>
              <span style={{ fontFamily: label, fontSize: "0.6rem", letterSpacing: "0.14em", textTransform: "uppercase", color: muted }}>
                {c.tag}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* title block */}
      <div style={{ display: "grid", gap: "var(--ra-space-2, .5rem)", textAlign: "center" }}>
        <div style={{ borderTop: `1px solid ${ink}`, height: 0 }} />
        <h1
          style={{
            margin: 0,
            fontFamily: serif,
            fontWeight: 900,
            fontSize: "clamp(2.6rem, 13vw, 5rem)",
            lineHeight: 0.92,
            letterSpacing: "-0.01em",
            color: ink,
          }}
        >
          HUMAN&nbsp;3.0
        </h1>
        <span
          style={{
            fontFamily: label,
            fontSize: "var(--ra-text-xs, .74rem)",
            letterSpacing: "0.28em",
            textTransform: "uppercase",
            color: muted,
          }}
        >
          Dan Koe
        </span>
      </div>
    </div>
  );
}
