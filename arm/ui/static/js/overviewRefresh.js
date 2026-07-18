/**
 * overviewRefresh.js — live progress for the "Now Ripping" hero on the
 * Settings -> General Info overview.
 *
 * Reuses the same endpoint the home page polls (/json?mode=joblist), which
 * returns all not-finished jobs with a live-computed progress + ETA parsed
 * from each job's MakeMKV/HandBrake progress log. We render one hero row per
 * active job into #nowRipping and refresh on an interval.
 */
(function () {
    "use strict";

    var POLL_MS = 5000;

    function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
            return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
        });
    }

    // job fields arrive stringified; treat "None"/"" as absent
    function val(v) {
        return (v == null || v === "None" || v === "") ? "" : v;
    }

    function clampPct(v) {
        var n = parseFloat(v);
        if (isNaN(n)) { return 0; }
        return Math.max(0, Math.min(100, n));
    }

    function rowHtml(job) {
        var pct = clampPct(job.progress_round !== undefined ? job.progress_round : job.progress);
        var title = val(job.title) || val(job.label) || "Unknown";
        var type = val(job.video_type) || val(job.disctype);
        var year = val(job.year);
        var dev = val(job.devpath);
        var eta = val(job.eta);
        var jobId = val(job.job_id);

        var meta = esc(type) + (year ? " (" + esc(year) + ")" : "");
        var sub = pct.toFixed(0) + "%" + (eta ? " &middot; ETA " + esc(eta) : "");

        return '' +
            '<div class="ars-hero-row">' +
                '<div class="ars-hero-head">' +
                    '<span class="ars-hero-dev">' + esc(dev) + '</span>' +
                    '<a class="ars-hero-name" href="jobdetail?job_id=' + esc(jobId) + '">' + esc(title) + '</a>' +
                    '<span class="ars-hero-meta">' + meta + '</span>' +
                '</div>' +
                '<div class="ars-hero-progress"><div class="ars-hero-fill" style="width:' + pct + '%"></div></div>' +
                '<div class="ars-hero-sub">' + sub + '</div>' +
            '</div>';
    }

    function render(results) {
        var host = document.getElementById("nowRipping");
        if (!host) { return; }
        var keys = Object.keys(results || {});
        if (!keys.length) {
            host.innerHTML = '<div class="ars-hero-empty">All drives idle &mdash; no active rips.</div>';
            return;
        }
        host.innerHTML = keys.map(function (k) { return rowHtml(results[k]); }).join("");
    }

    function poll() {
        fetch(location.origin + "/json?mode=joblist", {
            headers: {"Accept": "application/json"},
            credentials: "same-origin"
        }).then(function (r) {
            return r.ok ? r.json() : null;
        }).then(function (data) {
            if (data && typeof data.results !== "undefined") { render(data.results); }
        }).catch(function () { /* transient; keep last render */ });
    }

    function start() {
        if (!document.getElementById("nowRipping")) { return; }
        poll();
        setInterval(poll, POLL_MS);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
