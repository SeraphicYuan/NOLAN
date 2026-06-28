// Cover.tsx —— Article cover (lives above TOC + body + colophon, outside <Article>).
//
// Design: template D (geometric collage) for the `freddie` theme.
// A central "Claude" node with five labelled building-block satellites wired to
// it — "distinct parts, one system" at a glance. Echoes the article's subject
// without repeating the Hero text. Yellow is highlight only (freddie rule).
//
// Shell (3:4 ratio, positioning, PDF pagination) is UNTOUCHED — only the inner
// content region is replaced. All color/size/spacing via --ra-* / --mc-* tokens.

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
        borderRadius: "var(--ra-radius-md, 0)",
        border: "1px solid var(--ra-color-border, currentColor)",
        isolation: "isolate",
      }}
    >
      <CoverArt />
    </section>
  );
}

function CoverArt() {
  // The five building blocks, placed around a ring. Positions are percentages
  // of the 3:4 box so they reflow with any viewport / print scale.
  const nodes: { id: string; label: string; x: number; y: number }[] = [
    { id: "skills", label: "Skills", x: 50, y: 9 },
    { id: "prompts", label: "Prompts", x: 88, y: 33 },
    { id: "projects", label: "Projects", x: 76, y: 70 },
    { id: "subagents", label: "Subagents", x: 24, y: 70 },
    { id: "mcp", label: "MCP", x: 12, y: 33 },
  ];
  const cx = 50;
  const cy = 39; // visual centre of the diagram band (upper ~70% of cover)

  return (
    <>
      {/* faint paper grid */}
      <div
        aria-hidden="true"
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "linear-gradient(var(--ra-color-border, #e7dfce) 1px, transparent 1px), linear-gradient(90deg, var(--ra-color-border, #e7dfce) 1px, transparent 1px)",
          backgroundSize: "2.4rem 2.4rem",
          opacity: 0.35,
          zIndex: 0,
        }}
      />

      {/* connector lines (SVG spans full box, percentage coords) */}
      <svg
        aria-hidden="true"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 1 }}
      >
        {nodes.map((n) => (
          <line
            key={n.id}
            x1={cx}
            y1={cy}
            x2={n.x}
            y2={n.y}
            stroke="var(--ra-color-border-strong, #d6ccb4)"
            strokeWidth="0.4"
            strokeDasharray="1.4 1.4"
          />
        ))}
      </svg>

      {/* nodes layer */}
      <div style={{ position: "absolute", inset: 0, zIndex: 2 }}>
        {/* central Claude node */}
        <span
          style={{
            position: "absolute",
            left: `${cx}%`,
            top: `${cy}%`,
            transform: "translate(-50%, -50%)",
            background: "var(--ra-color-accent, #241c15)",
            color: "var(--ra-color-accent-contrast, #ffe01b)",
            fontFamily: "var(--ra-font-heading, Georgia, serif)",
            fontSize: "var(--ra-text-lg, 1.2rem)",
            fontWeight: 600,
            padding: "var(--ra-space-3, .75rem) var(--ra-space-5, 1.5rem)",
            borderRadius: "var(--ra-radius-full, 999px)",
            boxShadow: "3px 3px 0 var(--mc-yellow, #ffe01b)",
            whiteSpace: "nowrap",
          }}
        >
          Claude
        </span>

        {/* satellite nodes */}
        {nodes.map((n) => {
          const isSubject = n.id === "skills";
          return (
            <span
              key={n.id}
              style={{
                position: "absolute",
                left: `${n.x}%`,
                top: `${n.y}%`,
                transform: "translate(-50%, -50%)",
                background: isSubject
                  ? "var(--mc-yellow, #ffe01b)"
                  : "var(--ra-color-bg, #fff)",
                color: "var(--ra-color-heading, #1d160f)",
                border: `1px solid ${
                  isSubject
                    ? "var(--ra-color-heading, #1d160f)"
                    : "var(--ra-color-border-strong, #d6ccb4)"
                }`,
                fontFamily: "var(--ra-font-label, sans-serif)",
                fontSize: "var(--ra-text-sm, .85rem)",
                fontWeight: isSubject ? 700 : 500,
                letterSpacing: "0.01em",
                padding: "var(--ra-space-2, .5rem) var(--ra-space-4, 1rem)",
                borderRadius: "var(--ra-radius-full, 999px)",
                whiteSpace: "nowrap",
              }}
            >
              {n.label}
            </span>
          );
        })}
      </div>

      {/* text band — distinct from Hero (hook, not anchor) */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 3,
          padding:
            "var(--ra-space-6, 2rem) var(--ra-space-7, 3rem) var(--ra-space-7, 3rem)",
          display: "grid",
          gap: "var(--ra-space-2, .5rem)",
          background:
            "linear-gradient(to top, var(--ra-color-bg, #fff) 62%, transparent)",
        }}
      >
        <span
          style={{
            fontFamily: "var(--ra-font-label, sans-serif)",
            fontSize: "var(--ra-text-xs, .74rem)",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--ra-color-muted, #6f6356)",
          }}
        >
          The Claude agentic stack
        </span>
        <h1
          style={{
            margin: 0,
            fontFamily: "var(--ra-font-heading, Georgia, serif)",
            fontSize: "clamp(2rem, 9vw, var(--ra-text-4xl, 3rem))",
            lineHeight: 1.02,
            fontWeight: 600,
            color: "var(--ra-color-heading, #1d160f)",
          }}
        >
          Skills,
          <br />
          <span style={{ boxShadow: "inset 0 -0.34em 0 var(--mc-yellow, #ffe01b)" }}>
            explained.
          </span>
        </h1>
        <p
          style={{
            margin: 0,
            fontFamily: "var(--ra-font-body, sans-serif)",
            fontSize: "var(--ra-text-base, 1.06rem)",
            color: "var(--ra-color-text, #2c241c)",
            maxWidth: "26ch",
            lineHeight: 1.4,
          }}
        >
          Five building blocks, one system — and how to know which to reach for.
        </p>
      </div>
    </>
  );
}
