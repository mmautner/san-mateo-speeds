// Copy buttons on segment pages: [data-copy] names the input or textarea whose text to copy.
(function () {
  for (const btn of document.querySelectorAll("[data-copy]")) {
    btn.addEventListener("click", async () => {
      const src = document.getElementById(btn.dataset.copy);
      const status = btn.parentElement.querySelector(".sp-copied");
      const text = src.value;
      let ok = false;
      try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {
        // older browsers: select and copy from a temporary field
        const t = document.createElement("textarea");
        t.value = text; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
        document.body.append(t); t.select();
        try { ok = document.execCommand("copy"); } catch (e2) { ok = false; }
        t.remove();
      }
      if (status) status.textContent = ok ? "Copied." : "Couldn't copy. Select the text and copy it.";
    });
  }
})();
