// Injects the NOLAN app shell: a grouped left sidebar (Linear/Supabase style)
// on desktop, collapsing to an off-canvas drawer on phones (<=768px).
// Usage: <script src="/static/nav.js" data-active="library"></script>
// It wraps the page's existing body content in <main> — pages need no markup
// changes; their functions and layout are preserved.
(function () {
  var script = document.currentScript;
  var active = script && script.getAttribute("data-active"); // read sync (currentScript is null later)
  var MOBILE = 768;

  // Grouped navigation. Hub stands alone; the rest are sectioned.
  var groups = [
    { items: [{ id: "home", label: "Hub", href: "/" }] },
    { title: "Create", items: [
      { id: "studio", label: "Project Dashboard", href: "/studio" },
      { id: "process", label: "New from Essay", href: "/process" },
      { id: "script-styles", label: "Script Styles", href: "/script-styles" },
      { id: "script-projects", label: "Script Projects", href: "/script-projects" },
      { id: "video-styles", label: "Video Styles", href: "/video-styles" },
      { id: "deconstruct", label: "Deconstruct", href: "/deconstruct" },
    ]},
    { title: "Assets", items: [
      { id: "library", label: "Library", href: "/library" },
      { id: "ingest", label: "Add to Library", href: "/library/add" },
      { id: "clips", label: "Clips", href: "/clips" },
      { id: "images", label: "Picture Library", href: "/images" },
      { id: "extract", label: "Extract Assets", href: "/extract" },
      { id: "broll", label: "Evocative B-roll", href: "/broll" },
      { id: "tonal-broll", label: "Tonal B-roll (gallery)", href: "/tonal-broll/" },
      { id: "voices", label: "Voices", href: "/voices" },
    ]},
    { title: "Produce", items: [
      { id: "scenes", label: "Scenes", href: "/scenes" },
      { id: "pool", label: "Asset Pool", href: "/pool" },
      { id: "lottie", label: "Lottie", href: "/lottie" },
      { id: "comfyui", label: "ComfyUI", href: "/comfyui" },
    ]},
    { title: "Share", items: [
      { id: "publish", label: "Publish", href: "/publish" },
      { id: "showcase", label: "Showcase", href: "/showcase" },
    ]},
    { title: "System", items: [
      { id: "agents", label: "Agents", href: "/agents" },
      { id: "map", label: "NOLAN Map", href: "/map" },
      { id: "taste", label: "Taste", href: "/taste" },
      { id: "skills", label: "Skills", href: "/skills" },
      { id: "settings", label: "Settings", href: "/settings" },
    ]},
  ];

  // Inline stroke icons (replace ad-hoc emoji; inherit currentColor).
  function svg(p) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + p + '</svg>';
  }
  var ICON = {
    home:   svg('<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>'),
    studio: svg('<path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/>'),
    scenes: svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18M8 5v14"/>'),
    clips:  svg('<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4L8.5 15.5M14.5 9.5L20 20"/>'),
    voices: svg('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>'),
  };

  // Bottom-tab bar (mobile only): primary destinations within thumb reach.
  var tabs = [
    { id: "home",   label: "Hub",    href: "/",        icon: ICON.home },
    { id: "studio", label: "Studio", href: "/studio",  icon: ICON.studio },
    { id: "scenes", label: "Scenes", href: "/scenes",  icon: ICON.scenes },
    { id: "clips",  label: "Clips",  href: "/clips",   icon: ICON.clips },
    { id: "voices", label: "Voices", href: "/voices",  icon: ICON.voices },
  ];

  function build() {
    var body = document.body;

    // 1) Wrap all existing page content into <main>, preserving its padding.
    var main = document.createElement("main");
    main.className = "nolan-main";
    var bcs = getComputedStyle(body);
    var pad = bcs.paddingTop + " " + bcs.paddingRight + " " + bcs.paddingBottom + " " + bcs.paddingLeft;
    while (body.firstChild) main.appendChild(body.firstChild);
    body.style.margin = "0";
    body.style.padding = "0";
    // Re-apply the page's original body padding to the content area (skip if none).
    if (/[1-9]/.test(pad)) main.style.padding = pad;

    // 2) Build the sidebar.
    var aside = document.createElement("aside");
    aside.className = "nolan-sidebar";
    var html = '<a class="nolan-brand" href="/">NOLAN</a>';
    html += '<nav class="nolan-navgroups" aria-label="Primary">';
    groups.forEach(function (g) {
      if (g.title) html += '<div class="nolan-section">' + g.title + "</div>";
      g.items.forEach(function (l) {
        var on = l.id === active;
        html += '<a class="nolan-link' + (on ? " active" : "") + '" href="' + l.href + '"' +
          (on ? ' aria-current="page"' : "") + ">" + l.label + "</a>";
      });
    });
    html += "</nav>";
    html += '<div class="nolan-rail-foot">' +
      '<span class="svc" id="svc-render"><span class="dot" id="svc-render-dot"></span>render :3010</span>' +
      "</div>";
    aside.innerHTML = html;

    // 3) Mobile top bar (brand + hamburger) + scrim.
    var topbar = document.createElement("div");
    topbar.className = "nolan-topbar";
    topbar.innerHTML =
      '<button class="nolan-burger" id="nolan-burger" aria-label="Menu" aria-expanded="false">' +
      '<span></span><span></span><span></span></button>' +
      '<a class="nolan-brand" href="/">NOLAN</a>';
    var scrim = document.createElement("div");
    scrim.className = "nolan-scrim";
    scrim.id = "nolan-scrim";

    // 4) Assemble the shell.
    body.classList.add("nolan-shell");
    body.appendChild(aside);
    body.appendChild(scrim);
    main.insertBefore(topbar, main.firstChild);
    // Service-down banner lives at the top of the content area.
    var banner = document.createElement("div");
    banner.className = "nolan-banner hidden";
    banner.id = "nolan-banner";
    main.insertBefore(banner, topbar.nextSibling);
    body.appendChild(main);

    // 5) Drawer toggle.
    function setOpen(open) {
      body.classList.toggle("nav-open", open);
      var burger = document.getElementById("nolan-burger");
      if (burger) burger.setAttribute("aria-expanded", open ? "true" : "false");
    }
    document.getElementById("nolan-burger").addEventListener("click", function () {
      setOpen(!body.classList.contains("nav-open"));
    });
    scrim.addEventListener("click", function () { setOpen(false); });
    aside.addEventListener("click", function (e) {
      if (e.target && e.target.classList.contains("nolan-link")) setOpen(false);
    });

    // 6) Mobile bottom-tab bar — primary destinations within thumb reach.
    var tabbar = document.createElement("nav");
    tabbar.className = "nolan-tabbar";
    tabbar.setAttribute("aria-label", "Primary (mobile)");
    tabbar.innerHTML = tabs.map(function (t) {
      var on = t.id === active;
      return '<a href="' + t.href + '" class="' + (on ? "active" : "") + '"' +
        (on ? ' aria-current="page"' : "") + ">" + t.icon + "<span>" + t.label + "</span></a>";
    }).join("");
    body.appendChild(tabbar);
    // Spacer so the fixed tab bar never covers page content (robust vs inline body padding).
    var spacer = document.createElement("div");
    spacer.className = "nolan-tabbar-spacer";
    main.appendChild(spacer);

    startHealth();
  }

  function startHealth() {
    function check() {
      fetch("/api/status")
        .then(function (r) { return r.json(); })
        .then(function (s) {
          var up = s && s.render_service && s.render_service.available;
          var dot = document.getElementById("svc-render-dot");
          if (dot) dot.className = "dot " + (up ? "up" : "down");
          var b = document.getElementById("nolan-banner");
          if (b) {
            if (up) { b.className = "nolan-banner hidden"; }
            else {
              b.className = "nolan-banner";
              b.textContent = "⚠ Render service (:3010) is offline — rendering & effects are unavailable. Start it with start_webui.bat or: cd render-service && node dist/server.js";
            }
          }
        })
        .catch(function () {});
    }
    check();
    setInterval(check, 15000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
