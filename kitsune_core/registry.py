"""Kitsune registry subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .foundation import *
from .storage import *

PROJECT_STATUSES = ("active", "paused", "archived", "deleted", "unknown")

def registry_path():
    return os.path.join(projects_dir(), "registry.json")

def load_registry():
    path = registry_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        MEMORY_LOG.error(f"project registry corrupted ({e}) -- starting a fresh one; "
                          f"existing per-project memory files are untouched and will be re-linked as projects are opened")
        return {}

def save_registry(registry):
    ensure_core_dirs()
    if not atomic_write_json(registry_path(), registry):
        MEMORY_LOG.error("could not save project registry")

def get_or_create_project_id(root):
    """Identifies a project across moves and copies without storing memory inside the
    project folder. Returns (project_id, prior_status_or_None) -- prior_status is the
    status the project had BEFORE this call touched it (e.g. 'archived'), so callers
    can tell the user "this project was archived" instead of it silently flipping to
    active with no trace.

    A move (folder renamed/relocated as a whole) keeps its id and its full memory,
    because the marker travels with the folder and its old registry path no longer
    exists. A copy (folder duplicated while the original still exists) gets a FRESH
    id instead of silently sharing history with the original, because the old
    registry path is still there on disk."""
    root = os.path.abspath(root)
    marker_path = os.path.join(root, PROJECT_MARKER_FILENAME)
    registry = load_registry()

    existing_id = None
    if os.path.exists(marker_path):
        try:
            with open(marker_path, "r", encoding="utf-8") as f:
                existing_id = json.load(f).get("project_id")
        except (json.JSONDecodeError, OSError):
            existing_id = None

    if existing_id and existing_id in registry:
        entry = registry[existing_id]
        recorded_path = entry.get("project_path")
        prior_status = entry.get("status")
        if recorded_path == root:
            entry["last_accessed"] = now_iso()
            entry["status"] = "active"
            save_registry(registry)
            return existing_id, prior_status
        if recorded_path and os.path.isdir(recorded_path):
            MEMORY_LOG.info(f"Folder {root} carries the ID of a project still present at {recorded_path} -- "
                             f"treating this as a separate copy with its own new project ID rather than merging history.")
            existing_id = None
        else:
            entry["project_path"] = root
            entry["last_accessed"] = now_iso()
            entry["status"] = "active"
            save_registry(registry)
            MEMORY_LOG.info(f"Project moved from {recorded_path} to {root} -- memory preserved under the same ID.")
            return existing_id, prior_status

    new_id = uuid.uuid4().hex[:12]
    try:
        with open(marker_path, "w", encoding="utf-8") as f:
            json.dump({"project_id": new_id}, f)
    except OSError:
        pass
    registry[new_id] = {
        "project_id": new_id,
        "project_name": os.path.basename(root) or new_id,
        "project_path": root,
        "created_at": now_iso(),
        "last_accessed": now_iso(),
        "status": "active",
    }
    save_registry(registry)
    return new_id, None

def scan_registry_for_missing():
    """Detects projects whose folder no longer exists and marks them 'deleted'
    WITHOUT touching any memory -- knowledge and workspace files stay exactly where
    they are. Returns the list of (project_id, name) newly marked this run."""
    registry = load_registry()
    newly_removed = []
    for pid, entry in registry.items():
        path = entry.get("project_path")
        if entry.get("status") != "deleted" and (not path or not os.path.isdir(path)):
            entry["status"] = "deleted"
            newly_removed.append((pid, entry.get("project_name", pid)))
            MEMORY_LOG.info(f"Project '{entry.get('project_name', pid)}' folder no longer found at {path} "
                             f"-- marked deleted; its knowledge and workspace memory are preserved.")
    if newly_removed:
        save_registry(registry)
    return newly_removed

