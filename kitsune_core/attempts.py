"""Kitsune attempts subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .foundation import *
from .storage import *

def memory_path(root):
    return os.path.join(root, MEMORY_FILENAME)

def load_memory(root):
    path = memory_path(root)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

def save_memory(root, goal, messages):
    path = memory_path(root)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"goal": goal, "messages": messages}, f, indent=2)
    except OSError as e:
        print(f"Warning: could not save memory ({e})")

def attempts_core_path(project_id):
    """Coding Attempt Memory now lives in core storage, not the project folder --
    same sibling-file pattern as architecture_path()/decisions_path()."""
    return os.path.join(knowledge_dir(), f"{project_id}.attempts.json")

def legacy_attempts_path(root):
    """The OLD project-local location (.agent_attempts.json). Only read from here for
    one-time migration of pre-existing projects; never written to anymore."""
    return os.path.join(root, ATTEMPTS_FILENAME)

def load_attempts(project_id, root=None):
    """Reads from core storage. If nothing exists there yet but a legacy project-local
    file does (an older project not yet migrated), reads that instead -- migrate_legacy_project()
    is what actually copies it over; this is just a safe fallback so attempt history
    isn't invisible in the gap before that runs."""
    path = attempts_core_path(project_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "tasks" in data:
                return data
        except (json.JSONDecodeError, OSError) as e:
            MEMORY_LOG.ignored(f"attempt memory ({project_id})", f"corrupted JSON ({e})")
    if root:
        legacy_path = legacy_attempts_path(root)
        if os.path.exists(legacy_path):
            try:
                with open(legacy_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "tasks" in data:
                    return data
            except (json.JSONDecodeError, OSError):
                pass
    return {"tasks": {}}

def save_attempts(project_id, data):
    if not atomic_write_json(attempts_core_path(project_id), data):
        MEMORY_LOG.error(f"could not save attempt memory for {project_id}")

def task_key(goal):
    """Stable identifier for a task, so attempt history for a 'fix this bug' run is
    kept separate from an unrelated 'build' run in the same project folder, and
    resuming the same goal later still finds its own history."""
    return hashlib.sha256((goal or "").strip().encode("utf-8")).hexdigest()[:16]

def fix_fingerprint(files_changed):
    """files_changed: list of (relative_path, before_text_or_None, after_text) tuples
    describing the actual change. Two proposed fixes that touch the same file(s) with
    the exact same resulting content hash identically here, regardless of how
    differently the model phrased its 'note' -- that's what makes this a real
    duplicate check rather than a string-match on the model's commentary."""
    h = hashlib.sha256()
    for path, before, after in sorted(files_changed, key=lambda x: x[0]):
        h.update(path.encode("utf-8"))
        h.update(b"\x00")
        h.update((before or "").encode("utf-8"))
        h.update(b"\x00")
        h.update((after or "").encode("utf-8"))
        h.update(b"\x01")
    return h.hexdigest()[:24]

class AttemptMemory:
    def __init__(self, root, goal, project_id):
        self.root = root
        self.project_id = project_id
        self.key = task_key(goal)
        self._data = load_attempts(project_id, root=root)
        self._data["tasks"].setdefault(self.key, {"goal": goal, "attempts": [], "next_id": 1})
        self.task = self._data["tasks"][self.key]
        self._pending_ids = []  # attempts applied since the last verification result

    def _save(self):
        save_attempts(self.project_id, self._data)

    def check(self, files_changed):
        """Returns (fingerprint, prior_failed_attempt_or_None)."""
        fp = fix_fingerprint(files_changed)
        prior = next((a for a in self.task["attempts"] if a["fingerprint"] == fp and a["result"] == "failed"), None)
        return fp, prior

    def record_attempt(self, action, fingerprint, files, note):
        attempt_id = self.task["next_id"]
        self.task["next_id"] += 1
        self.task["attempts"].append({
            "id": attempt_id,
            "action": action,
            "files": files,
            "fingerprint": fingerprint,
            "summary": (note or "").strip()[:300] or f"{action} on {', '.join(files)}",
            "result": "pending",
            "error": None,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._pending_ids.append(attempt_id)
        self._save()
        return attempt_id

    def resolve_pending(self, success, error=None, on_success=None, on_failure=None):
        """Called after a verification step (a run_command result, or the auto-verify
        test run) so every fix applied since the last check gets its real outcome
        recorded -- this is what turns a 'pending' attempt into a 'failed' one that
        future duplicate fixes will be rejected against. on_success(attempt_dict) /
        on_failure(attempt_dict), if given, fire once per attempt that just got that
        outcome (used to mirror both into Root Cause / Knowledge Memory -- a fix that
        didn't work is still useful memory of what the cause was NOT)."""
        if not self._pending_ids:
            return
        for a in self.task["attempts"]:
            if a["id"] in self._pending_ids:
                a["result"] = "success" if success else "failed"
                if error:
                    a["error"] = error.strip()[:500]
                if success and on_success:
                    on_success(a)
                elif not success and on_failure:
                    on_failure(a)
        self._pending_ids = []
        self._save()

    def failed_summary(self, limit=8):
        failed = [a for a in self.task["attempts"] if a["result"] == "failed"]
        if not failed:
            return None
        lines = []
        for a in failed[-limit:]:
            files = ", ".join(a["files"])
            err = f" -- resulted in: {a['error']}" if a.get("error") else ""
            lines.append(f"  Attempt #{a['id']} ({a['action']} on {files}): {a['summary']}{err}")
        return "\n".join(lines)

