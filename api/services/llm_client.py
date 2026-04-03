import urllib.request
import urllib.parse
import json

def ollama_list_models(base_url: str) -> list[str]:
    """Return model names available in a running Ollama instance."""
    url = base_url.rstrip("/") + "/api/tags"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
    return [m["name"] for m in data.get("models", [])]

def call_local_llm(prompt: str, cfg: dict) -> str:
    """
    Send a prompt to the configured local LLM and return the text response.
    Supports:
      - Ollama native API
      - OpenAI-compatible
    """
    base_url = cfg.get("base_url", "http://localhost:11434").rstrip("/")
    model = cfg.get("model", "llama3.2")
    provider = cfg.get("provider", "ollama")

    payload: dict
    endpoint: str

    if provider == "ollama":
        endpoint = f"{base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 300,
                "temperature": 0.3,
                "num_ctx": 4096,
            },
        }
    else:
        endpoint = f"{base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 200,
            "stream": False,
        }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read())

    if provider == "ollama":
        return result.get("response", "").strip()
    else:
        return result["choices"][0]["message"]["content"].strip()
