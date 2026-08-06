"""Script d'amorçage OAuth pour la publication TikTok (Content Posting API).

À exécuter UNE SEULE FOIS, manuellement, dans ton propre terminal (jamais
appelé par l'app Flask). Ouvre ton navigateur pour le consentement TikTok,
puis sauvegarde le token dans secrets/tiktok_token.json pour que l'app
puisse ensuite le recharger et le rafraîchir silencieusement.

Prérequis avant de lancer ce script :
1. Créer une app sur https://developers.tiktok.com/
2. Demander l'accès au produit "Content Posting API" (scope video.publish)
   — tant que l'app n'est pas auditée par TikTok, les vidéos publiées via
   l'API restent en visibilité SELF_ONLY (privées), même si le code demande
   PUBLIC_TO_EVERYONE.
3. Dans les paramètres de l'app, ajouter la redirect URI
   http://localhost:8080/callback (ou une autre valeur, à condition de la
   mettre aussi dans TIKTOK_REDIRECT_URI ci-dessous).
4. Mettre TIKTOK_CLIENT_KEY et TIKTOK_CLIENT_SECRET dans secrets/.env.
"""

import json
import os
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = REPO_ROOT / "secrets"
TOKEN_PATH = SECRETS_DIR / "tiktok_token.json"

load_dotenv(SECRETS_DIR / ".env")

CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8080/callback")
SCOPES = "video.publish"

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


class _CallbackHandler(BaseHTTPRequestHandler):
    auth_code: str | None = None

    def do_GET(self) -> None:  # noqa: N802 (nom imposé par BaseHTTPRequestHandler)
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            _CallbackHandler.auth_code = params["code"][0]
            body = b"Authentification TikTok reussie, tu peux fermer cet onglet."
        else:
            body = b"Echec de l'authentification TikTok (pas de code recu)."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # silence les logs HTTP par défaut
        pass


def _get_auth_code() -> str:
    query = urlencode(
        {
            "client_key": CLIENT_KEY,
            "scope": SCOPES,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "state": "kidstube",
        }
    )
    url = f"{AUTHORIZE_URL}?{query}"
    print(f"Ouverture du navigateur pour le consentement TikTok :\n{url}")
    webbrowser.open(url)

    parsed = urlparse(REDIRECT_URI)
    server = HTTPServer((parsed.hostname, parsed.port), _CallbackHandler)
    server.handle_request()  # bloque jusqu'à la première requête reçue

    if not _CallbackHandler.auth_code:
        raise RuntimeError("Aucun code d'autorisation reçu depuis TikTok.")
    return _CallbackHandler.auth_code


def main() -> int:
    SECRETS_DIR.mkdir(exist_ok=True)

    if not CLIENT_KEY or not CLIENT_SECRET:
        print(
            "TIKTOK_CLIENT_KEY et/ou TIKTOK_CLIENT_SECRET manquants dans secrets/.env.\n\n"
            "Étapes avant de relancer ce script :\n"
            "1. https://developers.tiktok.com/ -> créer une app\n"
            "2. Demander l'accès au produit \"Content Posting API\"\n"
            "3. Ajouter la redirect URI http://localhost:8080/callback (ou définir "
            "TIKTOK_REDIRECT_URI dans secrets/.env avec la valeur choisie)\n"
            "4. Copier Client Key et Client Secret dans secrets/.env",
            file=sys.stderr,
        )
        return 1

    code = _get_auth_code()

    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    response.raise_for_status()
    token_data = response.json()
    if "access_token" not in token_data:
        print(f"Réponse inattendue de TikTok : {token_data}", file=sys.stderr)
        return 1

    # obtained_at permet au client de calculer l'expiration sans dépendre
    # d'un objet Credentials comme pour Google — TikTok ne renvoie qu'une
    # durée relative (expires_in), pas une date d'expiration absolue.
    token_data["obtained_at"] = time.time()
    TOKEN_PATH.write_text(json.dumps(token_data, indent=2))
    print(f"Authentification réussie. Token sauvegardé dans {TOKEN_PATH}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
