// Injects a consistent NOLAN top-nav into any hub page.
// Usage: <script src="/static/nav.js" data-active="library"></script>
(function () {
  var script = document.currentScript;
  var active = script && script.getAttribute("data-active");

  var links = [
    { id: "home", label: "Hub", href: "/" },
    { id: "studio", label: "Studio", href: "/studio" },
    { id: "library", label: "Library", href: "/library" },
    { id: "clips", label: "Clips", href: "/clips" },
    { id: "script-styles", label: "Script Styles", href: "/script-styles" },
    { id: "script-projects", label: "Script Projects", href: "/script-projects" },
    { id: "scenes", label: "Scenes", href: "/scenes" },
    { id: "showcase", label: "Showcase", href: "/showcase" },
    { id: "comfyui", label: "ComfyUI", href: "/comfyui" },
    { id: "agents", label: "Agents", href: "/agents" },
    { id: "settings", label: "Settings", href: "/settings" },
  ];

  var nav = document.createElement("nav");
  nav.className = "nolan-nav";
  var html = '<a class="brand" href="/">NOLAN</a>';
  links.forEach(function (l) {
    html += '<a class="navlink' + (l.id === active ? " active" : "") + '" href="' + l.href + '">' + l.label + "</a>";
  });
  html += '<span class="spacer"></span>';
  html += '<span class="svc" id="svc-render"><span class="dot" id="svc-render-dot"></span>render :3010</span>';
  nav.innerHTML = html;
  document.body.insertBefore(nav, document.body.firstChild);

  // Service-down banner (render-service health).
  var banner = document.createElement("div");
  banner.className = "nolan-banner hidden";
  banner.id = "nolan-banner";
  document.body.insertBefore(banner, nav.nextSibling);

  function checkServices() {
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
  checkServices();
  setInterval(checkServices, 15000);
})();
