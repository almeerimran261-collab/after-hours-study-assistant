"""Local Ollama, or Groq restricted to the authored public sample."""
import requests

from src import config

GROQ_MODEL = "openai/gpt-oss-20b"


def complete(messages, retrieved_chunks):
    if config.DEMO_MODE:
        from src.public_demo import require_public_hits
        require_public_hits(retrieved_chunks)
        key = config.setting("GROQ_API_KEY").strip()
        if not key:
            raise RuntimeError("Set GROQ_API_KEY in the server's environment or Streamlit secrets.")
        messages = [dict(message) for message in messages]
        messages[0]["content"] += (
            " Copy citation brackets exactly: use square brackets, never parentheses. "
            "When asked what an acronym means, include its full expansion from the passage."
        )
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": GROQ_MODEL, "messages": messages, "temperature": 0,
            "max_completion_tokens": 2048, "reasoning_effort": "low",
            "reasoning_format": "hidden",
        }
        headers, timeout = {"Authorization": f"Bearer {key}"}, 90
        provider = "Groq"
    else:
        url = f"{config.OLLAMA_BASE_URL}/api/chat"
        payload = {
            "model": config.OLLAMA_MODEL_NAME, "messages": messages, "stream": False,
            "options": {"temperature": 0, "num_predict": 128, "num_ctx": 4096},
        }
        headers, timeout, provider = {}, 300, "Ollama"

    try:
        response = requests.post(
            url, json=payload, headers=headers, timeout=timeout, allow_redirects=False,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(f"{provider} did not finish within {timeout} seconds.") from None
    except requests.exceptions.RequestException:
        raise RuntimeError(f"Cannot contact {provider}. Check that the service is available.") from None
    if response.status_code != 200:
        hints = {
            401: "Check the server's API key.",
            403: "Check the account's model permissions.",
            404: "Check that the configured model is available.",
            429: "The free API quota or rate limit was reached. Try again later.",
        }
        raise RuntimeError(
            f"{provider} returned HTTP {response.status_code}. "
            + hints.get(response.status_code, "Try again later.")
        )
    try:
        data = response.json()
        if config.DEMO_MODE:
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise RuntimeError("Groq did not complete its answer. Try a shorter question.")
            answer = choice["message"]["content"]
        else:
            answer = data.get("message", {}).get("content", "")
        if not isinstance(answer, str):
            raise ValueError("Missing answer text")
    except (ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError(f"{provider} returned an unexpected response format.") from None
    return answer.strip()
