import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

// Lab-only deep-link: `?c=<chapter>&s=<step>` seeds the stepper cursor (the key
// must match useStepper's STORAGE_KEY) so a headless screenshotter can capture
// any step over file://. No-op when the params are absent.
try {
  const q = new URLSearchParams(location.search);
  if (q.has("c") || q.has("s")) {
    const cursor = { chapter: Number(q.get("c") ?? 0) | 0, step: Number(q.get("s") ?? 0) | 0 };
    localStorage.setItem("presentation-cursor-v4", JSON.stringify(cursor));
  }
} catch {
  /* ignore */
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
