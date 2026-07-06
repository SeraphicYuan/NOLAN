// Proposal harness slot — the effect-promotion GATE copies a candidate
// composition here and renders the fixed "Proposal" comp against its
// sample props. NEVER register proposals in Root directly; accept_proposal
// installs gated effects under ../promoted/. This placeholder renders a
// labeled frame so an empty harness is visibly not-a-real-effect.
import React from "react";

const Placeholder: React.FC<Record<string, unknown>> = () => (
  <div style={{
    width: "100%", height: "100%", display: "flex", alignItems: "center",
    justifyContent: "center", background: "#111", color: "#666",
    fontFamily: "monospace", fontSize: 42,
  }}>
    proposal harness — no candidate staged
  </div>
);

export default Placeholder;
