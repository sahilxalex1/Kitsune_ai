"""Kitsune sanity subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .memory_core import *
from .memory_types import *

SANITY_CONFIG_FILES = {
    "package.json": "json", "tsconfig.json": "json", "composer.json": "json",
    "pyproject.toml": None,  # parsed generically below (no TOML lib dependency assumed)
}

def run_sanity_checks(root, project_id):
    issues = []

    for fname, kind in SANITY_CONFIG_FILES.items():
        fpath = os.path.join(root, fname)
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            if kind == "json":
                json.loads(content)
            elif not content.strip():
                issues.append(f"{fname} exists but is empty")
        except (OSError, json.JSONDecodeError) as e:
            issues.append(f"{fname} failed to parse: {e}")

    if os.path.exists(os.path.join(root, "package.json")) and not os.path.isdir(os.path.join(root, "node_modules")):
        issues.append("package.json exists but node_modules/ is missing -- dependencies may not be installed")
    if os.path.exists(os.path.join(root, "requirements.txt")) and not os.path.isdir(os.path.join(root, "venv")) \
            and not os.path.isdir(os.path.join(root, ".venv")) and not os.environ.get("VIRTUAL_ENV"):
        issues.append("requirements.txt exists but no venv/.venv found and no active virtualenv detected")

    for path, mtype in (
        (workspace_path(project_id), "workspace"), (knowledge_path(project_id), "knowledge"),
        (architecture_path(project_id), "architecture"), (decisions_path(project_id), "decisions"),
    ):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ok, reason = validate_memory_blob(data, mtype)
            if not ok:
                issues.append(f"{mtype} memory integrity check failed: {reason}")
        except (OSError, json.JSONDecodeError) as e:
            issues.append(f"{mtype} memory file unreadable: {e}")

    return issues

