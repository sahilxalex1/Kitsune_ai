"""Kitsune git subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .repo import *

def git_is_repo(root):
    return os.path.isdir(os.path.join(root, ".git"))

def git_ensure_repo(root, timeout):
    if not git_is_repo(root):
        if input("This folder isn't a git repo yet. Initialize one? [y/N] ").strip().lower() == "y":
            print(run_shell_command("git init", cwd=root, timeout=timeout))

def git_status(root, timeout):
    return run_shell_command("git status --short", cwd=root, timeout=timeout)

def git_commit(root, message, timeout):
    run_shell_command("git add -A", cwd=root, timeout=timeout)
    return run_shell_command(f'git commit -m "{message}"', cwd=root, timeout=timeout)

def git_add_remote(root, url, name, timeout):
    existing = run_shell_command(f"git remote get-url {name}", cwd=root, timeout=timeout)
    if "exit code: 0" in existing:
        return run_shell_command(f"git remote set-url {name} {url}", cwd=root, timeout=timeout)
    return run_shell_command(f"git remote add {name} {url}", cwd=root, timeout=timeout)

def git_push(root, remote, branch, timeout):
    if not branch:
        branch_result = run_shell_command("git rev-parse --abbrev-ref HEAD", cwd=root, timeout=timeout)
        branch = branch_result.split("\n")[-1].strip() or "main"
    return run_shell_command(f"git push -u {remote} {branch}", cwd=root, timeout=timeout)

def git_undo_last_commit(root, timeout):
    if not git_is_repo(root):
        print("Not a git repo -- nothing to undo.")
        return
    print("Last commit:")
    print(run_shell_command("git log -1 --oneline", cwd=root, timeout=timeout))
    print("\nThis will run 'git revert --no-edit HEAD' (keeps history intact).")
    if input("Proceed? [y/N] ").strip().lower() == "y":
        print(run_shell_command("git revert --no-edit HEAD", cwd=root, timeout=timeout))
    else:
        print("Cancelled.")

