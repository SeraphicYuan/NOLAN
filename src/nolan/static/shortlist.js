/* NolanShortlist — per-project asset shortlist widget shared by the library
 * pages. It renders a project switcher (the shortlist target) into a page-
 * provided container, plus a floating tray FAB + drawer, and talks to the
 * /api/shortlist endpoints.
 *
 * Items are stored in the exact shape the /scenes asset picker consumes, so
 * "Send to essay" just opens /scenes for the project — no translation needed:
 *   { key, kind: 'image'|'clip', label, thumb, payload:{op:'add', source, ...} }
 *
 * Usage:
 *   await NolanShortlist.init({ mount: '#shortlistSwitch' });
 *   NolanShortlist.add([{ key, kind, label, thumb, payload }]);   // from action bar
 */
(function () {
  var LS_KEY = 'nolan.shortlist.project';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  var SL = {
    project: null,
    projects: [],
    items: [],
    _fab: null, _tray: null, _backdrop: null, _body: null, _badge: null, _switch: null,

    async init(opts) {
      opts = opts || {};
      this._buildTray();
      await this.loadProjects();
      this.project = localStorage.getItem(LS_KEY) || (this.projects[0] && this.projects[0].slug) || null;
      if (opts.mount) this._buildSwitch(opts.mount);
      await this.refresh();
    },

    async loadProjects() {
      try {
        var r = await fetch('/api/projects');
        var d = await r.json();
        // Prefer projects that can actually receive scenes (have a scene plan),
        // but keep all so a fresh project is still a valid target.
        this.projects = (d.projects || []).map(function (p) {
          return { slug: p.slug, name: p.name || p.slug, has_scene_plan: !!p.has_scene_plan };
        });
      } catch (e) { this.projects = []; }
    },

    _buildSwitch(mount) {
      var el = typeof mount === 'string' ? document.querySelector(mount) : mount;
      if (!el) return;
      var self = this;
      var wrap = document.createElement('span');
      wrap.className = 'ns-project-switch';
      wrap.innerHTML = '<label style="margin:0;">Essay</label>';
      var sel = document.createElement('select');
      if (!this.projects.length) {
        sel.innerHTML = '<option value="">(no projects)</option>';
        sel.disabled = true;
      } else {
        sel.innerHTML = this.projects.map(function (p) {
          return '<option value="' + esc(p.slug) + '"' + (p.slug === self.project ? ' selected' : '') +
            '>' + esc(p.name) + (p.has_scene_plan ? '' : ' (no scenes yet)') + '</option>';
        }).join('');
      }
      sel.addEventListener('change', function () { self.setProject(sel.value); });
      wrap.appendChild(sel);
      el.appendChild(wrap);
      this._switch = sel;
    },

    setProject(slug) {
      this.project = slug || null;
      if (slug) localStorage.setItem(LS_KEY, slug);
      if (this._switch && this._switch.value !== (slug || '')) this._switch.value = slug || '';
      this.refresh();
    },

    async add(items) {
      if (!this.project) {
        alert('Pick a target essay/project first (the "Essay" selector in the toolbar).');
        return false;
      }
      if (!items || !items.length) return false;
      try {
        var r = await fetch('/api/shortlist/add', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project: this.project, items: items }),
        });
        if (!r.ok) throw new Error(await r.text());
        var d = await r.json();
        this.items = d.items || [];
        this._render();
        this._flash(items.length + ' added to ' + this.project);
        return true;
      } catch (e) { alert('Add to shortlist failed: ' + e.message); return false; }
    },

    async refresh() {
      if (!this.project) { this.items = []; this._render(); return; }
      try {
        var r = await fetch('/api/shortlist?project=' + encodeURIComponent(this.project));
        var d = await r.json();
        this.items = d.items || [];
      } catch (e) { this.items = []; }
      this._render();
    },

    async remove(key) {
      if (!this.project) return;
      var r = await fetch('/api/shortlist/remove', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: this.project, keys: [key] }),
      });
      var d = await r.json(); this.items = d.items || []; this._render();
    },

    async clearAll() {
      if (!this.project || !this.items.length) return;
      if (!confirm('Clear the shortlist for ' + this.project + '?')) return;
      await fetch('/api/shortlist/clear', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: this.project }),
      });
      this.items = []; this._render();
    },

    sendToEssay() {
      if (!this.project) { alert('Pick a target essay first.'); return; }
      // The scenes picker's "Shortlist" source reads this same pool, so we just
      // land the user on the scene editor for the chosen project.
      window.location.href = '/scenes?project=' + encodeURIComponent(this.project) + '&shortlist=1';
    },

    // ---- tray DOM ----
    _buildTray() {
      var self = this;
      var fab = document.createElement('button');
      fab.className = 'ns-tray-fab';
      fab.innerHTML = '🎞 Shortlist <span class="ns-tray-badge">0</span>';
      fab.addEventListener('click', function () { self.open(); });

      var backdrop = document.createElement('div');
      backdrop.className = 'ns-tray-backdrop';
      backdrop.addEventListener('click', function () { self.close(); });

      var tray = document.createElement('div');
      tray.className = 'ns-tray';
      tray.innerHTML =
        '<div class="ns-tray-head"><h3>Shortlist</h3>' +
        '<button class="ns-ab-clear" title="Close">✕</button></div>' +
        '<div class="ns-tray-body"></div>' +
        '<div class="ns-tray-foot">' +
        '<button class="btn" data-act="send">Send to essay →</button>' +
        '<button class="btn ghost" data-act="clear">Clear all</button></div>';
      tray.querySelector('.ns-tray-head .ns-ab-clear').addEventListener('click', function () { self.close(); });
      tray.querySelector('[data-act="send"]').addEventListener('click', function () { self.sendToEssay(); });
      tray.querySelector('[data-act="clear"]').addEventListener('click', function () { self.clearAll(); });

      document.body.appendChild(fab);
      document.body.appendChild(backdrop);
      document.body.appendChild(tray);
      this._fab = fab; this._backdrop = backdrop; this._tray = tray;
      this._body = tray.querySelector('.ns-tray-body');
      this._badge = fab.querySelector('.ns-tray-badge');
    },

    _render() {
      if (this._badge) this._badge.textContent = this.items.length;
      if (!this._body) return;
      var self = this;
      if (!this.items.length) {
        this._body.innerHTML = '<div class="ns-tray-empty">Nothing shortlisted yet.<br>' +
          'Select assets in the library and choose <b>Add to shortlist</b>.</div>';
        return;
      }
      this._body.innerHTML = this.items.map(function (it) {
        return '<div class="ns-tray-item">' +
          '<img loading="lazy" src="' + esc(it.thumb || '') + '" alt="">' +
          '<div class="ns-ti-label">' + esc(it.label || it.key) +
          '<div class="ns-ti-kind">' + esc(it.kind || '') + '</div></div>' +
          '<button class="ns-ti-rm" title="Remove" data-key="' + esc(it.key) + '">✕</button></div>';
      }).join('');
      this._body.querySelectorAll('.ns-ti-rm').forEach(function (b) {
        b.addEventListener('click', function () { self.remove(b.getAttribute('data-key')); });
      });
    },

    _flash(msg) {
      // reuse the FAB as a lightweight confirmation
      if (!this._fab) return;
      var badge = this._badge;
      this._fab.style.borderColor = 'var(--success)';
      var self = this;
      setTimeout(function () { self._fab.style.borderColor = ''; }, 900);
    },

    open() { this._tray.classList.add('open'); this._backdrop.classList.add('open'); this.refresh(); },
    close() { this._tray.classList.remove('open'); this._backdrop.classList.remove('open'); },
  };

  window.NolanShortlist = SL;
})();
