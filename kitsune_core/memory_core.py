"""Kitsune memory_core subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .foundation import *
from .storage import *

REQUIRED_PAYLOAD_KEYS = {
    "knowledge": {"entries"},
    "environment": set(),  # free-form settings dict; no single key is mandatory
    "workspace": {"goal", "status"},
    "architecture": {"systems"},
    "decisions": {"entries"},
}

MEMORY_STATES = ("active", "archived", "stale", "invalid", "deprecated", "removed")

STALE_AFTER_DAYS = 365

class MemoryLog:
    """Collects the reasoning behind every accept/ignore decision for this run (used
    to build the startup Memory Recovery Report) and mirrors each one to
    core/logs/kitsune.log so the history survives past a single run."""

    def __init__(self):
        self.entries = []  # list of (level, message)

    def _write(self, level, message):
        self.entries.append((level, message))
        try:
            ensure_core_dirs()
            with open(os.path.join(logs_dir(), "kitsune.log"), "a", encoding="utf-8") as f:
                f.write(f"[{now_iso()}] {level.upper()}: {message}\n")
        except OSError:
            pass  # logging must never break the actual task

    def accepted(self, what, reason):
        self._write("accept", f"{what} -- {reason}")

    def ignored(self, what, reason):
        self._write("ignore", f"{what} -- {reason}")

    def info(self, message):
        self._write("info", message)

    def error(self, message):
        self._write("error", message)

    def migration(self, message):
        """Migration System requirement: every migration event goes to BOTH the
        unified kitsune.log (via the normal info-level write, so it still shows up
        in the startup report's accept/ignore counts and general history) AND a
        dedicated logs/migrations.log for anyone auditing migrations specifically."""
        self._write("info", f"[migration] {message}")
        try:
            ensure_core_dirs()
            with open(os.path.join(logs_dir(), "migrations.log"), "a", encoding="utf-8") as f:
                f.write(f"[{now_iso()}] {message}\n")
        except OSError:
            pass

    def counts(self):
        accepted = sum(1 for lvl, _ in self.entries if lvl == "accept")
        ignored = sum(1 for lvl, _ in self.entries if lvl == "ignore")
        return accepted, ignored

def validate_memory_blob(data, expected_type):
    """Runs every check the spec asks for -- existence is checked by the caller
    (missing file), this covers integrity, version compatibility, schema, and
    timestamps. Returns (ok: bool, reason: str). Never raises: a malformed file is
    just a rejection, not a crash."""
    if not isinstance(data, dict):
        return False, "file content is not a JSON object"

    version = data.get("memory_version")
    if version is None:
        return False, "missing memory_version (unversioned/legacy file -- needs migration, not direct use)"
    if not isinstance(version, int):
        return False, "memory_version is not an integer"
    if version > MEMORY_SCHEMA_VERSION:
        return False, (f"memory_version {version} is newer than this build of Kitsune understands "
                        f"(supports up to {MEMORY_SCHEMA_VERSION}) -- refusing to guess at its structure")

    if data.get("memory_type") != expected_type:
        return False, f"memory_type mismatch (expected '{expected_type}', found '{data.get('memory_type')!r}')"

    payload = data.get("payload")
    if not isinstance(payload, dict):
        return False, "missing or malformed payload"
    missing = REQUIRED_PAYLOAD_KEYS.get(expected_type, set()) - set(payload.keys())
    if missing:
        return False, f"payload missing required key(s): {', '.join(sorted(missing))}"

    if parse_iso(data.get("created_at")) is None:
        return False, "created_at is missing or not a valid timestamp"
    if parse_iso(data.get("last_used")) is None:
        return False, "last_used is missing or not a valid timestamp"

    return True, "valid"

def classify_memory_state(wrapped):
    """Derives a memory entry's state. An explicitly-set non-active state (e.g. a
    workspace marked 'archived' by save_workspace_memory) is always respected; this
    only fills in 'stale' for otherwise-active entries that haven't been touched in
    a long time. Purely descriptive -- setting/reading a state never triggers any
    action by itself (Core Principle: memory may recommend, never act)."""
    explicit = wrapped.get("state")
    if explicit and explicit != "active":
        return explicit
    age = days_since(wrapped.get("last_used"))
    if age is not None and age >= STALE_AFTER_DAYS:
        return "stale"
    return explicit or "active"

def compute_memory_confidence(wrapped, validation_ok):
    """Memory Confidence Scoring (0.00-1.00) -- rates how much a STORED MEMORY ITEM
    should be trusted as planning context (integrity + schema validity + recency +
    consistency of its state). This is deliberately a separate score from the
    Confidence System used elsewhere for code-fix quality (that one is 0-100% and
    answers 'did this fix work'; this one is 0.00-1.00 and answers 'should the
    planner trust this piece of memory'). Per the Core Principle, this score is
    informational only and must never be used to trigger a system-changing action --
    every caller of this function only uses it to decide what to SHOW or RECOMMEND."""
    if not validation_ok:
        return 0.0, "ignore"
    score = 0.7  # passed validation: integrity + schema validity both hold
    age = days_since(wrapped.get("last_used"))
    if age is not None:
        if age <= 7:
            score += 0.2
        elif age <= 30:
            score += 0.1
        elif age >= STALE_AFTER_DAYS:
            score -= 0.3
    state = classify_memory_state(wrapped)
    if state in ("stale", "deprecated"):
        score -= 0.2
    elif state in ("invalid", "removed"):
        score = 0.0
    score = max(0.0, min(1.0, score))
    tier = "ignore" if score <= 0.40 else ("needs_validation" if score <= 0.70 else "safe")
    return round(score, 2), tier

def load_core_memory(path, expected_type, label):
    """The single gate every stored memory file passes through. Returns
    (wrapped_dict_or_None, accepted: bool). On any problem -- missing file,
    unreadable, corrupted JSON, failed schema/version/timestamp validation -- this
    logs why and returns (None, False) so the caller safely falls back to a default,
    never crashing and never acting on bad data."""
    if not os.path.exists(path):
        return None, False
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        MEMORY_LOG.ignored(label, f"could not read file ({e})")
        return None, False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        MEMORY_LOG.ignored(label, f"corrupted JSON ({e})")
        return None, False

    ok, reason = validate_memory_blob(data, expected_type)
    if not ok:
        MEMORY_LOG.ignored(label, f"failed validation -- {reason}")
        return None, False

    age = days_since(data.get("last_used"))
    age_desc = f"last used {age} day(s) ago" if age is not None else "last-used time unknown"
    MEMORY_LOG.accepted(label, f"valid (schema v{data['memory_version']}, {age_desc})")
    return data, True

def save_core_memory(path, memory_type, payload, project_id=None, created_at=None, state="active"):
    """Writes a properly versioned, schema-tagged memory file. Preserves the original
    created_at across updates when the caller supplies it (callers read it from the
    existing file first, so a memory's true age is never reset just by touching it).
    `state` is one of active/archived/stale/invalid/deprecated/removed (Memory States)."""
    ensure_core_dirs()
    blob = {
        "memory_version": MEMORY_SCHEMA_VERSION,
        "memory_type": memory_type,
        "project_id": project_id,
        "created_at": created_at or now_iso(),
        "last_used": now_iso(),
        "state": state,
        "payload": payload,
    }
    if not atomic_write_json(path, blob):
        MEMORY_LOG.error(f"could not save {memory_type} memory to {path}")

def _existing_created_at(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("created_at")
    except (json.JSONDecodeError, OSError):
        return None

