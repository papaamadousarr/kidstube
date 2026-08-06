(function () {
  const searchInput = document.getElementById("board-search");
  const countEl = document.getElementById("board-filter-count");
  const columns = Array.from(document.querySelectorAll(".column"));
  if (!searchInput || !columns.length) return;

  function applyFilter() {
    const query = searchInput.value.trim().toLowerCase();
    let visibleTotal = 0;
    let cardTotal = 0;

    columns.forEach((column) => {
      const cards = Array.from(column.querySelectorAll(".card"));
      const countBadge = column.querySelector(".column-count");
      let visibleInColumn = 0;

      cards.forEach((card) => {
        const matches = !query || card.dataset.title.includes(query);
        card.hidden = !matches;
        if (matches) visibleInColumn += 1;
      });

      cardTotal += cards.length;
      visibleTotal += visibleInColumn;
      if (countBadge) countBadge.textContent = visibleInColumn;
    });

    countEl.textContent = query ? `${visibleTotal} / ${cardTotal}` : "";
  }

  searchInput.addEventListener("input", applyFilter);
})();
