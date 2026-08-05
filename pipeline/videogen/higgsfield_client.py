import asyncio
import json
import math
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SECRETS_DIR = REPO_ROOT / "secrets"
TOKEN_PATH = SECRETS_DIR / "higgsfield_token.json"
CLIENT_INFO_PATH = SECRETS_DIR / "higgsfield_client_info.json"
SERVER_URL = "https://mcp.higgsfield.ai/mcp"


class HiggsfieldError(Exception):
    pass


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


def is_connected() -> bool:
    return TOKEN_PATH.exists()


NOT_CONNECTED_MESSAGE = (
    "Compte Higgsfield non connecté. Lance `python scripts/higgsfield_auth.py` "
    "dans un terminal pour autoriser l'accès une première fois."
)


async def _refused_redirect(_url: str) -> None:
    raise HiggsfieldError(NOT_CONNECTED_MESSAGE)


async def _refused_callback() -> tuple[str, str | None]:
    raise HiggsfieldError(NOT_CONNECTED_MESSAGE)


def _build_oauth() -> OAuthClientProvider:
    return OAuthClientProvider(
        server_url=SERVER_URL,
        client_metadata=OAuthClientMetadata(
            redirect_uris=["http://127.0.0.1:8722/callback"],
            client_name="Kidstube",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        ),
        storage=FileTokenStorage(),
        redirect_handler=_refused_redirect,
        callback_handler=_refused_callback,
    )


def _find_tool(tools, *keywords: str):
    for tool in tools:
        name = tool.name.lower()
        if all(kw in name for kw in keywords):
            return tool
    return None


def _extract_payload(result) -> dict:
    if result.isError:
        text = "; ".join(
            block.text for block in result.content if getattr(block, "type", None) == "text"
        )
        raise HiggsfieldError(f"Higgsfield a renvoyé une erreur : {text or result.content}")

    if result.structuredContent is not None:
        return result.structuredContent

    for block in result.content:
        if getattr(block, "type", None) == "text":
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                continue

    if not result.content:
        return {}

    raise HiggsfieldError("Réponse Higgsfield illisible (pas de contenu JSON exploitable).")


def _unwrap_exception_group(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        leaves: list[BaseException] = []
        for sub in exc.exceptions:
            leaves.extend(_unwrap_exception_group(sub))
        return leaves
    return [exc]


async def _with_session(coro_fn):
    if not is_connected():
        raise HiggsfieldError(NOT_CONNECTED_MESSAGE)

    oauth = _build_oauth()
    try:
        async with streamablehttp_client(SERVER_URL, auth=oauth) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await coro_fn(session)
    except HiggsfieldError:
        raise
    except BaseExceptionGroup as exc:
        # streamablehttp_client/ClientSession run their I/O in anyio TaskGroups, so any
        # error raised inside coro_fn (including our own HiggsfieldError) comes back
        # wrapped in a BaseExceptionGroup whose default str() is just "unhandled errors
        # in a TaskGroup (N sub-exception)" — unwrap it to surface the real cause.
        leaves = _unwrap_exception_group(exc)
        higgsfield_errors = [leaf for leaf in leaves if isinstance(leaf, HiggsfieldError)]
        if higgsfield_errors:
            raise higgsfield_errors[0]
        if len(leaves) == 1:
            raise HiggsfieldError(f"Échec de l'appel à Higgsfield MCP : {leaves[0]}") from leaves[0]
        details = "; ".join(f"{type(leaf).__name__}: {leaf}" for leaf in leaves)
        raise HiggsfieldError(f"Échec de l'appel à Higgsfield MCP : {details}") from exc
    except Exception as exc:
        raise HiggsfieldError(f"Échec de l'appel à Higgsfield MCP : {exc}") from exc


def _run(coro_fn):
    return asyncio.run(_with_session(coro_fn))


DEFAULT_MODEL = "cinematic_studio_3_0"
MIN_DURATION_SECONDS = 4
MAX_DURATION_SECONDS = 15

_VIDEO_URL_KEYS = ("video_url", "url", "output_url", "media_url", "result_url")
_NESTED_PAYLOAD_KEYS = ("result", "output", "outputs", "data", "generation", "media")


def _find_video_url(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in _VIDEO_URL_KEYS:
        if payload.get(key):
            return payload[key]
    for nested_key in _NESTED_PAYLOAD_KEYS:
        nested = payload.get(nested_key)
        if isinstance(nested, list) and nested:
            nested = nested[0]
        if isinstance(nested, dict):
            for key in _VIDEO_URL_KEYS:
                if nested.get(key):
                    return nested[key]
    return None


def generate_video(
    prompt: str,
    reference_image_path: str | None,
    aspect_ratio: str,
    target_duration: float | None = None,
    model: str = DEFAULT_MODEL,
) -> str:
    """Lance une génération vidéo réaliste sur Higgsfield, retourne l'identifiant du job.

    Le tool officiel `generate_video` attend ses paramètres imbriqués sous une clé
    `params` (schéma confirmé par introspection réelle du serveur), avec `model`
    obligatoire. `target_duration` (durée de la narration associée) est convertie en
    une durée de clip explicite pour éviter de payer par défaut un clip de 15s quand
    la voix off ne dure que quelques secondes — le serveur applique de toute façon un
    clamp interne si le modèle utilisé a une plage différente.

    reference_image_path n'est pas encore câblé (nécessiterait un appel préalable à
    media_upload pour obtenir un UUID de média) — laissé à None pour l'instant.
    """

    async def action(session: ClientSession) -> str:
        tools = (await session.list_tools()).tools
        tool = _find_tool(tools, "video", "generate") or _find_tool(tools, "video")
        if tool is None:
            raise HiggsfieldError(
                "Aucun outil de génération vidéo trouvé sur le serveur Higgsfield MCP."
            )

        params = {"model": model, "prompt": prompt, "aspect_ratio": aspect_ratio}
        if target_duration:
            params["duration"] = max(
                MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, math.ceil(target_duration))
            )

        result = await session.call_tool(tool.name, {"params": params})
        payload = _extract_payload(result)

        notice = payload.get("notice") if isinstance(payload, dict) else None
        if isinstance(notice, dict) and notice.get("type") == "preset_recommendation":
            declined_id = (
                notice.get("data", {}).get("retry_literal_with", {}).get("declined_preset_id")
            )
            retry_params = dict(params)
            if declined_id:
                retry_params["declined_preset_id"] = declined_id
            result = await session.call_tool(tool.name, {"params": retry_params})
            payload = _extract_payload(result)

        job_id = payload.get("job_id") or payload.get("jobId") or payload.get("id")
        if not job_id:
            raise HiggsfieldError(f"Réponse Higgsfield inattendue (pas d'identifiant de job) : {payload}")
        return str(job_id)

    return _run(action)


DEFAULT_IMAGE_MODEL = "nano_banana_2"


def generate_image(prompt: str, aspect_ratio: str, model: str = DEFAULT_IMAGE_MODEL) -> str:
    """Lance une génération d'image sur Higgsfield (illustrations pour le pipeline
    podcast), retourne l'identifiant du job — à suivre ensuite avec poll_job(),
    exactement comme pour generate_video."""

    async def action(session: ClientSession) -> str:
        tools = (await session.list_tools()).tools
        tool = _find_tool(tools, "generate_image") or _find_tool(tools, "image", "generate")
        if tool is None:
            raise HiggsfieldError(
                "Aucun outil de génération d'image trouvé sur le serveur Higgsfield MCP."
            )

        params = {"model": model, "prompt": prompt, "aspect_ratio": aspect_ratio}
        result = await session.call_tool(tool.name, {"params": params})
        payload = _extract_payload(result)

        notice = payload.get("notice") if isinstance(payload, dict) else None
        if isinstance(notice, dict) and notice.get("type") == "preset_recommendation":
            declined_id = (
                notice.get("data", {}).get("retry_literal_with", {}).get("declined_preset_id")
            )
            retry_params = dict(params)
            if declined_id:
                retry_params["declined_preset_id"] = declined_id
            result = await session.call_tool(tool.name, {"params": retry_params})
            payload = _extract_payload(result)

        job_id = payload.get("job_id") or payload.get("jobId") or payload.get("id")
        if not job_id:
            raise HiggsfieldError(f"Réponse Higgsfield inattendue (pas d'identifiant de job) : {payload}")
        return str(job_id)

    return _run(action)


def poll_job(job_id: str) -> dict:
    """Interroge le statut d'un job de génération. Retourne
    {"status": "running", "raw": payload} ou {"status": "done", "video_url": ...}."""

    async def action(session: ClientSession) -> dict:
        tools = (await session.list_tools()).tools
        tool = (
            _find_tool(tools, "job_status")
            or _find_tool(tools, "job", "status")
            or _find_tool(tools, "status")
        )
        if tool is None:
            raise HiggsfieldError("Aucun outil de suivi de job trouvé sur le serveur Higgsfield MCP.")

        schema_props = (tool.inputSchema or {}).get("properties", {})
        args = {}
        for key in ("jobId", "job_id", "id"):
            if key in schema_props:
                args[key] = job_id
                break
        if "sync" in schema_props:
            args["sync"] = True

        result = await session.call_tool(tool.name, args)
        payload = _extract_payload(result)

        status = str(payload.get("status") or payload.get("state") or "").lower()
        video_url = _find_video_url(payload)

        if status in ("failed", "error"):
            raise HiggsfieldError(f"Génération Higgsfield échouée : {payload.get('error', payload)}")
        if video_url and (not status or status in ("completed", "done", "succeeded", "success")):
            return {"status": "done", "video_url": video_url}
        return {"status": "running", "raw": payload}

    return _run(action)


def download_result(video_url: str, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", video_url, timeout=120, follow_redirects=True) as response:
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)
