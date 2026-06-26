// Reusable job-poll + progress widget for hub pages.
// NolanJobs.start(url, formDataOrBody, {into, onDone}) -> polls /api/jobs/{id} and renders progress.
window.NolanJobs = (function () {
  function render(el, job) {
    var statusClass = "status-" + job.status;
    el.className = "job-widget " + statusClass;
    var badge = '<span class="badge ' + job.status + '">' + job.status + "</span>";
    var pct = Math.round((job.progress || 0) * 100);
    var logs = (job.logs || []).slice(-40).join("\n");
    el.innerHTML =
      '<div>' + badge + ' <strong>' + (job.type || "job") + "</strong></div>" +
      '<div class="bar"><div style="width:' + pct + '%"></div></div>' +
      '<div class="msg">' + (job.message || "") + (job.error ? (" — " + job.error) : "") + "</div>" +
      (logs ? '<div class="logs">' + escapeHtml(logs) + "</div>" : "");
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c];
    });
  }

  function poll(jobId, opts) {
    var into = opts.into;
    var interval = opts.interval || 1500;
    function tick() {
      fetch("/api/jobs/" + jobId)
        .then(function (r) { return r.json(); })
        .then(function (job) {
          if (into) render(into, job);
          if (job.status === "running" || job.status === "pending") {
            setTimeout(tick, interval);
          } else {
            if (opts.onDone) opts.onDone(job);
          }
        })
        .catch(function () { setTimeout(tick, interval * 2); });
    }
    tick();
  }

  // body: a plain object (sent as JSON) or FormData.
  function start(url, body, opts) {
    opts = opts || {};
    var init = { method: "POST" };
    if (body instanceof FormData) {
      init.body = body;
    } else {
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify(body || {});
    }
    return fetch(url, init)
      .then(function (r) {
        if (!r.ok) return r.text().then(function (t) { throw new Error(t || r.status); });
        return r.json();
      })
      .then(function (res) {
        if (opts.into) {
          opts.into.style.display = "block";
          render(opts.into, { type: res.type || "job", status: "pending", progress: 0, message: "Starting…" });
        }
        poll(res.job_id, opts);
        return res.job_id;
      });
  }

  return { start: start, poll: poll, render: render };
})();
