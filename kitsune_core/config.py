"""Kitsune config subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .foundation import *

def model_for(config, mode_key):
    """Pick the model for a given mode ('router_model', 'chat_model', etc.), falling
    back to the general 'model' setting if that mode-specific key isn't set."""
    return config.get(mode_key) or config["model"]

def check_ollama_running():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except requests.exceptions.ConnectionError:
        sys.exit(
            f"Error: can't reach Ollama at {OLLAMA_URL}.\n"
            "  Make sure Ollama is installed and running (it should run automatically after\n"
            "  install; otherwise start it with: ollama serve"
        )
    except Exception as e:
        sys.exit(f"Error talking to Ollama: {e}")

def load_config(root):
    config = dict(DEFAULT_CONFIG)
    path = os.path.join(root, CONFIG_FILENAME)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: could not read {CONFIG_FILENAME} ({e}), using defaults.")
    return config

def ensure_config_file(root):
    path = os.path.join(root, CONFIG_FILENAME)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"Created default {CONFIG_FILENAME} in project folder (edit it to tune behavior).")
        return True  # freshly created -- nothing "recovered" from memory here
    return False

class UsageTracker:
    def __init__(self):
        self.prompt_tokens = 0
        self.output_tokens = 0

    def add(self, prompt_eval_count, eval_count):
        self.prompt_tokens += prompt_eval_count or 0
        self.output_tokens += eval_count or 0

    def summary(self):
        return f"Tokens used (local, free) -- prompt: {self.prompt_tokens:,} | generated: {self.output_tokens:,}"

