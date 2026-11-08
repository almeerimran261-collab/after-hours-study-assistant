import re
import warnings
from getpass import GetPassWarning, getpass

import requests

from src.generator import (
    _clean_and_validate_answer_with_reason,
    _remove_think_trace,
)


MODEL = "openai/gpt-oss-20b"
SOURCE = "public_demo_notes.txt"

PASSAGE = (
    "These are original synthetic demonstration notes. "
    "A stack follows Last In, First Out (LIFO): "
    "the last item added is the first item removed."
)


def main():
    print("This test sends only a synthetic demo passage to Groq.")

    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        try:
            api_key = getpass(
                "Paste your Groq API key (hidden): "
            ).strip()
        except GetPassWarning:
            print(
                "Hidden input is unavailable. "
                "Run this in your PowerShell terminal."
            )
            return 1

    if not api_key:
        print("No API key entered. Test stopped.")
        return 1

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": (
                "Answer briefly using only the supplied passage. "
                "If asked what an acronym means, include its full expansion "
                "from the passage. "
                f"End with this exact citation: [{SOURCE}, p. 1] "
                "Keep the square brackets; do not use parentheses. "
                "Return only the answer and citation."
            )},
            {
                "role": "user",
                "content": (
                    f"[{SOURCE}, p. 1]\n{PASSAGE}\n\n"
                    "Question: What does LIFO mean?"
                ),
            },
        ],
        "temperature": 0,
        "max_completion_tokens": 1024,
        "reasoning_effort": "low",
        "reasoning_format": "hidden",
    }

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            json=payload,
            timeout=90,
            allow_redirects=False,
        )
    except requests.exceptions.RequestException as exc:
        print(
            f"Could not contact Groq ({type(exc).__name__})."
        )
        return 1

    if response.status_code != 200:
        explanations = {
            401: "The API key was rejected. Check it in Groq Console.",
            403: "Check your account access and model permissions.",
            404: "The configured model or endpoint is unavailable.",
            429: "A free-plan rate or quota limit was reached.",
        }
        print(f"Groq returned HTTP {response.status_code}.")
        print(
            explanations.get(
                response.status_code,
                "Request failed. Send this status code.",
            )
        )
        return 1

    try:
        data = response.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Missing answer text")
    except (ValueError, KeyError, IndexError, TypeError):
        print("Groq returned an unexpected response format.")
        return 1
    cleaned = _remove_think_trace(content)

    print(f"\nHTTP status: {response.status_code}")
    print("Finish reason:", choice.get("finish_reason"))
    print("Final text length:", len(cleaned))
    print("Cleaned final text:", repr(cleaned[:1200]))
    print(
        "Completion tokens:",
        (data.get("usage") or {}).get("completion_tokens"),
    )

    if not cleaned:
        print("CHECK: Groq returned no final answer text.")
        return 1
    answer, reason = _clean_and_validate_answer_with_reason(
        cleaned,
        [{"source": SOURCE, "page": 1}],
    )

    print(f"\nModel: {MODEL}")
    print(f"Answer: {answer}")
    print(f"Citation check: {reason}")

    words = " ".join(
        re.findall(r"\w+", answer.casefold())
    )
    passed = (
        reason == "answered_with_validated_citation"
        and "last in first out" in words
    )

    if passed:
        print("PASS: connection and basic cited answer.")
    else:
        print("CHECK: answer or citation needs review.")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())