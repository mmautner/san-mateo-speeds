// Google Analytics events for the speeds pages. Same safe-call pattern as maxmautner.com's trackEvent; every event
// is prefixed speeds_ so it can be filtered from the blog's events in the shared property.
(function () {
  const segment = document.documentElement.dataset.segment || "";

  function track(name, params) {
    if (typeof gtag === "function") gtag("event", "speeds_" + name, Object.assign({ segment }, params || {}));
  }
  window.spTrack = track;

  document.addEventListener("click", (ev) => {
    const el = ev.target.closest("a, button");
    if (!el) return;

    // elements that name their own event: data-track="ask_email_clicked" plus data-track-* params
    if (el.dataset.track) {
      const params = {};
      for (const [k, v] of Object.entries(el.dataset))
        if (k.startsWith("track") && k !== "track") // data-track-pdf-page -> pdf_page
          params[k.slice(5).replace(/[A-Z]/g, (c) => "_" + c.toLowerCase()).replace(/^_/, "")] = v;
      track(el.dataset.track, params);
      return;
    }
    if (el.tagName !== "A") return;
    const href = el.getAttribute("href") || "";

    // a street link in the index table
    if (el.closest("#sp-table")) {
      track("table_segment_clicked", { target_segment: href.split("/").filter(Boolean).pop() || "" });
      return;
    }
    // links that leave maxmautner.com: city documents, FHWA, the request form, GitHub
    try {
      const u = new URL(href, location.href);
      if (u.protocol.startsWith("http") && u.hostname !== location.hostname)
        track("outbound_clicked", { link_url: u.href, link_text: el.textContent.trim().slice(0, 100) });
    } catch (e) { /* not a URL */ }
  });
})();
