// Sortable, filterable segment table. The table works without this script; this adds sorting and the filter.
(function () {
  const table = document.getElementById("sp-table");
  if (!table) return;
  const body = table.tBodies[0];
  const heads = [...table.tHead.rows[0].cells];

  heads.forEach((th, i) => {
    const btn = th.querySelector("button");
    if (!btn) return;
    btn.addEventListener("click", () => {
      const cur = th.getAttribute("aria-sort");
      const kind = btn.dataset.sort;
      // first click: text ascending, numbers descending (biggest first)
      const dir = cur === "none" ? (kind === "text" ? "ascending" : "descending")
        : (cur === "ascending" ? "descending" : "ascending");
      heads.forEach((h) => h.setAttribute("aria-sort", "none"));
      th.setAttribute("aria-sort", dir);
      const sign = dir === "ascending" ? 1 : -1;
      const rows = [...body.rows];
      rows.sort((a, b) => {
        const va = a.cells[i].dataset.v, vb = b.cells[i].dataset.v;
        const c = kind === "num" ? Number(va) - Number(vb) : va.localeCompare(vb);
        return sign * c || a.cells[0].dataset.v.localeCompare(b.cells[0].dataset.v);
      });
      body.append(...rows);
      if (window.spTrack) window.spTrack("table_sorted", { column: btn.textContent.trim(), direction: dir });
    });
  });

  const filters = document.querySelectorAll("[data-filter]");
  filters.forEach((b) => b.addEventListener("click", () => {
    filters.forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    const only = b.dataset.filter === "inc";
    for (const r of body.rows) r.hidden = only && r.dataset.inc !== "1";
    if (window.spTrack) window.spTrack("table_filtered", { filter: b.dataset.filter });
  }));
})();
