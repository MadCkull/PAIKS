import json
import urllib.request
import logging
from django.http import JsonResponse

from api.services.config import (
    load_llm_config, save_llm_config,
    load_app_settings, get_cloud_models,
)
from api.services.llm_client import ollama_list_models

logger = logging.getLogger(__name__)


def _get_first_cloud_model(provider: str) -> str:
    """Return the first model from .env for the given provider, or '' if none."""
    models = get_cloud_models(provider)
    return models[0] if models else ""


def status(request):
    """Return combined local + cloud LLM status.

    Local Ollama models are always fetched.
    If cloud is enabled, cloud_models/cloud_model/cloud_key_set are also included.
    """
    settings = load_app_settings()
    models_cfg = settings.get("models", {})
    cloud_enabled = models_cfg.get("cloud_llm_enabled", False)

    # ── Always fetch local Ollama status ──────────────────────────────────
    cfg = load_llm_config()
    base_url = cfg.get("base_url", "http://localhost:11434").rstrip("/")
    provider = cfg.get("provider", "ollama")
    local_models: list[str] = []
    local_reachable = False
    error_msg = None

    try:
        if provider == "ollama":
            local_models = ollama_list_models(base_url)
            local_reachable = True
        else:
            req = urllib.request.Request(
                f"{base_url}/v1/models",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            local_models = [m["id"] for m in data.get("data", [])]
            local_reachable = True
    except Exception as exc:
        error_msg = str(exc)

    response = {
        "reachable": local_reachable,
        "provider": provider,
        "base_url": base_url,
        "current_model": cfg.get("model"),
        "available_models": local_models,
        "cloud_enabled": cloud_enabled,
        "error": error_msg,
    }

    # ── Append cloud info if enabled ──────────────────────────────────────
    if cloud_enabled:
        cloud_provider = models_cfg.get("cloud_provider", "Google Gemini")
        cloud_key = models_cfg.get("cloud_key", "").strip()

        # Model list comes ONLY from .env via get_cloud_models()
        cloud_models = get_cloud_models(cloud_provider)

        # Resolve active cloud_model: use saved value only if it's in the .env list,
        # otherwise snap to the first available model from .env.
        saved_model = models_cfg.get("cloud_model", "")
        if saved_model in cloud_models:
            cloud_model = saved_model
        elif cloud_models:
            cloud_model = cloud_models[0]
        else:
            cloud_model = ""

        response["cloud_models"] = cloud_models
        response["cloud_model"] = cloud_model
        response["cloud_provider"] = cloud_provider
        response["cloud_key_set"] = bool(cloud_key)
        # Note: cloud_key_valid is only checked on explicit validate_key calls (expensive)

    return JsonResponse(response)


def validate_key(request):
    """Test whether the saved cloud API key is valid by making a real API call.

    Returns:
        {"valid": True/False, "error": str|None}
    
    Called explicitly — not on every page load — because it makes a network request.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    settings = load_app_settings()
    models_cfg = settings.get("models", {})
    cloud_provider = models_cfg.get("cloud_provider", "Google Gemini")
    cloud_key = models_cfg.get("cloud_key", "").strip()

    if not cloud_key:
        return JsonResponse({"valid": False, "error": "No API key configured"})

    if cloud_provider == "Google Gemini":
        cloud_models = get_cloud_models(cloud_provider)
        test_model = cloud_models[0] if cloud_models else "gemini-flash-latest"
        try:
            import urllib.request as urlreq
            payload = json.dumps({
                "contents": [{"parts": [{"text": "hi"}]}]
            }).encode()
            req = urlreq.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{test_model}:generateContent",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": cloud_key,
                },
                method="POST",
            )
            with urlreq.urlopen(req, timeout=8) as resp:
                resp.read()
            return JsonResponse({"valid": True, "error": None})
        except urlreq.HTTPError as exc:
            # exc.code will be 400, 401, 403 etc.
            body = exc.read().decode(errors="ignore")
            if exc.code in [400, 401, 403] or "API_KEY_INVALID" in body:
                return JsonResponse({"valid": False, "error": "Invalid API key"})
            return JsonResponse({"valid": False, "error": f"Cloud API error ({exc.code}): {exc.reason}"})
        except Exception as exc:
            return JsonResponse({"valid": None, "error": f"Network or system error: {str(exc)}"})

    return JsonResponse({"valid": None, "error": f"Validation not implemented for {cloud_provider}"})


def config(request):
    try:
        payload = json.loads(request.body) if request.body else {}
    except ValueError:
        payload = {}
        
    base_url = payload.get("base_url", "").strip()
    model = payload.get("model", "").strip()
    provider = payload.get("provider", "ollama").strip()

    if not base_url or not model:
        return JsonResponse({"error": "base_url and model are required"}, status=400)

    cfg = {"base_url": base_url, "model": model, "provider": provider}
    save_llm_config(cfg)
    return JsonResponse({"status": "saved", **cfg})
