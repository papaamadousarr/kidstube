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
3. Dans les paramètres de l'app (produit Login Kit), ajouter comme redirect
   URI Web : https://papaamadousarr.github.io/kidstube/tiktok-callback.html
   (TikTok exige une URI Web en HTTPS ou un domaine de confiance — un simple
   http://localhost ne suffit pas seul).
4. Mettre TIKTOK_CLIENT_KEY et TIKTOK_CLIENT_SECRET dans secrets/.env.

Pour tester en Sandbox avant l'audit TikTok (nécessaire pour enregistrer la
vidéo de démo de l'App Review) : ajoute ton compte comme Target User dans
l'onglet Sandbox du portail, mets TIKTOK_SANDBOX_CLIENT_KEY et
TIKTOK_SANDBOX_CLIENT_SECRET dans secrets/.env, puis lance ce script avec
`--sandbox`. Le token sandbox est sauvegardé séparément
(secrets/tiktok_sandbox_token.json) pour ne jamais se mélanger avec celui de
Production.
"""

import argparse
import base64
import hashlib
import json
import os
import secrets as secrets_lib
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = REPO_ROOT / "secrets"

load_dotenv(SECRETS_DIR / ".env")

# Page statique hébergée sur GitHub Pages (docs/tiktok-callback.html) qui
# affiche le code d'autorisation à copier-coller ici — TikTok exige une
# redirect URI Web en HTTPS (ou un domaine de confiance), un simple serveur
# loopback local ne suffit plus comme unique méthode d'autorisation.
REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "https://papaamadousarr.github.io/kidstube/tiktok-callback.html")
SCOPES = "video.publish"

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


def _new_pkce_pair() -> tuple[str, str]:
    """TikTok exige PKCE (RFC 7636) sur ce flow : le code_verifier est un
    secret gardé côté client, le code_challenge (son hash) part dans l'URL
    d'autorisation, et le code_verifier original est renvoyé à l'échange du
    token pour prouver que c'est bien le même client des deux côtés."""
    code_verifier = secrets_lib.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def _get_auth_code(client_key: str, code_challenge: str) -> str:
    query = urlencode(
        {
            "client_key": client_key,
            "scope": SCOPES,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "state": "kidstube",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    url = f"{AUTHORIZE_URL}?{query}"
    print(f"Ouverture du navigateur pour le consentement TikTok :\n{url}")
    webbrowser.open(url)

    print(
        "\nUne fois autorisé, TikTok te redirige vers une page qui affiche un code.\n"
        "Copie-le et colle-le ici."
    )
    code = input("Code d'autorisation : ").strip()
    if not code:
        raise RuntimeError("Aucun code d'autorisation saisi.")
    return code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Utilise les credentials et le token Sandbox au lieu de Production.",
    )
    args = parser.parse_args()

    SECRETS_DIR.mkdir(exist_ok=True)

    if args.sandbox:
        client_key = os.getenv("TIKTOK_SANDBOX_CLIENT_KEY")
        client_secret = os.getenv("TIKTOK_SANDBOX_CLIENT_SECRET")
        token_path = SECRETS_DIR / "tiktok_sandbox_token.json"
        env_var_hint = "TIKTOK_SANDBOX_CLIENT_KEY et/ou TIKTOK_SANDBOX_CLIENT_SECRET"
    else:
        client_key = os.getenv("TIKTOK_CLIENT_KEY")
        client_secret = os.getenv("TIKTOK_CLIENT_SECRET")
        token_path = SECRETS_DIR / "tiktok_token.json"
        env_var_hint = "TIKTOK_CLIENT_KEY et/ou TIKTOK_CLIENT_SECRET"

    if not client_key or not client_secret:
        print(
            f"{env_var_hint} manquants dans secrets/.env.\n\n"
            "Étapes avant de relancer ce script :\n"
            "1. https://developers.tiktok.com/ -> créer une app\n"
            "2. Demander l'accès au produit \"Content Posting API\"\n"
            "3. Ajouter la redirect URI Web "
            "https://papaamadousarr.github.io/kidstube/tiktok-callback.html\n"
            f"4. Copier Client Key et Client Secret dans secrets/.env ({env_var_hint})",
            file=sys.stderr,
        )
        return 1

    code_verifier, code_challenge = _new_pkce_pair()
    code = _get_auth_code(client_key, code_challenge)

    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
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
    token_path.write_text(json.dumps(token_data, indent=2))
    print(f"Authentification réussie. Token sauvegardé dans {token_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
