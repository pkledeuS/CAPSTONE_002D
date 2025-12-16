(function () {
  function parseJSONScript(id) {
    const el = document.getElementById(id);
    if (!el) return [];
    try {
      return JSON.parse(el.textContent || '[]');
    } catch (err) {
      console.warn('[admin-analytics] JSON parse failed for', id, err);
      return [];
    }
  }

  function ensureData(canvas, emptyElem, labels) {
    const hasData = Array.isArray(labels) && labels.length > 0;
    if (!canvas) return false;
    if (!hasData) {
      canvas.classList.add('d-none');
      if (emptyElem) emptyElem.classList.remove('d-none');
      return false;
    }
    canvas.classList.remove('d-none');
    if (emptyElem) emptyElem.classList.add('d-none');
    return true;
  }

  function createBarChart(canvasId, emptyId, labels, values, datasetLabel) {
    const canvas = document.getElementById(canvasId);
    const empty = document.getElementById(emptyId);
    if (!ensureData(canvas, empty, labels)) return;

    const palette = ['#60a5fa', '#34d399', '#fbbf24', '#f472b6', '#a78bfa', '#f97316', '#14b8a6', '#ef4444'];
    const colors = labels.map((_, idx) => palette[idx % palette.length]);

    new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: datasetLabel,
            data: values,
            backgroundColor: colors,
            borderRadius: 8,
            borderSkipped: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: { precision: 0 },
          },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  function createHorizontalBar(canvasId, emptyId, labels, values, datasetLabel) {
    const canvas = document.getElementById(canvasId);
    const empty = document.getElementById(emptyId);
    if (!ensureData(canvas, empty, labels)) return;

    const palette = ['#22c55e', '#14b8a6', '#f97316', '#a855f7', '#3b82f6', '#f43f5e'];
    const colors = labels.map((_, idx) => palette[idx % palette.length]);

    new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: datasetLabel,
            data: values,
            backgroundColor: colors,
            borderRadius: 8,
            borderSkipped: false,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { beginAtZero: true, ticks: { precision: 0 } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  function createPieChart(canvasId, emptyId, labels, values) {
    const canvas = document.getElementById(canvasId);
    const empty = document.getElementById(emptyId);
    if (!ensureData(canvas, empty, labels) || !values.some(v => v > 0)) {
      if (canvas) canvas.classList.add('d-none');
      if (empty) empty.classList.remove('d-none');
      return;
    }

    new Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: ['#60a5fa', '#22c55e', '#f97316', '#a855f7'],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom' } },
      },
    });
  }

  function initCharts() {
    if (typeof Chart === 'undefined') return;

    const brandLabels = parseJSONScript('brandL');
    const brandValues = parseJSONScript('brandV');
    const storeLabels = parseJSONScript('storeL');
    const storeValues = parseJSONScript('storeV');
    const funnelLabels = parseJSONScript('funnelL');
    const funnelValues = parseJSONScript('funnelV');

    createBarChart('chartBrands', 'emptyBrands', brandLabels, brandValues, 'Vistas registradas');
    createHorizontalBar('chartStores', 'emptyStores', storeLabels, storeValues, 'Clicks registrados');
    createPieChart('chartFunnel', 'emptyFunnel', funnelLabels, funnelValues);
  }

  document.addEventListener('DOMContentLoaded', initCharts);
})();
