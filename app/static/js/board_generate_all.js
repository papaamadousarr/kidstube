(function () {
  const widget = document.querySelector(".generate-all-widget");
  if (!widget) return;

  const startUrl = widget.dataset.startUrl;
  const stopUrl = widget.dataset.stopUrl;
  const statusUrl = widget.dataset.statusUrl;
  const startBtn = widget.querySelector(".generate-all-start-btn");
  const progress = widget.querySelector(".generate-all-progress");
  const stopBtn = widget.querySelector(".generate-all-stop-btn");
  const activeCountEl = widget.querySelector(".generate-all-active-count");

  let pollHandle = null;

  function showProgress() {
    startBtn.hidden = true;
    progress.hidden = false;
    poll();
  }

  function showIdle() {
    clearTimeout(pollHandle);
    progress.hidden = true;
    startBtn.hidden = false;
    // Le compte de vidéos restantes affiché sur le bouton peut avoir changé
    // (jobs terminés, ou nouvelles idées passées à "assembled" entre-temps) —
    // un rechargement le remet à jour sans dupliquer la logique côté client.
    window.location.reload();
  }

  async function poll() {
    try {
      const res = await fetch(statusUrl);
      const data = await res.json();
      activeCountEl.textContent = data.active;

      if (data.stopping) {
        stopBtn.disabled = true;
        stopBtn.textContent = "Arrêt en cours…";
      }

      if (data.active === 0) {
        showIdle();
        return;
      }
    } catch (err) {
      /* accroc réseau passager : on continue de sonder */
    }
    pollHandle = setTimeout(poll, 1000);
  }

  startBtn.addEventListener("click", async () => {
    showProgress();
    try {
      await fetch(startUrl, { method: "POST" });
    } catch (err) {
      /* le sondage prendra quand même le relai si le lot a bien démarré */
    }
  });

  stopBtn.addEventListener("click", async () => {
    stopBtn.disabled = true;
    stopBtn.textContent = "Arrêt en cours…";
    try {
      await fetch(stopUrl, { method: "POST" });
    } catch (err) {
      stopBtn.disabled = false;
      stopBtn.textContent = "Arrêter proprement";
    }
  });

  if (widget.dataset.autostart === "1") {
    showProgress();
  }
})();
