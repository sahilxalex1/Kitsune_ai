"""Kitsune migration subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .attempts import *
from .foundation import *
from .memory_types import *

def migrate_legacy_project(root, project_id):
    """One-way, non-destructive import of the OLD per-project files
    (.agent_memory.json, .agent_attempts.json, .agent_config.json) into the new core
    memory stores. Runs only the first time a project is seen that has legacy files
    but no core workspace memory yet -- safe to call every run, and never deletes or
    modifies the legacy files, so nothing is lost if this logic ever needs to be
    re-run or debugged. This IS the spec's Backup step: the legacy files are left in
    place untouched, so they serve as the backup with no redundant copy needed."""
    _, existing_workspace = load_workspace_memory(project_id)
    if existing_workspace is not None:
        return  # already on core memory (migrated before, or created core-native)

    legacy_mem = load_memory(root)
    if isinstance(legacy_mem, dict) and "goal" in legacy_mem:
        save_workspace_memory(project_id, legacy_mem.get("goal", ""), "active", legacy_mem.get("messages", []))
        MEMORY_LOG.migration(f"Migrated legacy {MEMORY_FILENAME} for '{os.path.basename(root)}' "
                              f"(project {project_id}) into workspace memory "
                              f"(unversioned -> schema v{MEMORY_SCHEMA_VERSION}). Original file left in place.")

    legacy_attempts_file = legacy_attempts_path(root)
    legacy_attempts = {"tasks": {}}
    if os.path.exists(legacy_attempts_file):
        try:
            with open(legacy_attempts_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "tasks" in data:
                legacy_attempts = data
        except (json.JSONDecodeError, OSError):
            pass
    successes = 0
    for task in legacy_attempts.get("tasks", {}).values():
        for a in task.get("attempts", []):
            if a.get("result") == "success":
                record_knowledge_entry(project_id, a.get("summary", ""), a.get("files", []), kind="fix")
                successes += 1
    if successes:
        MEMORY_LOG.migration(f"Migrated {successes} successful fix(es) from legacy attempt memory for "
                              f"'{os.path.basename(root)}' (project {project_id}) into knowledge memory. "
                              f"Original file left in place.")

    legacy_config_path = os.path.join(root, CONFIG_FILENAME)
    if os.path.exists(legacy_config_path):
        try:
            with open(legacy_config_path, "r", encoding="utf-8") as f:
                legacy_config = json.load(f)
            model = legacy_config.get("model")
            if model:
                record_model_used(model, role="build_model")
                MEMORY_LOG.migration(f"Migrated preferred model '{model}' from legacy {CONFIG_FILENAME} for "
                                      f"'{os.path.basename(root)}' (project {project_id}) into environment memory.")
        except (json.JSONDecodeError, OSError):
            pass

