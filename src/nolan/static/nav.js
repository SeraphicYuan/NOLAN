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
      { id: "studio", label: "Studio", href: "/studio" },
      { id: "script-styles", label: "Script Styles", href: "/script-styles" },
      { id: "script-projects", label: "Script Projects", href: "/script-projects" },
      { id: "video-styles", label: "Video Styles", href: "/video-styles" },
    ]},
    { title: "Assets", items: [
      { id: "library", label: "Library", href: "/library" },
      { id: "clips", label: "Clips", href: "/clips" },
      { id: "voices", label: "Voices", href: "/voices" },
    ]},
    { title: "Produce", items: [
      { id: "tts", label: "TTS Studio", href: "/tts" },
      { id: "scenes", label: "Scenes", href: "/scenes" },
      { id: "lottie", label: "Lottie", href: "/lottie" },
      { id: "comfyui", label: "ComfyUI", href: "/comfyui" },
    ]},
    { title: "Share", items: [
      { id: "publish", label: "Publish", href: "/publish" },
      { id: "showcase", label: "Showcase", href: "/showcase" },
    ]},
    { title: "System", items: [
      { id: "agents", label: "Agents", href: "/agents" },
      { id: "settings", label: "Settings", href: "/settings" },
    ]},
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
    html += '<nav class="nolan-navgroups">';
    groups.forEach(function (g) {
      if (g.title) html += '<div class="nolan-section">' + g.title + "</div>";
      g.items.forEach(function (l) {
        html += '<a class="nolan-link' + (l.id === active ? " active" : "") +
          '" href="' + l.href + '">' + l.label + "</a>";
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
