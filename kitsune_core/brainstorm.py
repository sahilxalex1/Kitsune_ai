"""Kitsune brainstorm subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .agent_protocol import *
from .ollama import *

def run_brainstorm(config, usage_tracker):
    print("\nDescribe what you're thinking about (an area, a rough idea, or an existing project to extend).")
    prompt = input("> ").strip()
    ollama_chat_stream(BRAINSTORM_SYSTEM_PROMPT, [{"role": "user", "content": prompt}], config["model"], config, usage_tracker, label="brainstorm")
    print("\n" + usage_tracker.summary())

