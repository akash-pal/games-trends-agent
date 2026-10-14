"""Tiny client for a local Ollama server (standard library only).

Every model call in the project goes through chat_json(), so switching to
another provider later means rewriting this one file.

Ollama must be running ('ollama serve' or the Ollama app) with at least one
model pulled, for example:  ollama pull qwen2.5:7b
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import config


class LLMError(RuntimeError):
    """Anything that stops us getting a usable answer from the local model."""


_model: str | None = None


def _opener() -> urllib.request.OpenerDirector:
    # Never route a call to localhost through a system HTTP(S) proxy.
    host = urllib.parse.urlparse(config.ollama_url()).hostname
    if host in ("127.0.0.1", "localhost", "::1"):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def _unreachable(err: Exception) -> LLMError:
    reason = getattr(err, "reason", err)
    return LLMError(
        f"Can't reach Ollama at {config.ollama_url()} ({reason}). "
        "Start it with `ollama serve` (or open the Ollama app), or set OLLAMA_HOST."
    )


def _get(path: str, timeout: int = 10) -> dict:
    try:
        with _opener().open(config.ollama_url() + path, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError) as e:
        raise _unreachable(e) from e


def list_models() -> list[str]:
    return [m["name"] for m in _get("/api/tags").get("models", []) if m.get("name")]


def resolve_model() -> str:
    """Pick the model to use: OLLAMA_MODEL if set, else the only installed one."""
    global _model
    if _model:
        return _model
    installed = list_models()
    wanted = config.ollama_model()
    if wanted:
        candidates = [wanted] if ":" in wanted else [wanted, wanted + ":latest"]
        for c in candidates:
            if c in installed:
                _model = c
                return _model
        raise LLMError(
            f"Model '{wanted}' isn't installed in Ollama. Installed: "
            f"{', '.join(installed) or '(none)'}. Run `ollama pull {wanted}` "
            "or change OLLAMA_MODEL in .env."
        )
    if not installed:
        raise LLMError(
            "Ollama is running but has no models. Pull one, e.g. `ollama pull qwen2.5:7b`."
        )
    if len(installed) == 1:
        _model = installed[0]
        return _model
    raise LLMError(
        "Several models are installed, so I won't guess. Set OLLAMA_MODEL in .env "
        f"to one of: {', '.join(installed)}"
    )


def check() -> str:
    """Fail fast (before any fetching) if Ollama or the model isn't usable."""
    model = resolve_model()
    print(f"Ollama OK at {config.ollama_url()} using model '{model}'")
    return model


def chat_json(system: str, user: str, schema: dict, retries: int = 2) -> dict:
    """One chat call that must return a JSON object.

    Sends `schema` as Ollama's structured-output format. Older Ollama versions
    reject a schema (HTTP 400), so we fall back to plain JSON mode once. The
    system prompt should therefore also describe the expected shape in words.
    """
    payload = {
        "model": resolve_model(),
        "stream": False,
        "format": schema,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": 0, "num_ctx": config.OLLAMA_NUM_CTX},
    }
    last_problem = "no attempt made"
    for _ in range(retries + 1):
        req = urllib.request.Request(
            config.ollama_url() + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _opener().open(req, timeout=config.OLLAMA_TIMEOUT) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            if e.code == 400 and payload["format"] != "json":
                payload["format"] = "json"  # older Ollama: no schema support
                last_problem = f"schema rejected ({detail})"
                continue
            raise LLMError(f"Ollama returned HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, OSError) as e:
            raise _unreachable(e) from e

        content = (data.get("message") or {}).get("content") or ""
        try:
            parsed = json.loads(content)
        except ValueError:
            last_problem = f"reply wasn't valid JSON: {content[:120]!r}"
            continue
        if isinstance(parsed, dict):
            return parsed
        last_problem = "reply was JSON but not an object"
    raise LLMError(f"Model gave no usable answer ({last_problem}).")


if __name__ == "__main__":
    try:
        check()
    except LLMError as e:
        raise SystemExit(str(e))
