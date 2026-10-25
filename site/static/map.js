// Map of surveyed segments. The list on the page is the primary content; the map is an index into it.
(function () {
  const el = document.getElementById("sp-map");
  const dataEl = document.getElementById("sp-data");
  if (!el || !dataEl) return;
  const data = JSON.parse(dataEl.textContent);

  // The site's tokens are oklch(); MapLibre needs plain rgb.
  const px = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  const cssColor = (name) => {
    px.clearRect(0, 0, 1, 1);
    px.fillStyle = "#000";
    px.fillStyle = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    px.fillRect(0, 0, 1, 1);
    const [r, g, b] = px.getImageData(0, 0, 1, 1).data;
    return `rgb(${r}, ${g}, ${b})`;
  };
  const styleUrl = () =>
    `https://tiles.openfreemap.org/styles/${document.documentElement.dataset.theme === "light" ? "positron" : "dark"}`;

  function target(id) {
    document.querySelectorAll(".sp-card.is-target").forEach((c) => c.classList.remove("is-target"));
    const card = document.getElementById(id);
    if (!card) return;
    card.classList.add("is-target");
    card.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    card.focus({ preventScroll: true });
  }
  if (location.hash) target(location.hash.slice(1));
  window.addEventListener("hashchange", () => target(location.hash.slice(1)));

  const bounds = () => {
    let w = 180, s = 90, e = -180, n = -90;
    for (const f of data.features) for (const [x, y] of f.geometry.coordinates) {
      w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y);
    }
    return [[w, s], [e, n]];
  };

  const css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = "https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/4.7.1/maplibre-gl.min.css";
  document.head.append(css);
  const js = document.createElement("script");
  js.src = "https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/4.7.1/maplibre-gl.min.js";
  js.onerror = () => { el.innerHTML = '<p class="sp-meta" style="padding:12px">The map didn\'t load. Every street is listed below.</p>'; };
  js.onload = () => {
    const m = new maplibregl.Map({
      container: el, style: styleUrl(), bounds: bounds(), fitBoundsOptions: { padding: 30 },
      attributionControl: { compact: true }, cooperativeGestures: true, dragRotate: false, pitchWithRotate: false,
    });
    if (new URLSearchParams(location.search).has("debug")) window.__spmap = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    const add = () => {
      m.addSource("segs", { type: "geojson", data });
      m.addLayer({ id: "segs-halo", type: "line", source: "segs", layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": cssColor("--bg"), "line-width": 9 } });
      m.addLayer({ id: "segs", type: "line", source: "segs", layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": cssColor("--line"), "line-width": 5 } });
      // wide invisible line so thin segments are easy to tap
      m.addLayer({ id: "segs-hit", type: "line", source: "segs", paint: { "line-color": "#000", "line-opacity": 0, "line-width": 22 } });
    };
    m.on("style.load", add);
    const popup = new maplibregl.Popup({ closeButton: false, offset: 8 });
    m.on("mousemove", "segs-hit", (ev) => {
      m.getCanvas().style.cursor = "pointer";
      const p = ev.features[0].properties;
      popup.setLngLat(ev.lngLat).setText(`${p.label}: ${p.text}`).addTo(m);
    });
    m.on("mouseleave", "segs-hit", () => { m.getCanvas().style.cursor = ""; popup.remove(); });
    m.on("click", "segs-hit", (ev) => {
      const id = ev.features[0].properties.id;
      if (location.hash === "#" + id) target(id); else location.hash = id;
    });
    new MutationObserver(() => m.setStyle(styleUrl()))
      .observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  };
  document.head.append(js);
})();
