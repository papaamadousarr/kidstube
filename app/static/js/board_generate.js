(function () {
  document.querySelectorAll(".generate-widget").forEach((widget) => {
    const generateUrl = widget.dataset.generateUrl;
    const pollUrl = widget.dataset.pollUrl;
    const btn = widget.querySelector(".generate-btn");
    const progress = widget.querySelector(".generate-progress");
    const elapsedEl = widget.querySelector(".generate-elapsed");
    const detailLink = widget.querySelector(".generate-detail-link");

    let startTime = null;
    let timerHandle = null;

    function formatElapsed(seconds) {
      const m = Math.floor(seconds / 60).toString().padStart(2, "0");
      const s = Math.floor(seconds % 60).toString().padStart(2, "0");
      return `${m}:${s}`;
    }

    function showProgress() {
      btn.hidden = true;
      progress.hidden = false;
      detailLink.hidden = false;
      startTime = Date.now();
      clearInterval(timerHandle);
      timerHandle = setInterval(() => {
        elapsedEl.textContent = formatElapsed((Date.now() - startTime) / 1000);
      }, 1000);
      poll();
    }

    function finish(success) {
      clearInterval(timerHandle);
      progress.hidden = true;
      if (success) {
        // La carte doit changer de colonne (statut "assembled") : un rechargement
        // reflète ça simplement, sans dupliquer la logique de rendu du Kanban.
        // Les autres générations en cours reprennent leur suivi au chargement
        // via data-autostart, donc rien n'est perdu pour les jobs concurrents.
        window.location.reload();
        return;
      }
      detailLink.hidden = true;
      btn.hidden = false;
      btn.textContent = "Échec — Réessayer";
    }

    async function poll() {
      try {
        const res = await fetch(pollUrl);
        const data = await res.json();
        if (data.status === "done") {
          finish(!!data.success);
          return;
        }
      } catch (err) {
        /* accroc réseau passager : on continue de sonder */
      }
      setTimeout(poll, 1000);
    }

    btn.addEventListener("click", async () => {
      showProgress();
      try {
        await fetch(generateUrl, { method: "POST" });
      } catch (err) {
        /* le sondage prendra quand même le relai si le job a bien démarré */
      }
    });

    if (widget.dataset.autostart === "1") {
      showProgress();
    }
  });
})();
