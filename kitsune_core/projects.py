"""Kitsune projects subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .foundation import *
from .repo import *

CONTROL_ENTRIES = {"kitsune.py", "kitsune_gui.py", CONFIG_FILENAME, MEMORY_FILENAME, ATTEMPTS_FILENAME,
                    PROJECT_MARKER_FILENAME, "REVIEW.md",
                    INDEX_FILENAME, "__pycache__", ".git", ".gitignore", ".venv", "venv"}

def slugify(text, max_words=6, max_len=50):
    words = re.findall(r"[A-Za-z0-9]+", (text or "").lower())[:max_words]
    slug = "-".join(words)[:max_len].strip("-")
    return slug or "project"

def _resolve_root(path_str):
    root = os.path.abspath(path_str or ".")
    if not os.path.isdir(root):
        if input(f"'{root}' doesn't exist. Create it? [y/N] ").strip().lower() == "y":
            os.makedirs(root, exist_ok=True)
        else:
            print("Aborting.")
            return None

    script_dir = os.path.dirname(SELF_PATH)
    if root == script_dir:
        print(
            "\n⚠ Warning: this project folder is the SAME folder the kitsune.py script\n"
            "  lives in. The agent's own file is protected from writes/edits, but it will still\n"
            "  see and can affect every other file here (including any personal files you keep\n"
            "  in this folder). Strongly recommended: use a dedicated subfolder instead, e.g.\n"
            f"  {os.path.join(script_dir, 'my-project')}\n"
        )
        if input("Continue anyway in this folder? [y/N] ").strip().lower() != "y":
            print("Aborting -- pick a project subfolder instead.")
            return None

    return root

def resolve_new_project_folder(base_dir, goal):
    """Used only by 'build' when starting a brand-new project (no resume, no existing
    memory/.git in the target folder). Decides whether it's safe to write directly into
    base_dir, or whether Kitsune should autonomously create a fresh subfolder for the
    project instead -- which it ALWAYS does if base_dir is Kitsune's own script folder,
    no confirmation needed, no exceptions."""
    base = os.path.abspath(base_dir)
    os.makedirs(base, exist_ok=True)

    script_dir = os.path.dirname(SELF_PATH)
    has_existing_project_markers = (
        os.path.exists(os.path.join(base, MEMORY_FILENAME))
        or os.path.exists(os.path.join(base, PROJECT_MARKER_FILENAME))
        or os.path.isdir(os.path.join(base, ".git"))
    )

    try:
        meaningful_entries = [e for e in os.listdir(base) if e not in CONTROL_ENTRIES and not e.startswith(".")]
    except PermissionError:
        meaningful_entries = []

    must_use_subfolder = (base == script_dir) or (meaningful_entries and not has_existing_project_markers)

    if not must_use_subfolder:
        return base

    slug = slugify(goal)
    candidate = os.path.join(base, slug)
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(base, f"{slug}-{n}")
        n += 1
    os.makedirs(candidate, exist_ok=True)
    print(f"\nCreating a new project folder for this: {candidate}\n")
    return candidate

