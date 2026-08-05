(function () {
  const root = document.getElementById("higgsfield-root");
  if (!root) return;

  const ideaId = root.dataset.ideaId;
  const pollUrl = `/higgsfield/${ideaId}/poll`;

  const timerEl = document.getElementById("elapsed-timer");
  const messageEl = document.getElementById("job-message");
  const bannerEl = document.getElementById("status-banner");
  const loaderPanel = document.getElementById("loader-panel");
  const loaderTitle = document.getElementById("loader-title");
  const spinner = document.getElementById("spinner");

  function formatElapsed(seconds) {
    const m = Math.floor(seconds / 60).toString().padStart(2, "0");
    const s = Math.floor(seconds % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }

  const startTime = Date.now();
  const tick = setInterval(() => {
    timerEl.textContent = formatElapsed((Date.now() - startTime) / 1000);
  }, 1000);

  function finish(success, message) {
    clearInterval(tick);
    loaderPanel.classList.add("finished");
    loaderTitle.textContent = success ? "Terminé !" : "Échec pendant la génération";
    spinner.style.display = "none";

    bannerEl.hidden = false;
    bannerEl.classList.add(success ? "success" : "failure");
    bannerEl.querySelector(".status-text").textContent = message;
  }

  async function poll() {
    try {
      const res = await fetch(pollUrl);
      const data = await res.json();

      if (data.message) {
        messageEl.textContent = data.message;
      }

      if (data.status === "done") {
        finish(!!data.success, data.message || (data.success ? "Vidéo générée avec succès." : "Échec de la génération."));
        return;
      }
    } catch (err) {
      /* accroc réseau passager : on continue de sonder */
    }
    setTimeout(poll, 800);
  }

  poll();
})();
