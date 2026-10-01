"""Kitsune memory_types subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .memory_core import *
from .storage import *

def knowledge_path(project_id):
    return os.path.join(knowledge_dir(), f"{project_id}.json")

def load_knowledge_memory(project_id):
    wrapped, ok = load_core_memory(knowledge_path(project_id), "knowledge", f"knowledge memory ({project_id})")
    return wrapped["payload"] if ok else {"entries": []}

def record_knowledge_entry(project_id, summary, files, kind="fix", result="success",
                            problem=None, cause=None, confidence=None):
    """Root Cause Memory (Feature 6): stores not just what fix was tried, but the
    Problem/Cause/Fix/Result shape, and for BOTH successes and failures -- a fix that
    didn't work is still useful memory of what the cause was NOT. `confidence`, if
    given, is the Confidence System (Feature 2) score computed for this outcome."""
    payload = load_knowledge_memory(project_id)
    payload.setdefault("entries", []).append({
        "kind": kind,  # "fix" | "pattern" | "preference"
        "result": result,  # "success" | "failed"
        "problem": (problem or "").strip()[:300] or None,
        "cause": (cause or "").strip()[:300] or None,
        "summary": (summary or "").strip()[:300],
        "files": files,
        "confidence": confidence,
        "recorded_at": now_iso(),
    })
    payload["entries"] = payload["entries"][-200:]  # cap unbounded growth
    save_core_memory(knowledge_path(project_id), "knowledge", payload, project_id=project_id,
                      created_at=_existing_created_at(knowledge_path(project_id)))

def similar_fix_history(project_id, files):
    """Used by the Confidence System: how many past fixes touching any of these same
    files succeeded vs. failed, so a fix in a historically shaky area scores lower."""
    entries = load_knowledge_memory(project_id).get("entries", [])
    files = set(files)
    successes = sum(1 for e in entries if e.get("kind") == "fix" and e.get("result") == "success"
                     and files & set(e.get("files", [])))
    failures = sum(1 for e in entries if e.get("kind") == "fix" and e.get("result") == "failed"
                    and files & set(e.get("files", [])))
    return successes, failures

def architecture_path(project_id):
    return os.path.join(knowledge_dir(), f"{project_id}.architecture.json")

def load_architecture_memory(project_id):
    wrapped, ok = load_core_memory(architecture_path(project_id), "architecture", f"architecture memory ({project_id})")
    return wrapped["payload"] if ok else {"systems": []}

def record_architecture_system(project_id, name, description, files):
    payload = load_architecture_memory(project_id)
    systems = payload.setdefault("systems", [])
    existing = next((s for s in systems if s.get("name") == name), None)
    if existing:
        existing["description"] = (description or existing.get("description", ""))[:400]
        existing["files"] = sorted(set(existing.get("files", [])) | set(files))
        existing["updated_at"] = now_iso()
    else:
        systems.append({
            "name": name, "description": (description or "")[:400],
            "files": files, "updated_at": now_iso(),
        })
    save_core_memory(architecture_path(project_id), "architecture", payload, project_id=project_id,
                      created_at=_existing_created_at(architecture_path(project_id)))

def decisions_path(project_id):
    return os.path.join(knowledge_dir(), f"{project_id}.decisions.json")

def load_decision_memory(project_id):
    wrapped, ok = load_core_memory(decisions_path(project_id), "decisions", f"decision memory ({project_id})")
    return wrapped["payload"] if ok else {"entries": []}

def record_decision(project_id, decision, reason):
    payload = load_decision_memory(project_id)
    payload.setdefault("entries", []).append({
        "decision": (decision or "").strip()[:300],
        "reason": (reason or "").strip()[:300],
        "recorded_at": now_iso(),
    })
    save_core_memory(decisions_path(project_id), "decisions", payload, project_id=project_id,
                      created_at=_existing_created_at(decisions_path(project_id)))

def environment_path():
    return os.path.join(environment_dir(), "environment.json")

def load_environment_memory():
    wrapped, ok = load_core_memory(environment_path(), "environment", "environment memory")
    payload = wrapped["payload"] if ok else {}
    payload.setdefault("installed_models_last_seen", [])
    payload.setdefault("preferred_models", {})
    payload.setdefault("model_last_used", {})
    payload.setdefault("tool_paths", {})
    return payload

def save_environment_memory(payload):
    save_core_memory(environment_path(), "environment", payload, created_at=_existing_created_at(environment_path()))

def record_environment_snapshot(available_models):
    env = load_environment_memory()
    env["installed_models_last_seen"] = list(available_models)
    save_environment_memory(env)
    return env

def record_model_used(model, role=None):
    env = load_environment_memory()
    env["model_last_used"][model] = now_iso()
    if role:
        env["preferred_models"][role] = model
    save_environment_memory(env)

def workspace_path(project_id):
    return os.path.join(workspace_dir(), f"{project_id}.json")

def load_workspace_memory(project_id):
    wrapped, ok = load_core_memory(workspace_path(project_id), "workspace", f"workspace memory ({project_id})")
    return (wrapped, wrapped["payload"]) if ok else (None, None)

def save_workspace_memory(project_id, goal, status, messages):
    payload = {"goal": goal, "status": status, "messages": messages}
    save_core_memory(workspace_path(project_id), "workspace", payload, project_id=project_id,
                      created_at=_existing_created_at(workspace_path(project_id)))

def archive_workspace_memory(project_id):
    """Moves (not deletes) a project's workspace memory into core/memory/archives/.
    Only called by explicit maintenance (`kitsune.py gc`), never automatically."""
    src = workspace_path(project_id)
    if not os.path.exists(src):
        return False
    dest = os.path.join(archive_dir(), f"{project_id}-{int(time.time())}.json")
    try:
        shutil.move(src, dest)
        MEMORY_LOG.info(f"Archived workspace memory for project {project_id} -> {dest}")
        return True
    except OSError as e:
        MEMORY_LOG.error(f"could not archive workspace memory for {project_id} ({e})")
        return False

