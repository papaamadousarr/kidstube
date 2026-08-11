"""Script d'amorçage OAuth pour l'upload YouTube.

À exécuter UNE SEULE FOIS, manuellement, dans ton propre terminal (jamais
appelé par l'app Flask). Ouvre ton navigateur pour le consentement Google,
puis sauvegarde le token dans secrets/youtube_token.json pour que l'app
puisse ensuite le recharger et le rafraîchir silencieusement.

Prérequis avant de lancer ce script :
1. Créer un projet sur https://console.cloud.google.com/
2. Activer "YouTube Data API v3" pour ce projet
3. Configurer l'écran de consentement OAuth (mode "Test", t'ajouter
   toi-même comme testeur suffit pour un usage personnel)
4. Créer des identifiants OAuth 2.0 de type "Application de bureau"
   (PAS "Application Web")
5. Télécharger le fichier JSON et le placer dans secrets/client_secret.json
"""

import sys
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = REPO_ROOT / "secrets"
CLIENT_SECRET_PATH = SECRETS_DIR / "client_secret.json"
TOKEN_PATH = SECRETS_DIR / "youtube_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube",
]


def main() -> int:
    SECRETS_DIR.mkdir(exist_ok=True)

    if TOKEN_PATH.exists():
        # Important : ne PAS passer `scopes` ici. Si on le fait, google-auth utilise
        # la valeur passée telle quelle au lieu de lire les scopes réellement stockés
        # dans le fichier, et ce check serait alors toujours vrai même si le token
        # ne couvre pas les nouveaux scopes requis.
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
        has_all_scopes = set(SCOPES) <= set(creds.scopes or [])

        if creds.valid and has_all_scopes:
            print(f"Déjà authentifié avec tous les scopes nécessaires ({TOKEN_PATH}). Rien à faire.")
            return 0

        if creds.expired and creds.refresh_token and has_all_scopes:
            try:
                creds.refresh(Request())
            except RefreshError:
                print(
                    "Le refresh token a été révoqué ou a expiré "
                    "(courant après ~7 jours en mode Test OAuth) — nouvelle authentification nécessaire."
                )
            else:
                TOKEN_PATH.write_text(creds.to_json())
                print(f"Token rafraîchi et sauvegardé dans {TOKEN_PATH}.")
                return 0

        if not has_all_scopes:
            print("Le token existant ne couvre pas tous les scopes requis — nouvelle authentification nécessaire.")

    if not CLIENT_SECRET_PATH.exists():
        print(
            f"Fichier introuvable : {CLIENT_SECRET_PATH}\n\n"
            "Étapes avant de relancer ce script :\n"
            "1. https://console.cloud.google.com/ -> créer un projet\n"
            "2. Activer \"YouTube Data API v3\" ET \"YouTube Analytics API\"\n"
            "3. Configurer l'écran de consentement OAuth (mode Test, t'ajouter comme testeur)\n"
            "4. Créer des identifiants OAuth 2.0 de type \"Application de bureau\"\n"
            f"5. Télécharger le JSON et le placer dans {CLIENT_SECRET_PATH}",
            file=sys.stderr,
        )
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"Authentification réussie. Token sauvegardé dans {TOKEN_PATH}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
