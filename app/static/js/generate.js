(function () {
  const root = document.getElementById("generate-root");
  if (!root) return;

  const ideaId = root.dataset.ideaId;
  const pollUrl = `/ideas/${ideaId}/generate/poll`;

  const logEl = document.getElementById("log-output");
  const timerEl = document.getElementById("elapsed-timer");
  const progressFill = document.getElementById("progress-fill");
  const progressLabel = document.getElementById("progress-label");
  const itemsCountEl = document.getElementById("items-count");
  const bannerEl = document.getElementById("status-banner");
  const loaderPanel = document.getElementById("loader-panel");
  const loaderTitle = document.getElementById("loader-title");
  const spinner = document.getElementById("spinner");

  function setStep(name, state) {
    const el = root.querySelector(`[data-step="${name}"]`);
    if (!el) return;
    el.classList.remove("pending", "active", "done");
    el.classList.add(state);
  }

  function updateFromLog(log) {
    const itemsMatch = log.match(/\[2\/4\]\s+(\d+)\s+items/);
    const total = itemsMatch ? parseInt(itemsMatch[1], 10) : null;
    const doneCount = (log.match(/^\s*-\s+.+? ok \(/gm) || []).length;

    if (/\[1\/4\]/.test(log)) setStep("intro", "active");
    if (/\[2\/4\]/.test(log)) {
      setStep("intro", "done");
      setStep("items", total !== null && doneCount >= total ? "done" : "active");
    }
    if (/\[3\/4\]/.test(log)) {
      setStep("items", "done");
      setStep("outro", "active");
    }
    if (/\[4\/4\]/.test(log)) {
      setStep("outro", "done");
      setStep("assemble", "active");
    }

    if (total !== null) {
      itemsCountEl.textContent = `(${Math.min(doneCount, total)}/${total})`;
    }

    const pctMatches = [...log.matchAll(/frame_index:\s+(\d+)%/g)];
    if (pctMatches.length) {
      const pct = pctMatches[pctMatches.length - 1][1];
      progressFill.style.width = `${pct}%`;
      progressLabel.textContent = `${pct}%`;
    }
  }

  function formatElapsed(seconds) {
    const m = Math.floor(seconds / 60).toString().padStart(2, "0");
    const s = Math.floor(seconds % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }

  const startTime = Date.now();
  const tick = setInterval(() => {
    timerEl.textContent = formatElapsed((Date.now() - startTime) / 1000);
  }, 1000);

  function finish(success) {
    clearInterval(tick);
    root.querySelectorAll("[data-step]").forEach((el) => {
      el.classList.remove("pending", "active");
      el.classList.add("done");
    });
    progressFill.style.width = "100%";
    progressLabel.textContent = "100%";

    loaderPanel.classList.add("finished");
    loaderTitle.textContent = success ? "Terminé !" : "Échec pendant la génération";
    spinner.style.display = "none";

    bannerEl.hidden = false;
    bannerEl.classList.add(success ? "success" : "failure");
    bannerEl.querySelector(".status-text").textContent = success
      ? "Vidéo générée avec succès."
      : "Échec de la génération.";
  }

  async function poll() {
    try {
      const res = await fetch(pollUrl);
      const data = await res.json();
      const log = data.log || "";

      logEl.textContent = log;
      logEl.scrollTop = logEl.scrollHeight;
      updateFromLog(log);

      if (data.status === "done") {
        finish(!!data.success);
        return;
      }
    } catch (err) {
      /* transient network hiccup: keep polling */
    }
    setTimeout(poll, 800);
  }

  poll();
})();
