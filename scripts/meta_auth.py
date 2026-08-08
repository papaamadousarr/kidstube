"""Script d'amorçage OAuth pour Facebook Page (et, plus tard, Instagram Reels)
via l'API Graph de Meta.

À exécuter UNE SEULE FOIS, manuellement, dans ton propre terminal. Ouvre le
navigateur pour le consentement Meta, puis échange le code contre un token
Page longue durée (n'expire pas tant que tu restes admin de la Page) —
sauvegardé dans secrets/meta_token.json.

Prérequis avant de lancer ce script :
1. Créer une app sur https://developers.facebook.com/apps/
2. Ajouter le produit "Facebook Login for Business" (ou "Facebook Login")
3. Dans les paramètres du produit, ajouter comme Valid OAuth Redirect URI :
   https://papaamadousarr.github.io/kidstube/tiktok-callback.html
   (page générique déjà utilisée pour TikTok — elle affiche juste le code
   reçu dans l'URL, rien de spécifique à une plateforme)
4. Mettre META_APP_ID et META_APP_SECRET dans secrets/.env
5. Tant que l'app est en mode Development, seuls les admins/testeurs de
   l'app (toi) peuvent s'authentifier — donc pas besoin d'App Review pour
   ton propre usage sur ta propre Page.
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = REPO_ROOT / "secrets"
TOKEN_PATH = SECRETS_DIR / "meta_token.json"

load_dotenv(SECRETS_DIR / ".env")

APP_ID = os.getenv("META_APP_ID")
APP_SECRET = os.getenv("META_APP_SECRET")
REDIRECT_URI = os.getenv("META_REDIRECT_URI", "https://papaamadousarr.github.io/kidstube/tiktok-callback.html")

GRAPH_API_VERSION = "v23.0"
AUTHORIZE_URL = "https://www.facebook.com/v23.0/dialog/oauth"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# pages_manage_posts entraîne automatiquement pages_show_list et
# pages_read_engagement (ils ne peuvent pas être demandés seuls).
SCOPES = "pages_show_list,pages_read_engagement,pages_manage_posts"


def main() -> int:
    SECRETS_DIR.mkdir(exist_ok=True)

    if not APP_ID or not APP_SECRET:
        print(
            "META_APP_ID et/ou META_APP_SECRET manquants dans secrets/.env.\n\n"
            "Étapes avant de relancer ce script :\n"
            "1. https://developers.facebook.com/apps/ -> créer une app\n"
            "2. Ajouter le produit \"Facebook Login for Business\"\n"
            "3. Ajouter comme Valid OAuth Redirect URI : "
            f"{REDIRECT_URI}\n"
            "4. Copier App ID et App Secret dans secrets/.env",
            file=sys.stderr,
        )
        return 1

    query = urlencode(
        {
            "client_id": APP_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "response_type": "code",
        }
    )
    print(f"Ouvre ce lien pour autoriser l'app Meta :\n{AUTHORIZE_URL}?{query}\n")
    print("Une fois autorisé, tu es redirigé vers une page qui affiche un code.")
    code = input("Code d'autorisation : ").strip()
    if not code:
        print("Aucun code saisi.", file=sys.stderr)
        return 1

    # 1. Code -> token utilisateur courte durée
    short_lived = requests.get(
        f"{GRAPH_URL}/oauth/access_token",
        params={
            "client_id": APP_ID,
            "redirect_uri": REDIRECT_URI,
            "client_secret": APP_SECRET,
            "code": code,
        },
        timeout=30,
    ).json()
    if "access_token" not in short_lived:
        print(f"Échec de l'échange du code : {short_lived}", file=sys.stderr)
        return 1

    # 2. Token utilisateur courte durée -> longue durée (~60 jours)
    long_lived = requests.get(
        f"{GRAPH_URL}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "fb_exchange_token": short_lived["access_token"],
        },
        timeout=30,
    ).json()
    if "access_token" not in long_lived:
        print(f"Échec de l'extension du token : {long_lived}", file=sys.stderr)
        return 1

    # 3. Token utilisateur longue durée -> token Page (n'expire pas tant que
    # tu restes admin de la Page).
    pages = requests.get(
        f"{GRAPH_URL}/me/accounts",
        params={"access_token": long_lived["access_token"]},
        timeout=30,
    ).json()
    if "data" not in pages or not pages["data"]:
        print(f"Aucune Page trouvée pour ce compte : {pages}", file=sys.stderr)
        return 1

    if len(pages["data"]) > 1:
        print("Plusieurs Pages trouvées, choisis-en une :")
        for i, page in enumerate(pages["data"]):
            print(f"  [{i}] {page['name']} ({page['id']})")
        choice = int(input("Numéro : ").strip())
        page = pages["data"][choice]
    else:
        page = pages["data"][0]

    token_data = {
        "page_id": page["id"],
        "page_name": page["name"],
        "page_access_token": page["access_token"],
    }

    # Compte Instagram Business/Creator lié à cette Page, si présent (requis
    # pour instagram_client.py — publication de Reels).
    ig_lookup = requests.get(
        f"{GRAPH_URL}/{page['id']}",
        params={"fields": "instagram_business_account", "access_token": page["access_token"]},
        timeout=30,
    ).json()
    ig_account = ig_lookup.get("instagram_business_account")
    if ig_account:
        token_data["ig_user_id"] = ig_account["id"]

    TOKEN_PATH.write_text(json.dumps(token_data, indent=2))
    print(f"\nAuthentification réussie pour la Page « {page['name']} ». Token sauvegardé dans {TOKEN_PATH}.")
    if ig_account:
        print(f"Compte Instagram lié détecté (ig_user_id={ig_account['id']}) — prêt pour instagram_client.py.")
    else:
        print(
            "Aucun compte Instagram Business/Creator lié à cette Page — "
            "instagram_client.py ne fonctionnera pas tant qu'un compte n'est pas lié "
            "(Meta Business Suite -> Paramètres -> Comptes liés)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
