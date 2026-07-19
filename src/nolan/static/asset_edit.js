/* Shared per-asset quick-edit subsystem — crop / trim / effects / remove-bg / cleanup (single + batch).
   Loaded by BOTH /hyperframes (hf_scenes.html) and /pool (pool.html). Fully self-contained: its own
   $/esc/toast/jget/jpost, and it self-injects its modal markup + CSS. All edits hit the comp-scoped
   /api/hf/asset/* routes with a comp-relative `path` (assets/…).

   Page config via window.AE_ENV (all optional):
     comp()        -> current HF comp id           (fallback: window.COMP)
     listAssets()  -> [{path, kind, name}]          for the batch-cleanup picker
     onEdited()    -> called after any successful edit (page reloads its pool / inspector)

   Public API: AssetEdit.init() · AssetEdit.actions(path, kind) -> the "✎ edit" button HTML ·
   AssetEdit.openMenu(e, path, kind) · AssetEdit.openCleanupReview(). The rest are inline-handler targets. */
(function () {
  "use strict";
  const ENV = () => window.AE_ENV || {};
  const comp = () => (ENV().comp ? ENV().comp() : (window.COMP || ""));
  const listAssets = () => (ENV().listAssets ? ENV().listAssets() : []);
  let AE_V = 0;                                       // cache-bust version, bumped after an in-place edit
  const onEdited = () => { AE_V++; if (ENV().onEdited) return ENV().onEdited(); };

  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toast = (m, k) => (window.toast ? window.toast(m, k) : console.log("[asset-edit]", k || "", m));
  async function jget(u) { const r = await fetch(u); if (!r.ok) throw new Error((await r.text()).slice(0, 200)); return r.json(); }
  async function jpost(u, b) { const r = await fetch(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }); if (!r.ok) { let d; try { d = (await r.json()).detail; } catch { d = r.status; } throw new Error(d); } return r.json(); }
  const assetUrl = p => `/api/hf/asset-file?comp=${encodeURIComponent(comp())}&path=${encodeURIComponent(p)}&v=${AE_V}`;
  const assetThumbUrl = p => `/api/hf/asset-thumb?comp=${encodeURIComponent(comp())}&path=${encodeURIComponent(p)}&v=${AE_V}`;
  const assetFrameUrl = (p, t) => `/api/hf/asset-frame?comp=${encodeURIComponent(comp())}&path=${encodeURIComponent(p)}&t=${Math.max(0, t).toFixed(3)}&v=${AE_V}`;

  let QE_OPS = {}, CATALOG = null;
  async function catalog() { if (!CATALOG) { try { CATALOG = await jget("/api/hf/catalog"); } catch { CATALOG = {}; } } return CATALOG; }

  // ---- the "✎ edit" affordance: one button → a registry-driven popover (fixed, escapes overflow) ----
  const QE_ICONS = { crop: "⛶", trim: "✂", remove_bg: "◐", treat: "✦", cleanup: "🧹" };
  const QE_HANDLERS = { crop: openCrop, trim: openTrim, remove_bg: removeBg, treat: openTreat, cleanup: cleanupAsset };
  let QE_MENU_FOR = null;
  function assetActions(path, kind) {
    const any = Object.keys(QE_HANDLERS).some(op => QE_OPS[op] && QE_OPS[op].media.includes(kind));
    return any ? `<button class="qe-edit" title="Edit this asset — crop, trim, background, effects, clean up" onclick='event.stopPropagation();AssetEdit.openMenu(event,${JSON.stringify(path)},"${kind}")'>✎ edit</button>` : "";
  }
  function openQeMenu(e, path, kind) {
    e.stopPropagation();
    const menu = $("#qe-menu"); if (!menu) return;
    QE_MENU_FOR = { path, kind };
    const ops = Object.keys(QE_HANDLERS).filter(op => QE_OPS[op] && QE_OPS[op].media.includes(kind));
    menu.innerHTML = ops.map(op => `<button class="qe-item" data-op="${op}">${QE_ICONS[op] || "•"} ${esc(QE_OPS[op].label)}</button>`).join("");
    const r = e.currentTarget.getBoundingClientRect();
    menu.style.display = "block";
    const mw = menu.offsetWidth || 170, mh = menu.offsetHeight || 40;
    const left = Math.max(4, Math.min(r.left, window.innerWidth - mw - 8));
    let top = r.bottom + 4; if (top + mh > window.innerHeight) top = Math.max(4, r.top - mh - 4);
    menu.style.left = left + "px"; menu.style.top = top + "px";
  }
  function closeQeMenu() { const m = $("#qe-menu"); if (m) m.style.display = "none"; QE_MENU_FOR = null; }
  function wireQeMenu() {
    const m = $("#qe-menu"); if (!m) return;
    m.addEventListener("click", e => {
      const b = e.target.closest(".qe-item"); if (!b || !QE_MENU_FOR) return;
      const ctx = QE_MENU_FOR, fn = QE_HANDLERS[b.dataset.op]; closeQeMenu();
      if (fn) fn(ctx.path, ctx.kind);
    });
    document.addEventListener("click", () => closeQeMenu());
    window.addEventListener("scroll", () => closeQeMenu(), true);
  }

  // ---- Crop: drag a rectangle → crop to a new pool asset or in place ----
  let CROP = null;
  function openCrop(path, kind) {
    const stage = $("#crop-stage");
    CROP = { path, kind, rect: null, natW: 0, natH: 0 };
    $("#crop-name").textContent = path.split("/").pop();
    $("#crop-newname").value = (path.split("/").pop().replace(/\.[^.]+$/, "")) + "_crop";
    $("#crop-result").textContent = ""; $("#crop-sel").style.display = "none"; $("#crop-dims").textContent = "full frame";
    const old = stage.querySelector("img,video"); if (old) old.remove();
    const el = document.createElement(kind === "video" ? "video" : "img");
    el.src = assetUrl(path);
    if (kind === "video") { el.controls = true; el.muted = true; el.addEventListener("loadedmetadata", () => { CROP.natW = el.videoWidth; CROP.natH = el.videoHeight; }); }
    else { el.addEventListener("load", () => { CROP.natW = el.naturalWidth; CROP.natH = el.naturalHeight; }); }
    stage.insertBefore(el, $("#crop-sel"));
    $("#cropModal").style.display = "flex";
  }
  function closeCrop() { $("#cropModal").style.display = "none"; CROP = null; }
  function cropReset() { if (!CROP) return; CROP.rect = null; $("#crop-sel").style.display = "none"; $("#crop-dims").textContent = "full frame"; }
  function _cropMediaBox() {
    const el = $("#crop-stage").querySelector("img,video"); if (!el) return null;
    const s = $("#crop-stage").getBoundingClientRect(), m = el.getBoundingClientRect();
    return { el, offX: m.left - s.left, offY: m.top - s.top, w: m.width, h: m.height };
  }
  function bindCropDrag() {
    const stage = $("#crop-stage"); if (!stage) return;
    let start = null;
    stage.addEventListener("mousedown", e => {
      const b = _cropMediaBox(); if (!b || !CROP) return;
      const x = e.clientX - stage.getBoundingClientRect().left, y = e.clientY - stage.getBoundingClientRect().top;
      start = { x: Math.max(b.offX, Math.min(x, b.offX + b.w)), y: Math.max(b.offY, Math.min(y, b.offY + b.h)) };
    });
    window.addEventListener("mousemove", e => {
      if (!start || !CROP) return;
      const b = _cropMediaBox(); if (!b) return;
      const sr = stage.getBoundingClientRect();
      const cx = Math.max(b.offX, Math.min(e.clientX - sr.left, b.offX + b.w));
      const cy = Math.max(b.offY, Math.min(e.clientY - sr.top, b.offY + b.h));
      const x = Math.min(start.x, cx), y = Math.min(start.y, cy), w = Math.abs(cx - start.x), h = Math.abs(cy - start.y);
      const sel = $("#crop-sel"); sel.style.display = "block";
      sel.style.left = x + "px"; sel.style.top = y + "px"; sel.style.width = w + "px"; sel.style.height = h + "px";
      CROP.rect = { x: x - b.offX, y: y - b.offY, w, h, dispW: b.w, dispH: b.h };
      const sc = (CROP.natW || b.w) / b.w;
      $("#crop-dims").textContent = `${Math.round(w * sc)} × ${Math.round(h * sc)} px`;
    });
    window.addEventListener("mouseup", () => { start = null; });
  }
  async function applyCrop(mode) {
    if (!CROP) return;
    if (!CROP.rect || CROP.rect.w < 4 || CROP.rect.h < 4) { $("#crop-result").textContent = "Drag a crop region on the asset first."; return; }
    const sc = (CROP.natW || CROP.rect.dispW) / CROP.rect.dispW;
    const params = { x: Math.round(CROP.rect.x * sc), y: Math.round(CROP.rect.y * sc), w: Math.round(CROP.rect.w * sc), h: Math.round(CROP.rect.h * sc) };
    $("#crop-result").textContent = "cropping…";
    try {
      const r = await jpost("/api/hf/asset-quickedit", { comp: comp(), path: CROP.path, op: "crop", params, mode, name: $("#crop-newname").value || null });
      await onEdited();
      $("#crop-result").innerHTML = `<span style="color:#30a46c">✓ ${mode === "inplace" ? "cropped in place (revertable)" : "new asset: " + r.name}</span>`;
      if (mode === "inplace") closeCrop();
    } catch (e) { $("#crop-result").innerHTML = `<span style="color:#e5484d">crop failed: ${esc(e.message)}</span>`; }
  }

  // ---- Trim: mark in/out on a scrubber → cut the range ----
  let TRIM = null;
  function openTrim(path) {
    TRIM = { path };
    $("#trim-name").textContent = path.split("/").pop();
    $("#trim-newname").value = path.split("/").pop().replace(/\.[^.]+$/, "") + "_trim";
    $("#trim-result").textContent = "";
    const v = $("#trim-video"); v.src = assetUrl(path);
    v.onloadedmetadata = () => { $("#trim-in").value = 0; $("#trim-out").value = (v.duration || 0).toFixed(1); trimLen(); };
    v.ontimeupdate = () => { $("#trim-now").textContent = v.currentTime.toFixed(1); };
    $("#trimModal").style.display = "flex";
  }
  function closeTrim() { $("#trimModal").style.display = "none"; const v = $("#trim-video"); v.pause(); v.src = ""; TRIM = null; }
  function trimMark(which) { $("#trim-" + which).value = $("#trim-video").currentTime.toFixed(1); trimLen(); }
  function trimLen() { $("#trim-len").textContent = Math.max(0, (parseFloat($("#trim-out").value) || 0) - (parseFloat($("#trim-in").value) || 0)).toFixed(1); }
  async function applyTrim(mode) {
    if (!TRIM) return;
    const a = parseFloat($("#trim-in").value), b = parseFloat($("#trim-out").value);
    if (!(b > a)) { $("#trim-result").textContent = "Out must be after in."; return; }
    $("#trim-result").textContent = "trimming…";
    try {
      const r = await jpost("/api/hf/asset-quickedit", { comp: comp(), path: TRIM.path, op: "trim", params: { start: a, end: b }, mode, name: $("#trim-newname").value || null });
      await onEdited();
      $("#trim-result").innerHTML = `<span style="color:#30a46c">✓ ${mode === "inplace" ? "trimmed in place (revertable)" : "new asset: " + r.name}</span>`;
      if (mode === "inplace") closeTrim();
    } catch (e) { $("#trim-result").innerHTML = `<span style="color:#e5484d">trim failed: ${esc(e.message)}</span>`; }
  }

  // ---- Effects ("treat") with a LIVE CSS preview → baked new asset ----
  let TREATCTX = null;
  async function openTreat(path, kind) {
    const fx = (await catalog()).effects || {};
    const items = Object.entries(fx).filter(([id, m]) => m.bakeable);
    if (!items.length) { toast("No bakeable effects in the catalog", "err"); return; }
    TREATCTX = { path, kind };
    const fams = {};
    for (const [id, m] of items) (fams[m.family] = fams[m.family] || []).push([id, m]);
    const groups = Object.entries(fams).map(([fam, list]) =>
      `<div style="margin:6px 0"><div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#8a8a8a;margin:3px 0">${fam}</div>` +
      list.map(([id, m]) => `<label style="display:inline-flex;align-items:center;gap:5px;margin:3px 12px 3px 0;font-size:13px;cursor:pointer" title="${esc(m.purpose || "")}"><input type="checkbox" value="${id}" onchange="AssetEdit.updateTreatPreview()">${id}${(m.method === "blend_overlay" && m.stocked === false) ? " (no plate)" : ""}</label>`).join("") +
      `</div>`).join("");
    const base = kind === "video"
      ? `<video id="tp-base" src="${assetUrl(path)}" muted loop autoplay playsinline style="width:100%;height:100%;object-fit:cover"></video>`
      : `<img id="tp-base" src="${assetUrl(path)}" style="width:100%;height:100%;object-fit:cover">`;
    const ov = document.createElement("div");
    ov.id = "treatModal";
    ov.style = "position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:9999;display:flex;align-items:center;justify-content:center";
    ov.innerHTML = `<div style="background:#1c1c20;color:#eaeaea;border:1px solid #3a3a3f;border-radius:10px;padding:16px 18px;width:560px;max-width:92vw;max-height:90vh;overflow:auto;box-shadow:0 14px 44px rgba(0,0,0,.55)">
      <div style="font-weight:600;font-size:15px;margin-bottom:8px">Effects &rarr; new asset</div>
      <div id="treatPreview" style="position:relative;width:100%;aspect-ratio:16/9;background:#000;border-radius:8px;overflow:hidden">${base}<div id="tp-overlays" style="position:absolute;inset:0;pointer-events:none"></div></div>
      <div style="font-size:11px;color:#888;margin:6px 0 8px">Live preview (a CSS approximation of the bake). A fire/rain overlay on an image makes a short video. New pool asset; original kept.</div>
      ${groups}
      <div style="margin-top:12px;display:flex;gap:8px;justify-content:flex-end">
        <button class="btn ghost" onclick="AssetEdit.closeTreat()">Cancel</button>
        <button class="btn ghost" onclick="AssetEdit.applyTreatPreview()" title="Bake a fast low-res sample so you see the REAL ffmpeg result">Preview result</button>
        <button class="btn" onclick="AssetEdit.applyTreat()">Apply</button>
      </div></div>`;
    ov.addEventListener("click", e => { if (e.target === ov) closeTreat(); });
    document.body.appendChild(ov);
    updateTreatPreview();
  }
  function updateTreatPreview() {
    const _b = document.getElementById("tp-baked"); if (_b) _b.remove();
    const fx = (CATALOG || {}).effects || {};
    const ids = [...document.querySelectorAll("#treatModal input:checked")].map(c => c.value);
    const base = document.getElementById("tp-base");
    if (base) base.style.filter = ids.map(id => (fx[id] || {}).css).filter(Boolean).join(" ");
    const ovc = document.getElementById("tp-overlays");
    if (!ovc) return;
    ovc.innerHTML = "";
    for (const id of ids) {
      const m = fx[id] || {};
      if (m.method !== "blend_overlay") continue;
      let el;
      if (m.css_bg) { el = document.createElement("div"); el.style.background = m.css_bg; el.style.backgroundSize = "cover"; }
      else if (m.plate && m.stocked) { el = document.createElement("video"); el.src = "/api/hf/overlay-plate?tag=" + encodeURIComponent(m.plate); el.muted = true; el.loop = true; el.autoplay = true; el.playsInline = true; el.style.width = "100%"; el.style.height = "100%"; el.style.objectFit = "cover"; }
      else continue;
      el.style.position = "absolute"; el.style.inset = "0";
      el.style.mixBlendMode = m.blend || "normal";
      el.style.opacity = (m.opacity != null ? m.opacity : 1);
      ovc.appendChild(el);
      if (el.play) el.play().catch(() => {});
    }
  }
  function closeTreat() { const m = document.getElementById("treatModal"); if (m) m.remove(); TREATCTX = null; }
  async function applyTreat() {
    if (!TREATCTX) return;
    const ids = [...document.querySelectorAll("#treatModal input:checked")].map(c => c.value);
    if (!ids.length) { toast("Pick at least one effect", "err"); return; }
    const path = TREATCTX.path;
    closeTreat();
    toast("Baking " + ids.join("+") + "… (a video may take a moment)", "ok");
    try {
      const r = await jpost("/api/hf/asset-quickedit", { comp: comp(), path, op: "treat", params: { effects: ids }, mode: "new" });
      await onEdited();
      toast("Baked → " + (r.name || "new asset") + " ✓", "ok");
    } catch (e) { toast("Bake failed: " + e.message, "err"); }
  }
  async function applyTreatPreview() {
    if (!TREATCTX) return;
    const ids = [...document.querySelectorAll("#treatModal input:checked")].map(c => c.value);
    if (!ids.length) { toast("Pick an effect first", "err"); return; }
    const box = document.getElementById("treatPreview");
    let baked = document.getElementById("tp-baked");
    if (baked) baked.remove();
    baked = document.createElement("div"); baked.id = "tp-baked";
    baked.style.cssText = "position:absolute;inset:0;background:#000;display:flex;align-items:center;justify-content:center;color:#bbb;font-size:12px;z-index:2";
    baked.textContent = "baking preview…";
    box.appendChild(baked);
    try {
      const r = await fetch("/api/hf/asset-treat-preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ comp: comp(), path: TREATCTX.path, effects: ids }) });
      if (!r.ok) throw new Error((await r.text()).slice(0, 160));
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const isVid = (blob.type || "").startsWith("video");
      baked.innerHTML = (isVid
        ? `<video src="${url}" autoplay muted loop playsinline style="width:100%;height:100%;object-fit:cover"></video>`
        : `<img src="${url}" style="width:100%;height:100%;object-fit:cover">`)
        + `<div style="position:absolute;top:6px;left:6px;background:rgba(0,0,0,.65);color:#fff;font-size:10px;padding:2px 7px;border-radius:4px">baked result</div>`;
    } catch (e) { baked.textContent = "preview failed: " + e.message; }
  }

  // ---- Remove background: a background job (rembg) → poll → refresh ----
  async function removeBg(path) {
    let job;
    try { job = await jpost("/api/hf/asset-removebg", { comp: comp(), path }); }
    catch (e) { toast("remove-bg failed to start: " + e.message, "err"); return; }
    toast("removing background… (see Background Jobs)", "ok");
    const poll = setInterval(async () => {
      let j; try { j = await jget("/api/jobs/" + job.job_id); } catch { return; }
      if (j.status === "done") { clearInterval(poll); await onEdited(); toast("cutout ready: " + ((j.result || {}).name || ""), "ok"); }
      else if (j.status === "error") { clearInterval(poll); toast("remove-bg failed: " + (j.error || ""), "err"); }
    }, 1500);
  }

  // ---- Composite auto-cleanup (single) ----
  async function cleanupAsset(path, kind) {
    const detects = "a corner logo, burned-in captions" + (kind === "video" ? ", and stray head/tail frames" : "");
    if (!window.confirm(`Auto-clean "${path.split("/").pop()}"?\n\nDetects ${detects}, crops/trims them, and saves a NEW pool asset (original kept). Takes ~10–30s.`)) return;
    toast("Analyzing " + path.split("/").pop() + "… (detecting " + detects + ")");
    try {
      const r = await jpost("/api/hf/asset/cleanup", { comp: comp(), path });
      if (!r.changed) { toast("Nothing to clean — nothing detected on " + path.split("/").pop(), "ok"); return; }
      const p = r.plan, bits = [];
      if ((p.logos || []).length) bits.push("logo");
      if (p.caption) bits.push("captions");
      if (p.trim_in > 0 || (p.kind === "video" && p.trim_out < (p.dur || 0) - 0.01)) bits.push("trim");
      toast("Cleaned (" + (bits.join(", ") || "crop") + ") → " + r.name, "ok");
      await onEdited();
    } catch (e) { toast("cleanup failed: " + (e.message || e), "err"); }
  }

  // ---- Batch cleanup review ----
  let CLEANUP_PLANS = [];
  function poolMedia() {
    return listAssets().filter(a => (a.kind === "image" || a.kind === "video") && !/\.orig\.(mp4|png)$/.test(a.name) && !/_clean\.[^.]+$/.test(a.name));
  }
  function openCleanupReview() {
    const media = poolMedia();
    if (!media.length) return toast("Pool has no image/video assets to clean", "err");
    CLEANUP_PLANS = [];
    const rows = media.map(a => `<label class="cu-pick">
        <input type="checkbox" class="cu-sel" data-path="${esc(a.path)}" checked>
        <img src="${assetThumbUrl(a.path)}" loading="lazy">
        <span>${esc(a.name)}</span><span style="color:var(--text-secondary)">· ${a.kind}</span></label>`).join("");
    $("#cleanup-body").innerHTML = `<div style="font-size:12px;color:var(--text-secondary);margin-bottom:6px">Pick assets to scan (${media.length} in pool), then Analyze. Nothing changes until you Apply.</div>${rows}`;
    $("#cleanup-analyze-btn").style.display = ""; $("#cleanup-analyze-btn").disabled = false;
    $("#cleanup-apply-btn").style.display = "none";
    $("#cleanup-status").textContent = "";
    $("#cleanupModal").style.display = "flex";
  }
  function closeCleanup() { $("#cleanupModal").style.display = "none"; }
  async function runCleanupAnalyze() {
    const paths = [...document.querySelectorAll("#cleanup-body .cu-sel:checked")].map(c => c.dataset.path);
    if (!paths.length) return toast("select at least one asset", "err");
    const confirm = $("#cleanup-confirm").checked;
    $("#cleanup-analyze-btn").disabled = true;
    $("#cleanup-status").textContent = `Analyzing ${paths.length} asset(s)… detecting logo / captions / stray frames${confirm ? ", vision-confirming" : ""} — a few seconds each.`;
    try {
      const r = await jpost("/api/hf/asset/cleanup-analyze-batch", { comp: comp(), paths, confirm });
      CLEANUP_PLANS = (r.results || []).map(x => {
        const p = x.plan;
        return { ...x, apply: !x.error && !!(p && p.changed), acc: new Set(),
          autoIn: p ? (p.trim_in || 0) : 0, autoOut: p ? (p.trim_out != null ? p.trim_out : (p.dur || 0)) : 0 };
      });
      renderCleanupReview();
    } catch (e) { $("#cleanup-status").textContent = "analyze failed: " + (e.message || e); $("#cleanup-analyze-btn").disabled = false; }
  }
  function cleanupOverlay(p) {
    const pct = v => (Math.max(0, Math.min(1, v)) * 100).toFixed(2) + "%";
    let b = "";
    (p.logos || []).forEach(l => { b += `<div class="cu-ex" style="left:${pct(l.x)};top:${pct(l.y)};width:${pct(l.w)};height:${pct(l.h)}"></div>`; });
    if (p.caption) b += `<div class="cu-ex" style="left:0;top:${pct(p.caption.top)};width:100%;height:${pct(1 - p.caption.top)}"></div>`;
    if (p.crop && p.ow) { const c = p.crop; b += `<div class="cu-keep" style="left:${pct(c.x / p.ow)};top:${pct(c.y / p.oh)};width:${pct(c.w / p.ow)};height:${pct(c.h / p.oh)}"></div>`; }
    return b;
  }
  function cleanupTags(p) {
    const t = [];
    if ((p.logos || []).length) t.push(`🏷️ logo${p.logos.length > 1 ? "×" + p.logos.length : ""}`);
    if (p.caption) t.push("💬 captions");
    if (p.trim_in > 0) t.push(`✂️ head ${p.trim_in}s`);
    if (p.kind === "video" && p.trim_out < (p.dur || 0) - 0.01) t.push(`✂️ tail →${p.trim_out}s`);
    if (p.crop) t.push(`🔍 zoom ×${p.zoom}`);
    return t;
  }
  function recomputeTrim(x) {
    const p = x.plan; let ti = x.autoIn, to = x.autoOut;
    (p.trim_candidates || []).forEach((c, ci) => { if (x.acc.has(ci)) { if (c.side === "head") ti = Math.max(ti, c.t); else to = Math.min(to, c.t); } });
    p.trim_in = Math.round(ti * 1000) / 1000; p.trim_out = Math.round(to * 1000) / 1000;
    p.changed = !!p.crop || p.trim_in > 0 || (p.kind === "video" && p.trim_out < (p.dur || 0) - 0.01);
  }
  function candBlock(x, i) {
    const cands = x.plan.trim_candidates || [];
    if (!cands.length) return "";
    return `<div class="cu-cands"><div class="cu-cands-h">Ambiguous cut${cands.length > 1 ? "s" : ""} — look, then tick to trim the stray:</div>` +
      cands.map((c, ci) => {
        const lThumb = assetFrameUrl(x.path, c.t - 0.15), rThumb = assetFrameUrl(x.path, c.t + 0.15);
        const lLbl = c.side === "head" ? "stray?" : "keep", rLbl = c.side === "head" ? "keep" : "stray?";
        return `<label class="cu-cand-row"><input type="checkbox" class="cu-cand" data-i="${i}" data-ci="${ci}" ${x.acc.has(ci) ? "checked" : ""}>
          <span class="cu-cand-desc">${c.side} ${c.len}s<br><span class="cu-cand-frac">${Math.round(c.frac * 100)}% of clip</span></span>
          <span class="cu-fr ${c.side === "head" ? "stray" : ""}"><img src="${lThumb}" loading="lazy"><em>${lLbl}</em></span>
          <span class="cu-cut">✂</span>
          <span class="cu-fr ${c.side === "tail" ? "stray" : ""}"><img src="${rThumb}" loading="lazy"><em>${rLbl}</em></span></label>`;
      }).join("") + `</div>`;
  }
  function cleanupCardHTML(x, i) {
    const nm = esc(x.path.split("/").pop());
    if (x.error) return `<div class="cu-card err">${nm} — analyze failed: ${esc(x.error)}</div>`;
    const p = x.plan, actionable = !!p.changed || (p.trim_candidates || []).length > 0;
    return `<div class="cu-card${actionable ? "" : " clean"}" id="cu-card-${i}">
      <div class="cu-thumb" style="aspect-ratio:${p.ow || 16}/${p.oh || 9}"><img src="${assetThumbUrl(x.path)}">${cleanupOverlay(p)}</div>
      <div class="cu-info"><div class="cu-name">${nm}</div>
        <div class="cu-tags">${p.changed ? cleanupTags(p).join(" · ") : "✓ nothing auto-detected"}</div>
        ${candBlock(x, i)}</div>
      <label class="cu-apply">${actionable ? `<input type="checkbox" class="cu-do" data-i="${i}" ${x.apply ? "checked" : ""} ${p.changed ? "" : "disabled"}> apply` : ""}</label>
    </div>`;
  }
  function patchCleanupCard(i) {
    const x = CLEANUP_PLANS[i], p = x.plan, card = document.getElementById("cu-card-" + i);
    if (!card) return;
    card.classList.toggle("clean", !p.changed && !(p.trim_candidates || []).length);
    const tg = card.querySelector(".cu-tags"); if (tg) tg.innerHTML = p.changed ? cleanupTags(p).join(" · ") : "✓ nothing auto-detected";
    const ap = card.querySelector(".cu-do"); if (ap) { ap.checked = x.apply; ap.disabled = !p.changed; }
  }
  function cleanupApplyCount() { $("#cleanup-apply-btn").textContent = `Apply & save (${CLEANUP_PLANS.filter(x => x.apply).length})`; }
  function renderCleanupReview() {
    const nChanged = CLEANUP_PLANS.filter(x => !x.error && x.plan.changed).length;
    const nCand = CLEANUP_PLANS.filter(x => !x.error && (x.plan.trim_candidates || []).length).length;
    $("#cleanup-body").innerHTML = `<div class="cu-legend"><span class="cu-lg-ex">■</span> detected (removed) · <span class="cu-lg-keep">■</span> kept crop</div>${CLEANUP_PLANS.map(cleanupCardHTML).join("")}`;
    $("#cleanup-analyze-btn").style.display = "none";
    const ab = $("#cleanup-apply-btn"); ab.style.display = ""; ab.disabled = false;
    $("#cleanup-status").textContent = `${nChanged} of ${CLEANUP_PLANS.length} need cleanup${nCand ? ` · ${nCand} with an ambiguous cut to review` : ""} — review, untick any, then Apply.`;
    const body = $("#cleanup-body");
    body.querySelectorAll(".cu-do").forEach(cb => cb.addEventListener("change", () => { CLEANUP_PLANS[+cb.dataset.i].apply = cb.checked; cleanupApplyCount(); }));
    body.querySelectorAll(".cu-cand").forEach(cb => cb.addEventListener("change", () => {
      const i = +cb.dataset.i, ci = +cb.dataset.ci, x = CLEANUP_PLANS[i];
      cb.checked ? x.acc.add(ci) : x.acc.delete(ci);
      recomputeTrim(x); x.apply = x.plan.changed;
      patchCleanupCard(i); cleanupApplyCount();
    }));
    cleanupApplyCount();
  }
  async function applyCleanupSelected() {
    const todo = CLEANUP_PLANS.filter(x => x.apply && !x.error);
    if (!todo.length) return toast("nothing ticked to apply", "err");
    const ab = $("#cleanup-apply-btn"); ab.disabled = true;
    let done = 0, fail = 0;
    for (const x of todo) {
      $("#cleanup-status").textContent = `Applying ${done + fail + 1}/${todo.length}: ${x.path.split("/").pop()}…`;
      try { const r = await jpost("/api/hf/asset/cleanup", { comp: comp(), path: x.path, plan: x.plan }); r.changed ? done++ : fail++; }
      catch (e) { fail++; }
    }
    toast(`Cleaned ${done} asset(s)${fail ? `, ${fail} failed` : ""} → new pool assets`, fail ? "err" : "ok");
    await onEdited();
    closeCleanup();
  }

  // ---- self-injected modal markup + CSS (so both pages get them without duplicating template HTML) ----
  const MODALS = `
  <div id="ae-cropModal" class="modal ae-modal" data-modal="cropModal">
    <div class="modal-box" style="max-width:840px">
      <div class="modal-head"><b>Crop asset</b><span class="meta" id="crop-name" style="color:var(--text-secondary);font-size:12px;"></span>
        <span class="spacer"></span><button class="btn ghost mini" onclick="AssetEdit.closeCrop()">✕</button></div>
      <div class="crop-stage" id="crop-stage"><div class="crop-sel" id="crop-sel" style="display:none"></div></div>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px">
        <span style="font-size:12px;color:var(--text-secondary)">drag on the asset to select · <b id="crop-dims">full frame</b></span>
        <button class="btn ghost mini" onclick="AssetEdit.cropReset()">reset</button>
        <span style="flex:1"></span>
        <input type="text" id="crop-newname" placeholder="new asset name">
        <button class="btn ghost" onclick="AssetEdit.applyCrop('new')">Crop → new pool asset</button>
        <button class="btn" onclick="AssetEdit.applyCrop('inplace')" title="Replace this asset (original kept as a reversible backup)">Crop in place</button>
      </div>
      <div id="crop-result" style="font-size:12px;margin-top:8px"></div>
    </div>
  </div>
  <div id="ae-trimModal" class="modal ae-modal">
    <div class="modal-box" style="max-width:760px">
      <div class="modal-head"><b>Trim video</b><span class="meta" id="trim-name" style="color:var(--text-secondary);font-size:12px;"></span>
        <span class="spacer"></span><button class="btn ghost mini" onclick="AssetEdit.closeTrim()">✕</button></div>
      <video id="trim-video" controls preload="metadata" style="width:100%;max-height:56vh;background:#000;border-radius:8px;display:block"></video>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px">
        <span class="now">t = <b id="trim-now">0.0</b>s</span>
        <button class="btn ghost mini" onclick="AssetEdit.trimMark('in')">⟦ set IN</button>
        <div class="mk"><label>in</label><input type="number" id="trim-in" step="0.1" value="0"></div>
        <button class="btn ghost mini" onclick="AssetEdit.trimMark('out')">set OUT ⟧</button>
        <div class="mk"><label>out</label><input type="number" id="trim-out" step="0.1" value="0"></div>
        <span class="now">len <b id="trim-len">0.0</b>s</span>
        <span style="flex:1"></span>
        <input type="text" id="trim-newname" placeholder="new name">
        <button class="btn ghost" onclick="AssetEdit.applyTrim('new')">Trim → new pool asset</button>
        <button class="btn" onclick="AssetEdit.applyTrim('inplace')" title="Replace this video (original kept as a reversible backup)">Trim in place</button>
      </div>
      <div id="trim-result" style="font-size:12px;margin-top:8px"></div>
    </div>
  </div>
  <div id="ae-cleanupModal" class="modal ae-modal">
    <div class="modal-box" style="max-width:920px">
      <div class="modal-head"><b>🧹 Clean up pool assets</b>
        <span class="meta" style="color:var(--text-secondary);font-size:12px;">auto-detect a corner logo · burned-in captions · stray head/tail frames → crop &amp; trim to a new asset</span>
        <span class="spacer"></span><button class="btn ghost mini" onclick="AssetEdit.closeCleanup()">✕</button></div>
      <div id="cleanup-body" style="max-height:64vh;overflow:auto;margin-top:8px"></div>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px">
        <label style="font-size:12px;color:var(--text-secondary)"><input type="checkbox" id="cleanup-confirm" checked> vision confirm <span title="An OpenRouter vision model filters false detections.">ⓘ</span></label>
        <span style="flex:1"></span>
        <button class="btn ghost" id="cleanup-analyze-btn" onclick="AssetEdit.runCleanupAnalyze()">Analyze selected</button>
        <button class="btn" id="cleanup-apply-btn" onclick="AssetEdit.applyCleanupSelected()" style="display:none">Apply &amp; save</button>
      </div>
      <div id="cleanup-status" style="font-size:12px;margin-top:8px;color:var(--text-secondary)"></div>
    </div>
  </div>
  <div id="qe-menu"></div>`;

  const CSS = `
  .ae-modal.modal { position: fixed; inset: 0; background: rgba(0,0,0,0.55); display: none; align-items: center; justify-content: center; z-index: 4000; }
  .ae-modal .modal-box { background: var(--bg-secondary, #1c1c20); border: 1px solid var(--border, #333); border-radius: 14px; width: 640px; max-width: 92vw; max-height: 82vh; overflow: auto; padding: 16px; }
  .ae-modal .modal-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
  .ae-modal .modal-head .spacer { flex: 1; }
  .ae-modal .mk { display: inline-flex; align-items: center; gap: 4px; } .ae-modal .mk label { font-size: 11px; color: var(--text-secondary); } .ae-modal .now { font-size: 12px; color: var(--text-secondary); }
  #crop-stage { position: relative; width: 100%; max-height: 60vh; background: #0b0c0e repeating-conic-gradient(#15171a 0 25%, #0f1113 0 50%) 0/22px 22px; border: 1px solid var(--border, #333); border-radius: 8px; overflow: hidden; display: flex; justify-content: center; align-items: center; user-select: none; }
  #crop-stage img, #crop-stage video { max-width: 100%; max-height: 60vh; display: block; }
  #crop-sel { position: absolute; border: 2px dashed var(--accent, #4f7cff); background: rgba(79,124,255,0.12); box-shadow: 0 0 0 9999px rgba(0,0,0,0.45); pointer-events: none; }
  .qe-edit { cursor: pointer; font: inherit; font-size: 11px; padding: 2px 8px; border: 1px solid var(--border, #333); border-radius: 5px; background: var(--bg-primary, #202024); color: var(--text, #eaeaea); }
  .qe-edit:hover { border-color: var(--accent, #4f7cff); }
  .hf-actions { margin-top: 4px; }
  #qe-menu { position: fixed; z-index: 5000; display: none; min-width: 160px; background: var(--bg-primary, #202024); border: 1px solid var(--border, #333); border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,.35); padding: 4px; }
  #qe-menu .qe-item { display: block; width: 100%; text-align: left; font-size: 12px; padding: 6px 10px; border: none; background: none; color: var(--text, #eaeaea); border-radius: 5px; cursor: pointer; white-space: nowrap; }
  #qe-menu .qe-item:hover { background: var(--accent, #4f7cff); color: #fff; }
  .cu-legend{font-size:11px;color:var(--text-secondary);margin-bottom:8px} .cu-lg-ex{color:#ff5555;font-weight:700}.cu-lg-keep{color:#33dd88;font-weight:700}
  .cu-pick{display:flex;gap:8px;align-items:center;padding:4px 2px;font-size:12px} .cu-pick img{width:56px;height:32px;object-fit:cover;border-radius:4px;background:#000;flex:0 0 auto}
  .cu-card{display:flex;gap:12px;align-items:center;padding:8px;border:1px solid var(--border,#333);border-radius:8px;margin-bottom:8px} .cu-card.clean{opacity:.55}.cu-card.err{color:#d66;font-size:12px;display:block}
  .cu-thumb{position:relative;width:184px;flex:0 0 auto;background:#000;border-radius:6px;overflow:hidden} .cu-thumb img{width:100%;height:100%;object-fit:cover;display:block}
  .cu-ex{position:absolute;border:2px solid #ff5555;background:rgba(255,60,60,.20);box-sizing:border-box;pointer-events:none} .cu-keep{position:absolute;border:2px solid #33dd88;box-sizing:border-box;pointer-events:none}
  .cu-info{flex:1;font-size:12px;min-width:0} .cu-name{font-weight:600;margin-bottom:3px;word-break:break-all} .cu-tags{color:var(--text-secondary)}
  .cu-apply{font-size:12px;flex:0 0 auto;white-space:nowrap}
  .cu-cands{margin-top:6px;padding:6px 8px;border:1px dashed #e0a030;border-radius:6px;background:rgba(224,160,48,.06)} .cu-cands-h{font-size:11px;color:#e0a030;margin-bottom:5px}
  .cu-cand-row{display:flex;gap:8px;align-items:center;font-size:11px;padding:2px 0} .cu-cand-desc{flex:0 0 74px;color:var(--text-secondary);text-transform:capitalize;line-height:1.25} .cu-cand-frac{font-size:10px;opacity:.8}
  .cu-fr{position:relative;flex:0 0 auto} .cu-fr img{width:88px;height:50px;object-fit:cover;border-radius:3px;background:#000;display:block;border:1px solid var(--border,#333)} .cu-fr.stray img{border-color:#ff5555}
  .cu-fr em{position:absolute;left:2px;bottom:2px;font-style:normal;font-size:9px;padding:0 3px;border-radius:2px;background:rgba(0,0,0,.66);color:#fff} .cu-fr.stray em{background:#ff5555} .cu-cut{color:#e0a030;font-size:14px;flex:0 0 auto}`;

  let INJECTED = false, INITED = false;
  function inject() {
    if (INJECTED) return; INJECTED = true;
    const st = document.createElement("style"); st.id = "ae-style"; st.textContent = CSS; document.head.appendChild(st);
    document.body.insertAdjacentHTML("beforeend", MODALS);
    // the crop/trim/cleanup modals use their historical ids inside; expose them under those ids:
    $("#ae-cropModal").id = "cropModal"; $("#ae-trimModal").id = "trimModal"; $("#ae-cleanupModal").id = "cleanupModal";
    bindCropDrag(); wireQeMenu();
  }
  async function init() {
    if (INITED) return; INITED = true;
    inject();
    try { const d = await jget("/api/hf/quickedit-ops"); QE_OPS = d.ops || d || {}; } catch { QE_OPS = {}; }
  }

  window.AssetEdit = {
    init, actions: assetActions, openMenu: openQeMenu, openCleanupReview,
    // inline-handler targets:
    applyCrop, closeCrop, cropReset, applyTrim, closeTrim, trimMark,
    updateTreatPreview, applyTreat, applyTreatPreview, closeTreat,
    runCleanupAnalyze, applyCleanupSelected, closeCleanup,
    get ops() { return QE_OPS; },
  };
})();
