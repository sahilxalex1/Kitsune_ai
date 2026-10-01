"""Kitsune agent_io subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .foundation import *

ALWAYS_FREE_ACTIONS = {"web_search", "read_file", "list_dir", "search_files"}

APPLY_ACTIONS = {"write_file", "write_project", "edit_file", "edit_files"}

def _guess_script_path(command):
    """Best-effort extraction of a script filename from a shell command, so a
    corrective suggestion can reference the actual file instead of a placeholder."""
    for tok in reversed(command.split()):
        tok_clean = tok.strip("'\"")
        if os.path.splitext(tok_clean)[1] in (".py", ".js", ".mjs", ".ts", ".rb"):
            return tok_clean
    return None

def interactive_input_failure_hint(command, output):
    """If a command's failure looks like 'nobody was there to answer input()' rather
    than a real bug, return a concrete, ready-to-run corrective suggestion. Returns
    None if this doesn't look like that specific pattern."""
    if "EOFError" not in output or ("input(" not in output and "reading a line" not in output):
        return None

    script = _guess_script_path(command)
    syntax_check = (
        f'python -c "import ast; ast.parse(open(\'{script}\').read())"' if script
        else 'python -m py_compile <the script>'
    )
    if IS_WINDOWS:
        piped_example = f'"add`n2`n3`nquit" | {command}'
    else:
        piped_example = f'printf "add\\n2\\n3\\nquit\\n" | {command}'

    return (
        f"\n\nThis is NOT a bug in the code. `EOFError: EOF when reading a line` means the program called "
        f"input() and there was nobody available to type a response -- commands run here have no interactive "
        f"stdin. Running `{command}` again as-is will fail the exact same way every time.\n"
        f"Do ONE of the following instead:\n"
        f"  1) Check it parses cleanly (no interaction needed): {syntax_check}\n"
        f"  2) Or drive it with piped input matching its actual prompts/menu, e.g.: {piped_example}\n"
        f"    (adjust the piped values to match this program's real menu options)\n"
        f"Choose option 1 or 2 now -- do not run the bare command again."
    )

def confirm(action_name, config, prompt="Apply?"):
    if action_name in ALWAYS_FREE_ACTIONS:
        return True
    if action_name in config.get("auto_approve", []):
        print(f"  (auto-approved: {action_name})")
        return True
    if (action_name in APPLY_ACTIONS and config.get("autonomous_apply", True)
            and config.get("_rollback_ready")):
        print(f"  (auto-applied: {action_name} -- a git recovery point exists, so this can be undone "
              f"automatically if it causes a regression; see 'kitsune.py undo' or the automatic rollback log)")
        return True
    return input(f"  {prompt} [y/N] ").strip().lower() == "y"

def missing_required(d, *fields):
    """Return the names of any required fields absent from dict d. Used to turn a
    malformed action from the model into a normal, recoverable error message fed
    back to it -- instead of a raw KeyError that would crash the whole session."""
    return [f for f in fields if f not in d]

def field_error_message(act, missing):
    return (
        f'Error: your "{act}" action was missing required field(s): {", ".join(missing)}. '
        f'Re-check the action schema for "{act}" and resend a complete action.'
    )

