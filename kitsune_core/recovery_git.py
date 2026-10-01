"""Kitsune recovery_git subsystem. Extracted without changing the original function bodies."""

from .foundation import *

def _git_ok(root, args, timeout=30):
    try:
        return subprocess.run(["git"] + args, cwd=root, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None

def rollback_available(root):
    return shutil.which("git") is not None

def ensure_git_repo(root):
    if not rollback_available(root):
        return False
    if not os.path.isdir(os.path.join(root, ".git")):
        if _git_ok(root, ["init"]) is None:
            return False
        _git_ok(root, ["config", "user.email", "kitsune@local"])
        _git_ok(root, ["config", "user.name", "Kitsune"])
    return True

def create_recovery_point(root, label):
    """Commits the current state as a rollback point. Returns the commit hash, or
    None if git isn't available -- callers must treat None as 'no safety net', not
    as an error, and fall back to asking before applying changes (see confirm())."""
    if not ensure_git_repo(root):
        return None
    _git_ok(root, ["add", "-A"])
    result = _git_ok(root, ["commit", "-m", f"kitsune: recovery point -- {label}"[:200], "--allow-empty"])
    if result is None or result.returncode != 0:
        return None
    rev = _git_ok(root, ["rev-parse", "HEAD"])
    return rev.stdout.strip() if rev and rev.returncode == 0 else None

def rollback_to(root, commit_hash, reason):
    """Restores the project to a known-good recovery point. Never leaves the project
    in a worse state than before -- if the reset itself fails, this is logged loudly
    rather than silently continuing on top of a broken/regressed state."""
    if not commit_hash:
        MEMORY_LOG.error(f"Rollback requested for {root} but no recovery point exists -- cannot safely roll back")
        return False
    result = _git_ok(root, ["reset", "--hard", commit_hash])
    ok = result is not None and result.returncode == 0
    if ok:
        MEMORY_LOG.info(f"Rolled back {os.path.basename(root)} to {commit_hash[:8]} -- {reason}")
    else:
        MEMORY_LOG.error(f"Rollback to {commit_hash[:8]} FAILED for {root} -- {reason}. Manual `git status` check recommended.")
    return ok

