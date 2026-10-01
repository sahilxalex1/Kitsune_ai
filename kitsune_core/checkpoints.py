"""Kitsune checkpoints subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .foundation import *
from .recovery_git import *
from .storage import *

def checkpoint_project_dir(project_id):
    return os.path.join(checkpoints_dir(), project_id)

def _checkpoint_size_bytes(cp_dir):
    total = 0
    for dirpath, _dirs, filenames in os.walk(cp_dir):
        for fn in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, fn))
            except OSError:
                pass
    return total

def snapshot_recovery_available(project_id):
    """The fallback is available as long as the checkpoints directory can be created/
    written to -- true on any normal filesystem, regardless of git."""
    try:
        ensure_core_dirs()
        os.makedirs(checkpoint_project_dir(project_id), exist_ok=True)
        return True
    except OSError:
        return False

def create_checkpoint(root, project_id, files, reason, attempt_id=None):
    """Saves the original content of just `files` (relative paths, about to be
    modified) into a new numbered checkpoint. A file that doesn't exist yet (a
    brand-new file about to be created) has nothing to snapshot and is simply
    skipped -- restoring later means deleting it, not overwriting it, which
    restore_checkpoint() handles. Returns the checkpoint id, or None if nothing could
    be saved (e.g. disk full) -- callers must treat None as 'no snapshot safety net
    for this change', not as a hard failure."""
    proj_dir = checkpoint_project_dir(project_id)
    try:
        os.makedirs(proj_dir, exist_ok=True)
    except OSError as e:
        MEMORY_LOG.error(f"Could not create checkpoint storage for {project_id}: {e}")
        return None

    existing = sorted(d for d in os.listdir(proj_dir) if d.startswith("checkpoint_"))
    next_num = (int(existing[-1].split("_")[1]) + 1) if existing else 1
    cp_id = f"checkpoint_{next_num:03d}"
    cp_dir = os.path.join(proj_dir, cp_id)
    originals_dir = os.path.join(cp_dir, "original_files")

    saved, created_new = [], []
    try:
        os.makedirs(originals_dir, exist_ok=True)
        for rel in files:
            src = os.path.join(root, rel)
            if os.path.exists(src):
                dest = os.path.join(originals_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)
                saved.append(rel)
            else:
                created_new.append(rel)  # nothing to snapshot -- restore will just delete this file
        metadata = {
            "checkpoint_id": cp_id,
            "created_at": now_iso(),
            "project_id": project_id,
            "affected_files": list(files),
            "snapshotted_files": saved,
            "new_files": created_new,
            "reason": reason,
            "attempt_id": attempt_id,
            "recovery_source": "snapshot",
        }
        if not atomic_write_json(os.path.join(cp_dir, "metadata.json"), metadata):
            raise OSError("metadata write failed")
    except OSError as e:
        MEMORY_LOG.error(f"Could not create checkpoint {cp_id} for {project_id}: {e}")
        shutil.rmtree(cp_dir, ignore_errors=True)
        return None

    MEMORY_LOG.info(f"Checkpoint {cp_id} created for {os.path.basename(root)}: protected "
                     f"{len(saved)} existing file(s), {len(created_new)} new file(s) -- {reason}")
    prune_checkpoints(project_id)
    return cp_id

def list_checkpoints(project_id):
    """Newest first. Skips (and logs) any checkpoint whose metadata.json is corrupted
    rather than crashing -- consistent with the rest of this file's memory-safety rule."""
    proj_dir = checkpoint_project_dir(project_id)
    if not os.path.isdir(proj_dir):
        return []
    out = []
    for cp_id in sorted(os.listdir(proj_dir), reverse=True):
        meta_path = os.path.join(proj_dir, cp_id, "metadata.json")
        if not os.path.exists(meta_path):
            continue
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                out.append(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            MEMORY_LOG.error(f"Checkpoint {cp_id} for {project_id} has unreadable metadata, skipping: {e}")
    return out

def restore_checkpoint(root, checkpoint):
    """Restores exactly the files this checkpoint protected: existing files are
    copied back verbatim, files that didn't exist when the checkpoint was taken are
    deleted (undoing their creation). Verifies every restored file afterward and
    reports per-file success -- a partial restore is reported as such, never
    silently declared a full success."""
    project_id = checkpoint["project_id"]
    cp_dir = os.path.join(checkpoint_project_dir(project_id), checkpoint["checkpoint_id"])
    originals_dir = os.path.join(cp_dir, "original_files")
    restored, failed = [], []

    for rel in checkpoint.get("snapshotted_files", []):
        src = os.path.join(originals_dir, rel)
        dest = os.path.join(root, rel)
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            if os.path.exists(dest) and open(dest, "rb").read() == open(src, "rb").read():
                restored.append(rel)
            else:
                failed.append(rel)
        except OSError as e:
            MEMORY_LOG.error(f"Snapshot restore of {rel} failed: {e}")
            failed.append(rel)

    for rel in checkpoint.get("new_files", []):
        dest = os.path.join(root, rel)
        try:
            if os.path.exists(dest):
                os.remove(dest)
            restored.append(rel)
        except OSError as e:
            MEMORY_LOG.error(f"Could not remove {rel} (created after checkpoint) during restore: {e}")
            failed.append(rel)

    ok = not failed
    if ok:
        MEMORY_LOG.info(f"Snapshot restore succeeded: {checkpoint['checkpoint_id']} for {project_id} "
                         f"({len(restored)} file(s) restored)")
    else:
        MEMORY_LOG.error(f"Snapshot restore INCOMPLETE: {checkpoint['checkpoint_id']} for {project_id} -- "
                          f"restored {restored}, FAILED {failed}")
    return ok, restored, failed

def prune_checkpoints(project_id, max_count=None, max_mb=None):
    """Storage Limits: enforced on every checkpoint creation (not just at session
    start), so checkpoint storage can never grow unbounded regardless of how many
    sessions run. Oldest checkpoints are removed first, by count and then by total
    size, until both limits are satisfied."""
    max_count = max_count if max_count is not None else DEFAULT_CONFIG["max_checkpoints"]
    max_mb = max_mb if max_mb is not None else DEFAULT_CONFIG["max_checkpoint_storage_mb"]
    proj_dir = checkpoint_project_dir(project_id)
    if not os.path.isdir(proj_dir):
        return 0
    checkpoints = sorted(d for d in os.listdir(proj_dir) if d.startswith("checkpoint_"))
    removed = 0

    while len(checkpoints) > max_count:
        oldest = checkpoints.pop(0)
        shutil.rmtree(os.path.join(proj_dir, oldest), ignore_errors=True)
        removed += 1

    total_mb = _checkpoint_size_bytes(proj_dir) / (1024 * 1024)
    while total_mb > max_mb and checkpoints:
        oldest = checkpoints.pop(0)
        shutil.rmtree(os.path.join(proj_dir, oldest), ignore_errors=True)
        removed += 1
        total_mb = _checkpoint_size_bytes(proj_dir) / (1024 * 1024)

    if removed:
        MEMORY_LOG.info(f"Pruned {removed} old checkpoint(s) for {project_id} (limits: "
                         f"{max_count} checkpoints / {max_mb}MB)")
    return removed

def recover(root, project_id, reason, session_recovery_commit=None, attempt_id=None):
    """The single Automatic Recovery Selection entry point (Requirement 3): tries Git
    rollback first (if a recovery commit is available and the reset succeeds), then
    falls back to the most recent snapshot checkpoint, then reports unavailable.
    Returns a result dict: {"ok": bool, "method": "git"|"snapshot"|"none", "detail": str}.
    This is the ONLY place recovery-method selection happens -- callers (maybe_rollback
    in run_agent) don't need to know which method was used."""
    if session_recovery_commit and rollback_to(root, session_recovery_commit, reason):
        return {"ok": True, "method": "git", "detail": f"restored via git to {session_recovery_commit[:8]}"}

    checkpoints = list_checkpoints(project_id)
    if checkpoints:
        latest = checkpoints[0]
        ok, restored, failed = restore_checkpoint(root, latest)
        detail = f"restored via snapshot {latest['checkpoint_id']} ({len(restored)} file(s))"
        if failed:
            detail += f", {len(failed)} file(s) FAILED to restore: {failed}"
        return {"ok": ok, "method": "snapshot", "detail": detail}

    MEMORY_LOG.error(f"Recovery unavailable for {os.path.basename(root)}: no git recovery point and "
                      f"no snapshot checkpoints exist -- {reason}")
    return {"ok": False, "method": "none", "detail": "no git recovery point and no snapshot checkpoints available"}

