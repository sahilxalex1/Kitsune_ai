"""Kitsune startup subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .memory_core import *
from .memory_types import *
from .registry import *
from .storage import *

def generate_recovery_report(available_models):
    ensure_core_dirs()
    record_environment_snapshot(available_models)
    newly_removed = scan_registry_for_missing()
    registry = load_registry()
    env = load_environment_memory()

    lines = ["Memory Recovery Report", "-" * 23]

    lines.append("Knowledge Memory:")
    total_fixes = 0
    for pid in registry:
        wrapped, ok = load_core_memory(knowledge_path(pid), "knowledge", f"knowledge memory ({pid})")
        if ok:
            total_fixes += len(wrapped["payload"].get("entries", []))
    lines.append(f"  \u2713 Loaded {total_fixes} bug fix/pattern record(s) across {len(registry)} known project(s)")

    lines.append("\nEnvironment Memory:")
    if not env["preferred_models"]:
        lines.append("  (no preferred models recorded yet)")
    env_wrapped, env_ok = load_core_memory(environment_path(), "environment", "environment memory")
    for role, model in env["preferred_models"].items():
        base_name = model.split(":")[0]
        installed = any(m == model or m.startswith(base_name + ":") for m in available_models)
        age = days_since(env["model_last_used"].get(model))
        entry_wrapped = dict(env_wrapped) if env_ok else {}
        entry_wrapped["last_used"] = env["model_last_used"].get(model)
        state = classify_memory_state(entry_wrapped)
        lines.append(f"  Found preferred model: {model} (role: {role})")
        lines.append(f"    Last used: {age if age is not None else 'unknown'} day(s) ago")
        lines.append(f"    Status: {state}")
        if not installed:
            lines.append(f"    Action: none (not installed; {'stale -- ' if state == 'stale' else ''}"
                          f"will not auto-download; use ensure_model_available to decide interactively)")
        else:
            lines.append(f"    Action: Ready to use")

    lines.append("\nWorkspace Memory:")
    restored = 0
    if not registry:
        lines.append("  (no projects known yet)")
    for pid, entry in registry.items():
        wrapped, ok = load_core_memory(workspace_path(pid), "workspace", f"workspace memory ({pid})")
        if not ok:
            continue
        restored += 1
        age = days_since(wrapped.get("last_used"))
        mem_state = classify_memory_state(wrapped)
        lines.append(f"  Project: {entry.get('project_name', pid)}")
        lines.append(f"    Status: {entry.get('status', 'unknown')} (memory state: {mem_state})"
                      + (f", last used {age} day(s) ago" if age is not None else ""))

    accepted_count, ignored_count = MEMORY_LOG.counts()
    lines.append("\nSummary:")
    lines.append(f"  {restored} workspace memor{'y' if restored == 1 else 'ies'} restored")
    lines.append(f"  {accepted_count} memory record(s) accepted, {ignored_count} ignored")
    if newly_removed:
        lines.append(f"  {len(newly_removed)} project(s) newly detected missing (memory preserved)")
    lines.append("  0 automatic downloads performed")
    lines.append("  0 automatic installs performed")

    report = "\n".join(lines)
    print("\n" + report + "\n")
    return report

def _dedup_knowledge_entries(entries):
    seen = set()
    deduped = []
    for e in entries:
        fp = (e.get("kind"), e.get("summary"), tuple(sorted(e.get("files", []))))
        if fp in seen:
            continue
        seen.add(fp)
        deduped.append(e)
    return deduped

def run_memory_maintenance(archive_after_days=90):
    """Explicit, user-triggered maintenance only -- never runs automatically.
    - Detects missing project folders and marks them 'removed' (memory preserved).
    - Archives (moves, never deletes) workspace memory for removed/archived projects
      that haven't been touched in `archive_after_days` days.
    - Memory Health System: scans every core memory file for corruption (quarantining
      any that fail to parse, rather than leaving them permanently stuck failing),
      dedupes knowledge entries, and removes registry entries that point nowhere.
    - Knowledge memory and environment memory are NEVER deleted here -- fixes,
      patterns, decisions, and model/config history are kept indefinitely by design;
      health repair only removes exact duplicate entries and quarantines files that
      are already unreadable (so nothing readable is ever lost)."""
    ensure_core_dirs()
    removed = scan_registry_for_missing()
    registry = load_registry()
    archived = 0
    quarantined = []
    deduped_count = 0

    for pid, entry in registry.items():
        if entry.get("status") in ("deleted", "archived"):
            wrapped, ok = load_core_memory(workspace_path(pid), "workspace", f"workspace memory ({pid})")
            if ok:
                age = days_since(wrapped.get("last_used"))
                if age is not None and age >= archive_after_days and entry.get("status") != "archived":
                    if archive_workspace_memory(pid):
                        entry["status"] = "archived"
                        archived += 1

        # Corruption scan + repair for this project's files across all memory types.
        for path, mtype in (
            (knowledge_path(pid), "knowledge"), (workspace_path(pid), "workspace"),
            (architecture_path(pid), "architecture"), (decisions_path(pid), "decisions"),
        ):
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = f.read()
                data = json.loads(raw)
                ok, reason = validate_memory_blob(data, mtype)
            except (json.JSONDecodeError, OSError):
                ok, reason = False, "unreadable/corrupted JSON"
            if not ok:
                quarantine_path = path + ".corrupt"
                try:
                    shutil.move(path, quarantine_path)
                    quarantined.append((mtype, pid, reason))
                    MEMORY_LOG.info(f"Quarantined corrupted {mtype} memory for {pid} -> {quarantine_path} ({reason})")
                except OSError as e:
                    MEMORY_LOG.error(f"could not quarantine corrupted {mtype} memory for {pid}: {e}")

        know_wrapped, know_ok = load_core_memory(knowledge_path(pid), "knowledge", f"knowledge memory ({pid})")
        if know_ok:
            before = know_wrapped["payload"].get("entries", [])
            after = _dedup_knowledge_entries(before)
            if len(after) != len(before):
                deduped_count += len(before) - len(after)
                save_core_memory(knowledge_path(pid), "knowledge", {"entries": after}, project_id=pid,
                                  created_at=know_wrapped.get("created_at"))

    if archived or removed:
        save_registry(registry)
    return {"removed": removed, "archived": archived, "quarantined": quarantined, "deduped_entries": deduped_count}

