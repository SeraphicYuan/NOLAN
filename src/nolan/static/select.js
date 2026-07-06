/* NolanSelect — shared multi-select + contextual action bar for the asset
 * library grids (Pictures, Videos, Clips).
 *
 * A card grid opts in with:
 *
 *   const sel = NolanSelect.attach({
 *     grid: '#grid',              // container element or selector
 *     card: '.tile',             // selector for each selectable card
 *     id:   'data-id',           // attribute holding each card's id (default 'data-id')
 *     actions: [
 *       { label: 'Cut out', run: (ids) => ... },
 *       { label: 'Reject', danger: true, confirm: 'Reject N images?', run: (ids) => ... },
 *     ],
 *     onChange: (count) => {},
 *   });
 *
 * After the page re-renders its cards, call sel.refresh() to re-apply checkbox
 * badges + selection state. Selection is a Set of ids and survives re-renders.
 *
 * Interaction model (mirrors Photos/Frame.io):
 *  - The checkbox badge (top-left) toggles a card in any mode; it appears on
 *    hover, or always while "select mode" is on.
 *  - In select mode the whole card toggles (page's primary click is suppressed).
 *  - Shift-click extends a range from the last-toggled card.
 */
(function () {
  function resolve(el) { return typeof el === 'string' ? document.querySelector(el) : el; }

  function NolanSelect(opts) {
    this.grid = resolve(opts.grid);
    this.cardSel = opts.card;
    this.idAttr = opts.id || 'data-id';
    this.actions = opts.actions || [];
    this.onChange = opts.onChange || function () {};
    this.selected = new Set();
    this._anchor = null;   // index of last toggled card, for shift-range
    if (!this.grid) { console.warn('NolanSelect: grid not found', opts.grid); return; }
    this.grid.classList.add('ns-grid');
    this._buildBar();
    this._bind();
    this.refresh();
  }

  NolanSelect.prototype._cards = function () {
    return Array.prototype.slice.call(this.grid.querySelectorAll(this.cardSel));
  };
  NolanSelect.prototype._idOf = function (card) { return card.getAttribute(this.idAttr); };

  // Inject the checkbox badge + selection class into every card. Idempotent.
  NolanSelect.prototype.refresh = function () {
    var self = this;
    this._cards().forEach(function (card) {
      card.classList.add('ns-selectable');
      if (!card.querySelector('.ns-check')) {
        var b = document.createElement('div');
        b.className = 'ns-check'; b.textContent = '✓';
        b.addEventListener('click', function (e) {
          e.stopPropagation(); e.preventDefault(); self._toggleCard(card, e.shiftKey);
        });
        card.insertBefore(b, card.firstChild);
      }
      var on = self.selected.has(self._idOf(card));
      card.classList.toggle('ns-selected', on);
    });
    this._updateBar();
  };

  NolanSelect.prototype._bind = function () {
    var self = this;
    this.grid.addEventListener('click', function (e) {
      if (!self.grid.classList.contains('ns-select-mode')) return; // only hijack in select mode
      // let genuine controls (links/buttons/inputs) still work
      if (e.target.closest('a,button,select,input,textarea,.ns-check')) return;
      var card = e.target.closest(self.cardSel);
      if (!card || !self.grid.contains(card)) return;
      e.preventDefault(); e.stopPropagation();
      self._toggleCard(card, e.shiftKey);
    }, true);
  };

  NolanSelect.prototype._toggleCard = function (card, shift) {
    var cards = this._cards();
    var idx = cards.indexOf(card);
    var id = this._idOf(card);
    if (shift && this._anchor != null && this._anchor < cards.length) {
      var lo = Math.min(this._anchor, idx), hi = Math.max(this._anchor, idx);
      var turnOn = !this.selected.has(id);
      for (var i = lo; i <= hi; i++) {
        var cid = this._idOf(cards[i]);
        if (turnOn) this.selected.add(cid); else this.selected.delete(cid);
        cards[i].classList.toggle('ns-selected', turnOn);
      }
    } else {
      if (this.selected.has(id)) { this.selected.delete(id); card.classList.remove('ns-selected'); }
      else { this.selected.add(id); card.classList.add('ns-selected'); }
    }
    this._anchor = idx;
    this._updateBar();
    this.onChange(this.selected.size);
  };

  // ---- selection API ----
  NolanSelect.prototype.getSelected = function () { return Array.from(this.selected); };  // Sets are not array-like — slice.call(Set) returned [] and every bulk verb silently no-oped
  NolanSelect.prototype.count = function () { return this.selected.size; };
  NolanSelect.prototype.clear = function () {
    this.selected.clear(); this._anchor = null;
    this._cards().forEach(function (c) { c.classList.remove('ns-selected'); });
    this._updateBar(); this.onChange(0);
  };
  NolanSelect.prototype.toggleMode = function (force) {
    var on = this.grid.classList.toggle('ns-select-mode', force);
    if (!on) this.clear();
    return on;
  };

  // ---- contextual action bar ----
  NolanSelect.prototype._buildBar = function () {
    var self = this;
    var bar = document.createElement('div');
    bar.className = 'ns-action-bar';
    var count = document.createElement('span'); count.className = 'ns-ab-count';
    var acts = document.createElement('span'); acts.className = 'ns-ab-actions';
    this.actions.forEach(function (a) {
      var btn = document.createElement('button');
      btn.className = 'btn ' + (a.danger ? 'danger' : (a.cls || 'secondary'));
      btn.textContent = a.label;
      btn.addEventListener('click', function () {
        var ids = self.getSelected();
        if (!ids.length) return;
        if (a.confirm) {
          var msg = a.confirm.replace('N', ids.length);
          if (!window.confirm(msg)) return;
        }
        a.run(ids, self);
      });
      acts.appendChild(btn);
    });
    var clear = document.createElement('button');
    clear.className = 'ns-ab-clear'; clear.title = 'Clear selection'; clear.innerHTML = '✕';
    clear.addEventListener('click', function () { self.clear(); });
    bar.appendChild(count); bar.appendChild(acts); bar.appendChild(clear);
    document.body.appendChild(bar);
    this._bar = bar; this._barCount = count;
  };

  NolanSelect.prototype._updateBar = function () {
    var n = this.selected.size;
    this._barCount.innerHTML = '<b>' + n + '</b> selected';
    this._bar.classList.toggle('show', n > 0);
  };

  window.NolanSelect = { attach: function (opts) { return new NolanSelect(opts); } };
})();
