(function () {
  "use strict";

  const root = document.querySelector(".analytics");
  if (!root) return;

  const code = root.dataset.code;
  const base = `/api/v1/analytics/${encodeURIComponent(code)}`;
  const errorBox = document.getElementById("analytics-error");
  const totalBadge = document.getElementById("visits-total");
  const rangeButtons = document.querySelectorAll(".range-btn");

  let chart = null;

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
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = await res.json();
    return body.data;
  }

  function renderChart(points) {
    const labels = points.map((p) => p.date);
    const values = points.map((p) => p.clicks);
    if (chart) chart.destroy();
    const ctx = document.getElementById("visits-chart").getContext("2d");
    chart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Visits",
            data: values,
            borderColor: "#4f46e5",
            backgroundColor: "rgba(79,70,229,0.12)",
            fill: true,
            tension: 0.3,
            pointRadius: 2,
          },
        ],
      },
      options: {
        responsive: true,
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        plugins: { legend: { display: false } },
      },
    });
  }

  function fillBreakdown(bodyId, items, withPct) {
    const body = document.getElementById(bodyId);
    if (!items.length) {
      const cols = withPct ? 3 : 2;
      body.innerHTML = `<tr><td colspan="${cols}">No data yet.</td></tr>`;
      return;
    }
    const total = items.reduce((s, i) => s + i.count, 0);
    body.innerHTML = items
      .map((i) => {
        const label = i.label || "Direct/Unknown";
        if (withPct) {
          const pct = total ? ((i.count / total) * 100).toFixed(1) : "0.0";
          return `<tr><td>${label}</td><td>${i.count}</td><td>${pct}%</td></tr>`;
        }
        return `<tr><td>${label}</td><td>${i.count}</td></tr>`;
      })
      .join("");
  }

  async function loadAll(days) {
    clearError();
    try {
      const [ts, countries, referrers, browsers] = await Promise.all([
        apiGet(`${base}/timeseries?days=${days}`),
        apiGet(`${base}/countries?days=${days}&limit=50`),
        apiGet(`${base}/referrers?days=${days}&limit=10`),
        apiGet(`${base}/browsers?days=${days}&limit=10`),
      ]);

      renderChart(ts.points || []);
      totalBadge.textContent = `${ts.total} total`;

      fillBreakdown("countries-body", countries.items || [], true);
      fillBreakdown("referrers-body", referrers.items || [], false);
      fillBreakdown("browsers-body", browsers.items || [], false);
    } catch (err) {
      if (err.message !== "unauthorized") {
        showError("Failed to load analytics. " + err.message);
      }
    }
  }

  rangeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      rangeButtons.forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      loadAll(Number(btn.dataset.days));
    });
  });

  loadAll(7);
})();
