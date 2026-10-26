// Map of surveyed segments. The table and pages are the primary content; the map is an index into them.
(function () {
  const el = document.getElementById("sp-map");
  const dataEl = document.getElementById("sp-data");
  if (!el || !dataEl) return;
  const data = JSON.parse(dataEl.textContent);
  const single = dataEl.dataset.mode === "single";
  if (!data.features.length) return;

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
  js.onerror = () => { el.innerHTML = '<p class="sp-meta" style="padding:12px">The map didn\'t load. Every street is listed on this page.</p>'; };
  js.onload = () => {
    const m = new maplibregl.Map({
      container: el, style: styleUrl(), bounds: bounds(),
      fitBoundsOptions: { padding: single ? 50 : 24, maxZoom: 15.5 },
      attributionControl: { compact: true }, cooperativeGestures: true, dragRotate: false, pitchWithRotate: false,
    });
    if (new URLSearchParams(location.search).has("debug")) window.__spmap = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const lineColor = () => ["match", ["get", "bin"], 0, cssColor("--b0"), 1, cssColor("--b1"), 2, cssColor("--b2"), cssColor("--b3")];
    // heavier lines for faster streets, so the order reads without color; the halo is 2px wider at z12, 3px at z16
    const byBin = (w) => ["match", ["get", "bin"], 0, w[0], 1, w[1], 2, w[2], w[3]];
    const lineWidth = (pad) => ["interpolate", ["linear"], ["zoom"],
      12, byBin([2, 3, 4, 5].map((w) => w + pad)), 16, byBin([4, 5.5, 7, 8.5].map((w) => w + pad * 1.5))];
    const add = () => {
      m.addSource("segs", { type: "geojson", data });
      const lay = { "line-cap": "round", "line-join": "round", "line-sort-key": ["get", "bin"] };  // most over on top
      m.addLayer({ id: "segs-halo", type: "line", source: "segs", layout: lay,
        paint: { "line-color": cssColor("--bg"), "line-width": single ? 10 : lineWidth(2) } });
      m.addLayer({ id: "segs", type: "line", source: "segs", layout: lay,
        paint: { "line-color": lineColor(), "line-width": single ? 6 : lineWidth(0) } });
      if (!single) // wide invisible line so thin segments are easy to tap
        m.addLayer({ id: "segs-hit", type: "line", source: "segs", paint: { "line-color": "#000", "line-opacity": 0, "line-width": 20 } });
    };
    m.on("style.load", add);

    if (!single) {
      const popup = new maplibregl.Popup({ closeButton: false, offset: 8 });
      m.on("mousemove", "segs-hit", (ev) => {
        m.getCanvas().style.cursor = "pointer";
        const p = ev.features[0].properties;
        popup.setLngLat(ev.lngLat).setText(`${p.label}. ${p.text}`).addTo(m);
      });
      m.on("mouseleave", "segs-hit", () => { m.getCanvas().style.cursor = ""; popup.remove(); });
      m.on("click", "segs-hit", (ev) => {
        const url = ev.features[0].properties.url;
        if (window.spTrack) window.spTrack("map_segment_clicked", {
          target_segment: url.split("/").filter(Boolean).pop() });
        location.href = url;
      });
    }
    new MutationObserver(() => m.setStyle(styleUrl()))
      .observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  };
  document.head.append(js);
})();
