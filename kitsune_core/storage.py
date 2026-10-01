"""Kitsune storage subsystem. Extracted without changing the original function bodies."""

from .foundation import *

CORE_REQUIRED_DIRS = (
    "reserved_core", "knowledge", "environment", "workspace", "archives",
    "checkpoints", "projects", "project_metadata", "logs",
)

def kitsune_home():
    return os.environ.get("KITSUNE_HOME") or os.path.join(os.path.expanduser("~"), ".kitsune")

def core_dir(*parts):
    return os.path.join(kitsune_home(), *parts)

def knowledge_dir():
    return core_dir("memory", "knowledge")

def environment_dir():
    return core_dir("memory", "environment")

def workspace_dir():
    return core_dir("memory", "workspace")

def archive_dir():
    return core_dir("memory", "archives")

def checkpoints_dir():
    """Universal Recovery Layer (Snapshot Recovery): per-project checkpoint storage.
    Lives under the same core home directory as the rest of memory, NOT inside any
    project folder -- consistent with the existing rule that Kitsune memory must
    survive a project being moved, copied, or deleted."""
    return core_dir("memory", "checkpoints")

def projects_dir():
    return core_dir("projects")

def project_metadata_dir():
    """Reserved per the spec's folder structure (projects/metadata/). registry.json
    remains the single source of truth for project rows -- this directory is NOT
    populated with a duplicate copy of every registry entry (that would be exactly
    the "duplicate recovery/storage system" the architecture rules warn against).
    It exists so a future per-project detail file (e.g. a large debug dump) has a
    designated home without needing another top-level directory added later."""
    return core_dir("projects", "metadata")

def reserved_core_dir():
    """Reserved, currently-unused top-level directory matching the required
    structure's bare 'core/' entry. Not written to by anything yet -- kept as a
    placeholder for future internal runtime state, same spirit as
    project_metadata_dir()."""
    return core_dir("core")

def logs_dir():
    return core_dir("logs")

def ensure_core_dirs():
    for d in (reserved_core_dir(), knowledge_dir(), environment_dir(), workspace_dir(), archive_dir(),
              checkpoints_dir(), projects_dir(), project_metadata_dir(), logs_dir()):
        os.makedirs(d, exist_ok=True)

def validate_core_structure():
    """Startup structure validation + repair (requirement: 'create directories
    automatically if missing, validate structure, repair missing directories when
    possible'). Repairs the common case (a directory is simply missing) by creating
    it. The one case it can't safely auto-repair -- a regular FILE sitting where a
    directory needs to be -- is reported, not silently deleted, since that could be
    the user's own data; the person running Kitsune decides what to do with it.
    Returns a list of human-readable repair/issue strings for the caller to log/show."""
    dir_fns = {
        "core": reserved_core_dir, "memory/knowledge": knowledge_dir, "memory/environment": environment_dir,
        "memory/workspace": workspace_dir, "memory/archives": archive_dir, "memory/checkpoints": checkpoints_dir,
        "projects": projects_dir, "projects/metadata": project_metadata_dir, "logs": logs_dir,
    }
    events = []
    for label, fn in dir_fns.items():
        path = fn()
        if os.path.isdir(path):
            continue
        if os.path.exists(path):
            events.append(f"CANNOT auto-repair: {path} exists but is a file, not a directory "
                           f"(required for '{label}') -- move or remove it manually")
            continue
        try:
            os.makedirs(path, exist_ok=True)
            events.append(f"Repaired: created missing directory {path} (required for '{label}')")
        except OSError as e:
            events.append(f"CANNOT auto-repair: failed to create {path} for '{label}': {e}")
    for event in events:
        MEMORY_LOG.info(f"Startup structure check: {event}")
    return events

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

def parse_iso(ts):
    if not ts or not isinstance(ts, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(ts)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed

def days_since(ts):
    parsed = parse_iso(ts)
    if parsed is None:
        return None
    return max(0, (datetime.datetime.now(datetime.timezone.utc) - parsed).days)

def atomic_write_json(path, data):
    """Memory Locking / partial-write protection: writes to a temp file in the same
    directory, then atomically renames it into place. os.replace() is atomic on both
    POSIX and Windows, so a reader can never observe a half-written file, and a crash
    mid-write leaves the OLD file intact rather than a corrupted one. This is the one
    write primitive every memory/registry/checkpoint save in this file goes through."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
        return True
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return False

