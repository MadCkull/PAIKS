import json
import urllib.request
import logging
from django.http import JsonResponse

from api.services.config import load_llm_config, save_llm_config
from api.services.llm_client import ollama_list_models

logger = logging.getLogger(__name__)

def status(request):
    cfg = load_llm_config()
    base_url = cfg.get("base_url", "http://localhost:11434").rstrip("/")
    provider = cfg.get("provider", "ollama")

    models: list[str] = []
    reachable = False
    error_msg = None

    try:
        if provider == "ollama":
            models = ollama_list_models(base_url)
            reachable = True
        else:
            req = urllib.request.Request(
                f"{base_url}/v1/models",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            models = [m["id"] for m in data.get("data", [])]
            reachable = True
    except Exception as exc:
        error_msg = str(exc)

    return JsonResponse({
        "reachable": reachable,
        "provider": provider,
        "base_url": base_url,
        "current_model": cfg.get("model"),
        "available_models": models,
        "error": error_msg,
    })

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
