import threading

# La génération vidéo (MoviePy/ffmpeg) sature vite un poste de travail : lancer
# des dizaines de builds en parallèle (ex. bouton "Générer toutes les vidéos
# en attente") a fait planter la machine. On borne donc le nombre de builds
# réellement actifs en même temps, quel que soit le nombre de jobs déclenchés.
MAX_CONCURRENT_BUILDS = 2

_semaphore = threading.Semaphore(MAX_CONCURRENT_BUILDS)


class build_slot:
    """Context manager bloquant jusqu'à ce qu'une place de build se libère."""

    def __enter__(self):
        _semaphore.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        _semaphore.release()
        return False
