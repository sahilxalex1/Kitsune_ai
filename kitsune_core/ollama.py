"""Kitsune ollama subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .foundation import *

def ollama_chat_stream(system_prompt, messages, model, config, usage_tracker, json_mode=False, label="model"):
    """Stream a chat completion from Ollama's /api/chat endpoint, print live, return full text."""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "stream": True,
        "options": {"num_ctx": config.get("context_window", 8192)},
    }
    if json_mode:
        payload["format"] = "json"

    print(f"\n[{label} thinking...]")
    full_text = ""
    prompt_eval_count = 0
    eval_count = 0

    try:
        with requests.post(f"{OLLAMA_URL}/api/chat", json=payload, stream=True, timeout=600) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                if content:
                    print(content, end="", flush=True)
                    full_text += content
                if chunk.get("done"):
                    prompt_eval_count = chunk.get("prompt_eval_count", 0)
                    eval_count = chunk.get("eval_count", 0)
    except requests.exceptions.ConnectionError:
        sys.exit(f"\nError: lost connection to Ollama at {OLLAMA_URL}. Is it still running?")

    print()
    usage_tracker.add(prompt_eval_count, eval_count)
    return full_text.strip()

