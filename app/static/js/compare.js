(function () {
  "use strict";

  const form = document.getElementById("compare-form");
  if (!form) return;

  const errorBox = document.getElementById("compare-error");
  const summaryBody = document.getElementById("compare-summary");

  let chart = null;

  const PALETTE = [
    "#4f46e5", "#059669", "#dc2626", "#d97706", "#7c3aed",
    "#0891b2", "#db2777", "#65a30d", "#2563eb", "#ea580c",
  ];

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.hidden = false;
  }
  function clearError() {
    errorBox.hidden = true;
  }

  async function apiGet(url) {
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (res.status === 401) {
      window.location.href = "/?msg=login_required";
      throw new Error("unauthorized");
    }
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      const detail =
        body && body.errors && body.errors[0] ? body.errors[0].message : `HTTP ${res.status}`;
      throw new Error(detail);
    }
    const body = await res.json();
    return body.data;
  }

  function renderChart(series) {
    // All series share the same day axis (backend fills missing days).
    const labels = series.length ? series[0].points.map((p) => p.date) : [];

    const datasets = series.map((s, idx) => ({
      label: s.short_code,
      data: s.points.map((p) => p.clicks),
      borderColor: PALETTE[idx % PALETTE.length],
      backgroundColor: "transparent",
      tension: 0.3,
      pointRadius: 2,
    }));

    if (chart) chart.destroy();
    const ctx = document.getElementById("compare-chart").getContext("2d");
    chart = new Chart(ctx, {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        interaction: { mode: "index", intersect: false },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        plugins: { legend: { position: "bottom" } },
      },
    });
  }

  function renderSummary(series) {
    if (!series.length) {
      summaryBody.innerHTML = `<tr><td colspan="2">No data.</td></tr>`;
      return;
    }
    summaryBody.innerHTML = series
      .map((s) => `<tr><td><code>${s.short_code}</code></td><td>${s.total}</td></tr>`)
      .join("");
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError();

    const raw = document.getElementById("compare-codes").value;
    const codes = raw
      .split(",")
      .map((c) => c.trim())
      .filter(Boolean);

    if (!codes.length) {
      showError("Enter at least one short code.");
      return;
    }
    if (codes.length > 10) {
      showError("You can compare at most 10 links.");
      return;
    }

    const days = document.querySelector('input[name="days"]:checked').value;
    const url = `/api/v1/analytics/compare?codes=${encodeURIComponent(codes.join(","))}&days=${days}`;

    try {
      const data = await apiGet(url);
      renderChart(data.series || []);
      renderSummary(data.series || []);
    } catch (err) {
      if (err.message !== "unauthorized") {
        showError("Compare failed: " + err.message);
      }
    }
  });
})();
