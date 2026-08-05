(function () {
  document.querySelectorAll(".generate-ideas-form, .create-short-form").forEach((form) => {
    form.addEventListener("submit", () => {
      const btn = form.querySelector("button[type=submit]");
      if (!btn) return;
      btn.disabled = true;
      btn.dataset.originalText = btn.textContent;
      btn.textContent = "Génération…";
    });
  });
})();
