"""Kitsune models subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .memory_types import *
from .storage import *

def describe_model_relevance(model, role):
    """Gathers the signals the spec asks for -- installed?, recently used?, is there
    a newer/preferred alternative that IS installed? -- without taking any action."""
    env = load_environment_memory()
    last_used = env["model_last_used"].get(model)
    preferred = env["preferred_models"].get(role) if role else None
    return {
        "age_days": days_since(last_used),
        "newer_alt": preferred if preferred and preferred != model else None,
    }

def ensure_model_available(model, available_models, role=None, project_status="active", source="direct"):
    """Replaces the old unconditional auto-pull. Memory -- an old per-project config,
    a resumed session -- can only SUGGEST a model is needed; it never triggers a
    download by itself. Every path here ends in either using an already-installed
    model (no action), or an explicit, reasoned confirmation prompt before Ollama
    ever downloads anything. Returns the model name that should actually be used
    (which may differ from `model` if the user opts into an already-installed
    alternative) -- callers should assign the return value back into config['model'].
    """
    base_name = model.split(":")[0]
    installed = any(m == model or m.startswith(base_name + ":") or m == base_name for m in available_models)

    if installed:
        record_model_used(model, role=role)
        MEMORY_LOG.accepted(f"model '{model}'", "already installed -- using it, no download needed")
        return model

    info = describe_model_relevance(model, role)
    print(f"\nModel '{model}' is not installed.")
    if source == "memory":
        print("  (This came from previously saved memory, not something you just asked for.)")
    print(f"  Last used successfully: {info['age_days']} day(s) ago" if info["age_days"] is not None
          else "  Last used successfully: never recorded")
    print(f"  Project status: {project_status}")
    if info["newer_alt"]:
        print(f"  A different, currently preferred model for this role IS installed: '{info['newer_alt']}'")

    if info["newer_alt"] and info["newer_alt"] in available_models:
        if input(f"Use the already-installed '{info['newer_alt']}' instead? [Y/n] ").strip().lower() != "n":
            MEMORY_LOG.accepted(f"model '{info['newer_alt']}'",
                                 f"substituted for unavailable '{model}' -- already installed and preferred")
            record_model_used(info["newer_alt"], role=role)
            return info["newer_alt"]

    if input(f"Pull '{model}' now via Ollama? This may be a large download. [y/N] ").strip().lower() != "y":
        MEMORY_LOG.ignored(f"model '{model}'", "not installed and download declined -- no action taken")
        sys.exit(f"Aborting: '{model}' isn't installed and wasn't pulled. "
                 f"Run 'ollama pull {model}' manually, or pick a different model with --model.")

    print(f"Pulling '{model}' now (this may take a while)...")
    try:
        subprocess.run(["ollama", "pull", model], check=True)
    except Exception as e:
        sys.exit(f"Error pulling model: {e}\nTry manually: ollama pull {model}")
    MEMORY_LOG.accepted(f"model '{model}'", "pulled after explicit user confirmation")
    record_model_used(model, role=role)
    return model

