"""Script d'amorçage OAuth pour le serveur MCP officiel de Higgsfield.

À exécuter UNE SEULE FOIS, manuellement, dans ton propre terminal (jamais
appelé par l'app Flask). Ouvre ton navigateur pour le consentement Higgsfield,
puis sauvegarde le token dans secrets/higgsfield_token.json pour que l'app
puisse ensuite le recharger et le rafraîchir silencieusement.

Prérequis avant de lancer ce script :
1. Créer un compte sur https://higgsfield.ai (service payant, à crédits).
2. S'assurer d'avoir des crédits disponibles sur le compte.

Ce script se connecte exclusivement au serveur MCP officiel de Higgsfield
(https://mcp.higgsfield.ai/mcp) via un vrai flux OAuth — exactement comme le
ferait `claude mcp add`. Il n'utilise aucune méthode de contournement de la
protection anti-bot du site.
"""

import asyncio
import http.server
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = REPO_ROOT / "secrets"
TOKEN_PATH = SECRETS_DIR / "higgsfield_token.json"
CLIENT_INFO_PATH = SECRETS_DIR / "higgsfield_client_info.json"
SERVER_URL = "https://mcp.higgsfield.ai/mcp"
REDIRECT_PORT = 8722
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"


class FileTokenStorage:
    async def get_tokens(self) -> OAuthToken | None:
        if not TOKEN_PATH.exists():
            return None
        return OAuthToken.model_validate_json(TOKEN_PATH.read_text())

    async def set_tokens(self, tokens: OAuthToken) -> None:
        TOKEN_PATH.write_text(tokens.model_dump_json())

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        if not CLIENT_INFO_PATH.exists():
            return None
        return OAuthClientInformationFull.model_validate_json(CLIENT_INFO_PATH.read_text())

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        CLIENT_INFO_PATH.write_text(client_info.model_dump_json())


class _CallbackServer:
    """Petit serveur HTTP local pour récupérer le code d'autorisation OAuth
    renvoyé par le navigateur, sur le même principe que
    `InstalledAppFlow.run_local_server` utilisé pour l'OAuth YouTube."""

    def __init__(self, port: int) -> None:
        self.result: tuple[str | None, str | None] | None = None
        self._event = threading.Event()
        self._httpd = http.server.HTTPServer(("127.0.0.1", port), self._make_handler())

    def _make_handler(self):
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                code = params.get("code", [None])[0]
                state = params.get("state", [None])[0]
                outer.result = (code, state)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    "<html><body>Authentification Higgsfield réussie, "
                    "tu peux fermer cet onglet.</body></html>".encode("utf-8")
                )
                outer._event.set()

            def log_message(self, format, *args):
                pass

        return Handler

    def wait_for_code(self, timeout: float = 300.0) -> tuple[str, str | None]:
        thread = threading.Thread(target=self._httpd.handle_request, daemon=True)
        thread.start()
        if not self._event.wait(timeout):
            raise TimeoutError("Délai dépassé en attendant l'autorisation Higgsfield.")
        thread.join()
        code, state = self.result
        if not code:
            raise RuntimeError("Aucun code d'autorisation reçu de Higgsfield.")
        return code, state


async def _run() -> int:
    SECRETS_DIR.mkdir(exist_ok=True)
    callback_server = _CallbackServer(REDIRECT_PORT)

    async def redirect_handler(authorization_url: str) -> None:
        print(f"Ouverture du navigateur pour l'autorisation Higgsfield :\n{authorization_url}\n")
        webbrowser.open(authorization_url)

    async def callback_handler() -> tuple[str, str | None]:
        return await asyncio.to_thread(callback_server.wait_for_code)

    oauth = OAuthClientProvider(
        server_url=SERVER_URL,
        client_metadata=OAuthClientMetadata(
            redirect_uris=[REDIRECT_URI],
            client_name="Kidstube",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        ),
        storage=FileTokenStorage(),
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )

    try:
        async with streamablehttp_client(SERVER_URL, auth=oauth) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print(f"Connecté à Higgsfield MCP — {len(tools.tools)} outil(s) disponible(s) :")
                for tool in tools.tools:
                    print(f"  - {tool.name}")
    except Exception as exc:
        print(
            f"Échec de la connexion à Higgsfield MCP : {exc}\n\n"
            "Vérifie que ton compte https://higgsfield.ai existe bien et "
            "dispose de crédits, puis relance ce script.",
            file=sys.stderr,
        )
        return 1

    print(f"\nAuthentification réussie. Token sauvegardé dans {TOKEN_PATH}.")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
