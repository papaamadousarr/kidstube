(function () {
  const searchInput = document.getElementById("ideas-search");
  const statusFilter = document.getElementById("ideas-status-filter");
  const countEl = document.getElementById("ideas-filter-count");
  const rows = Array.from(document.querySelectorAll("#ideas-table tbody tr"));
  if (!searchInput || !rows.length) return;

  function applyFilter() {
    const query = searchInput.value.trim().toLowerCase();
    const status = statusFilter.value;
    let visible = 0;

    rows.forEach((row) => {
      const matchesQuery = !query || row.dataset.title.includes(query);
      const matchesStatus = !status || row.dataset.status === status;
      const show = matchesQuery && matchesStatus;
      row.hidden = !show;
      if (show) visible += 1;
    });

    countEl.textContent = `${visible} / ${rows.length}`;
  }

  searchInput.addEventListener("input", applyFilter);
  statusFilter.addEventListener("change", applyFilter);
  applyFilter();
})();
