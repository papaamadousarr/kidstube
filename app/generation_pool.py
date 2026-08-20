import subprocess
import threading

# La génération vidéo (MoviePy/ffmpeg) sature vite un poste de travail : lancer
# des dizaines de builds en parallèle (ex. bouton "Générer toutes les vidéos
# en attente") a fait planter la machine. On borne donc le nombre de builds
# réellement actifs en même temps, quel que soit le nombre de jobs déclenchés.
MAX_CONCURRENT_BUILDS = 2

_semaphore = threading.Semaphore(MAX_CONCURRENT_BUILDS)

# Arrêt propre d'un lot de génération ("Générer toutes les vidéos en
# attente") : un job qui n'a pas encore démarré son subprocess renonce
# simplement (l'idée reste en statut "idea", reprise normalement au prochain
# lancement) ; un job déjà en cours reçoit un SIGTERM (pas SIGKILL) pour
# laisser ffmpeg/moviepy une chance de sortir proprement plutôt que d'être
# tué brutalement. Un fichier de sortie partiel éventuel est de toute façon
# écrasé sans risque à la prochaine génération réussie.
_stop_event = threading.Event()
_active_processes: set[subprocess.Popen] = set()
_process_lock = threading.Lock()


class build_slot:
    """Context manager bloquant jusqu'à ce qu'une place de build se libère."""

    def __enter__(self):
        _semaphore.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        _semaphore.release()
        return False


def is_stop_requested() -> bool:
    return _stop_event.is_set()


def clear_stop() -> None:
    _stop_event.clear()


def request_stop() -> None:
    _stop_event.set()
    with _process_lock:
        processes = list(_active_processes)
    for proc in processes:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass


def register_process(proc: subprocess.Popen) -> None:
    with _process_lock:
        _active_processes.add(proc)


def unregister_process(proc: subprocess.Popen) -> None:
    with _process_lock:
        _active_processes.discard(proc)
