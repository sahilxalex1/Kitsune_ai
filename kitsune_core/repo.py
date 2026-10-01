"""Kitsune repo subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .foundation import *

INDEX_FILENAME = ".kitsune_index.json"

LANGUAGE_SYMBOL_PATTERNS = {
    ".py":  [(r"^\s*def\s+(\w+)", "function"), (r"^\s*class\s+(\w+)", "class")],
    ".js":  [(r"function\s+(\w+)", "function"), (r"class\s+(\w+)", "class"),
             (r"const\s+(\w+)\s*=\s*\(?.*?\)?\s*=>", "function")],
    ".jsx": [(r"function\s+(\w+)", "function"), (r"class\s+(\w+)", "class"),
             (r"const\s+(\w+)\s*=\s*\(?.*?\)?\s*=>", "function")],
    ".ts":  [(r"function\s+(\w+)", "function"), (r"class\s+(\w+)", "class"),
             (r"interface\s+(\w+)", "interface"), (r"const\s+(\w+)\s*=\s*\(?.*?\)?\s*=>", "function")],
    ".tsx": [(r"function\s+(\w+)", "function"), (r"class\s+(\w+)", "class"),
             (r"interface\s+(\w+)", "interface"), (r"const\s+(\w+)\s*=\s*\(?.*?\)?\s*=>", "function")],
    ".java": [(r"(?:class|interface)\s+(\w+)", "class"),
              (r"(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\],\s]+?\s+(\w+)\s*\(", "method")],
    ".cs":  [(r"(?:class|interface)\s+(\w+)", "class"),
             (r"(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\],\s]+?\s+(\w+)\s*\(", "method")],
    ".go":  [(r"^func\s+(?:\([^)]*\)\s*)?(\w+)", "function"), (r"^type\s+(\w+)\s+struct", "struct")],
    ".rs":  [(r"fn\s+(\w+)", "function"), (r"struct\s+(\w+)", "struct"), (r"enum\s+(\w+)", "enum")],
    ".rb":  [(r"def\s+(\w+)", "method"), (r"class\s+(\w+)", "class")],
    ".php": [(r"function\s+(\w+)", "function"), (r"class\s+(\w+)", "class")],
}

SYNTAX_CHECKABLE_EXTENSIONS = {".py", ".json", ".js", ".mjs", ".cjs"}

def build_tree(root, max_depth=3, max_entries=200):
    lines = []
    count = [0]

    def walk(path, depth, prefix):
        if depth > max_depth or count[0] >= max_entries:
            return
        try:
            entries = sorted(os.listdir(path))
        except PermissionError:
            return
        entries = [e for e in entries if e not in IGNORE_DIRS and not e.startswith(".")]
        for i, entry in enumerate(entries):
            if count[0] >= max_entries:
                lines.append(f"{prefix}... (truncated)")
                return
            full = os.path.join(path, entry)
            connector = "└── " if i == len(entries) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry}")
            count[0] += 1
            if os.path.isdir(full):
                extension = "    " if i == len(entries) - 1 else "│   "
                walk(full, depth + 1, prefix + extension)

    lines.append(os.path.basename(os.path.abspath(root)) + "/")
    walk(root, 1, "")
    return "\n".join(lines)

def search_in_files(root, pattern, max_matches=50):
    matches = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for fname in filenames:
            if len(matches) >= max_matches:
                return matches
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, start=1):
                        if pattern in line:
                            rel = os.path.relpath(fpath, root)
                            matches.append(f"{rel}:{lineno}: {line.strip()}")
                            if len(matches) >= max_matches:
                                break
            except (UnicodeDecodeError, PermissionError, OSError):
                continue
    return matches

def build_repo_index(root):
    index = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for fname in filenames:
            ext = os.path.splitext(fname)[1]
            patterns = LANGUAGE_SYMBOL_PATTERNS.get(ext)
            if not patterns:
                continue
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(fpath, root)
            symbols = []
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, start=1):
                        for regex, label in patterns:
                            m = re.search(regex, line)
                            if m:
                                symbols.append({"name": m.group(1), "type": label, "line": lineno})
            except OSError:
                continue
            if symbols:
                index[rel] = symbols
    return index

def save_repo_index(root, index):
    try:
        with open(os.path.join(root, INDEX_FILENAME), "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
    except OSError:
        pass

def load_repo_index(root):
    path = os.path.join(root, INDEX_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

def find_symbol_in_index(index, name):
    name_lower = name.lower()
    exact, partial = [], []
    for rel, symbols in index.items():
        for s in symbols:
            line = f"{rel}:{s['line']} ({s['type']}) {s['name']}"
            if s["name"].lower() == name_lower:
                exact.append(line)
            elif name_lower in s["name"].lower():
                partial.append(line)
    return exact + partial

def read_file_safe(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        return "Error: file is binary or not UTF-8 text, cannot display."

def write_one_file(root, rel_path, content):
    full_path = os.path.join(root, rel_path)
    if os.path.abspath(full_path) == SELF_PATH:
        raise PermissionError("Refusing to write to the agent's own script file.")
    os.makedirs(os.path.dirname(full_path) or root, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

def make_dirs(root, rel_path):
    os.makedirs(os.path.join(root, rel_path), exist_ok=True)

def check_syntax(rel_path, content):
    """Best-effort syntax check for a would-be file's content. Returns None if the
    syntax is OK (or the file type isn't one we know how to check), or a short
    human-readable error string describing the problem if it's genuinely broken."""
    ext = os.path.splitext(rel_path)[1].lower()

    if ext == ".py":
        try:
            ast.parse(content, filename=rel_path)
        except SyntaxError as e:
            pointer = ""
            if e.text:
                pointer = "\n    " + e.text.rstrip("\n") + ("\n    " + " " * (e.offset - 1) + "^" if e.offset else "")
            return f"Python syntax error in {rel_path}, line {e.lineno}: {e.msg}{pointer}"
        except (ValueError, RecursionError) as e:
            return f"Could not parse {rel_path} as Python: {e}"
        return None

    if ext == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            return f"JSON syntax error in {rel_path}, line {e.lineno} col {e.colno}: {e.msg}"
        return None

    if ext in (".js", ".mjs", ".cjs") and shutil.which("node"):
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=ext, delete=False, encoding="utf-8") as tf:
                tf.write(content)
                tmp_path = tf.name
            result = subprocess.run(["node", "--check", tmp_path], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                err = (result.stderr or "").strip().replace(tmp_path, rel_path)
                return f"JavaScript syntax error in {rel_path}:\n{err[:800]}"
        except Exception:
            pass  # best-effort only -- never block a write because the checker itself misbehaved
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        return None

    return None

def run_shell_command(command, cwd, timeout):
    shell_exe = ["powershell", "-Command", command] if IS_WINDOWS else ["bash", "-c", command]
    try:
        # stdin is explicitly closed (not inherited): nobody is present to answer an
        # interactive prompt, so a program calling input() should fail fast with
        # EOFError instead of hanging silently until the timeout fires.
        result = subprocess.run(
            shell_exe, capture_output=True, text=True, timeout=timeout, cwd=cwd, stdin=subprocess.DEVNULL
        )
        output = (result.stdout or "") + (result.stderr or "")
        return f"exit code: {result.returncode}\n{output.strip()[:6000]}"
    except subprocess.TimeoutExpired as e:
        partial = ((e.stdout or b"") if isinstance(e.stdout, (bytes, str)) else b"")
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="ignore")
        hint = (
            "Note: stdin was closed for this command, so if it's calling input() it should have failed "
            "immediately with EOFError rather than hanging -- a timeout more likely means the program is "
            "genuinely CPU-bound, stuck in an infinite loop, or waiting on a network/socket call. If this "
            "command is meant to run an interactive program, verify it differently: check syntax only, "
            "import it as a module without running its main loop, or pipe fixed input non-interactively "
            "(e.g. `echo \"1\\n5\\n3\\nq\" | python script.py`) instead of running it bare."
        )
        partial_note = f"\nPartial output before timeout:\n{partial.strip()[:2000]}" if partial.strip() else ""
        return f"Error: command timed out after {timeout} seconds.{partial_note}\n{hint}"
    except Exception as e:
        return f"Error running command: {e}"

def show_diff(old_text, new_text, path):
    old_lines = (old_text or "").splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"{path} (before)", tofile=f"{path} (after)")
    diff_text = "".join(diff)
    print(f"\n--- Diff: {path} ---")
    print(diff_text if diff_text else "(new file / no previous content)")
    print("---" + "-" * (len(path) + 8))

