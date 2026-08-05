(function () {
  const root = document.getElementById("publish-root");
  if (!root) return;

  const ideaId = root.dataset.ideaId;
  const pollUrl = `/ideas/${ideaId}/publish/poll`;

  const timerEl = document.getElementById("elapsed-timer");
  const progressFill = document.getElementById("progress-fill");
  const progressMessage = document.getElementById("progress-message");
  const bannerEl = document.getElementById("status-banner");
  const loaderPanel = document.getElementById("loader-panel");
  const loaderTitle = document.getElementById("loader-title");
  const spinner = document.getElementById("spinner");
  const videoLink = document.getElementById("video-link");

  function formatElapsed(seconds) {
    const m = Math.floor(seconds / 60).toString().padStart(2, "0");
    const s = Math.floor(seconds % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }

  const startTime = Date.now();
  const tick = setInterval(() => {
    timerEl.textContent = formatElapsed((Date.now() - startTime) / 1000);
  }, 1000);

  function finish(success, videoId, errorMessage) {
    clearInterval(tick);
    loaderPanel.classList.add("finished");
    spinner.style.display = "none";

    bannerEl.hidden = false;
    bannerEl.classList.add(success ? "success" : "failure");

    if (success) {
      loaderTitle.textContent = "Terminé !";
      progressFill.style.width = "100%";
      bannerEl.querySelector(".status-text").textContent = "Vidéo publiée avec succès.";
      const url = `https://youtu.be/${videoId}`;
      videoLink.innerHTML = `<a href="${url}" target="_blank" rel="noopener">Voir sur YouTube</a> &middot; ` +
        `<a href="https://studio.youtube.com/video/${videoId}/edit" target="_blank" rel="noopener">Ouvrir dans YouTube Studio</a>`;
    } else {
      loaderTitle.textContent = "Échec de la publication";
      bannerEl.querySelector(".status-text").textContent = errorMessage || "Échec de la publication.";
    }
  }

  async function poll() {
    try {
      const res = await fetch(pollUrl);
      const data = await res.json();

      progressFill.style.width = `${data.progress || 0}%`;
      progressMessage.textContent = data.message || "";

      if (data.status === "done") {
        finish(!!data.success, data.video_id, data.error);
        return;
      }
    } catch (err) {
      /* transient network hiccup: keep polling */
    }
    setTimeout(poll, 800);
  }

  poll();
})();
