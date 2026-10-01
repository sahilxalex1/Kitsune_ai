"""Kitsune commands subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .agent import *
from .attempts import *
from .brainstorm import *
from .chat import *
from .config import *
from .foundation import *
from .git import *
from .memory_types import *
from .migration import *
from .models import *
from .projects import *
from .registry import *
from .repo import *
from .review import *
from .startup import *
from .storage import *

def cmd_build(args, available_models):
    root = _resolve_root(args.dir)
    if root is None:
        return

    usage_tracker = UsageTracker()

    goal = args.goal
    project_id, prior_status = get_or_create_project_id(root)
    migrate_legacy_project(root, project_id)  # picks up a pre-existing legacy .agent_memory.json, if any
    workspace_wrapped, workspace_payload = load_workspace_memory(project_id)
    if workspace_payload and not args.no_resume:
        age = days_since(workspace_wrapped["last_used"])
        status_note = f", status: {prior_status}" if prior_status and prior_status != "active" else ""
        age_note = f", last used {age} day(s) ago" if age is not None else ""
        print(f"\nFound previous session for this project{status_note}{age_note}. Last goal was:\n"
              f"  \"{workspace_payload['goal']}\"")
        if input("Resume that session with a follow-up instruction? [y/N] ").strip().lower() == "y":
            if not goal:
                goal = input("Follow-up instruction: ").strip()
            config = load_config(root)
            requested_model = args.model or model_for(config, "build_model")
            config["model"] = ensure_model_available(
                requested_model, available_models, role="build_model",
                project_status=prior_status or "active",
                source="direct" if args.model else "memory",
            )
            run_agent(root, goal, config, usage_tracker, messages=workspace_payload["messages"])
            return

    if not goal:
        goal = input("What should the agent do? ").strip()

    # Fresh start -- figure out whether to build directly here or spin up a new subfolder.
    root = resolve_new_project_folder(root, goal)
    created_fresh_config = ensure_config_file(root)
    config = load_config(root)
    requested_model = args.model or model_for(config, "build_model")
    config["model"] = ensure_model_available(
        requested_model, available_models, role="build_model",
        source="direct" if (args.model or created_fresh_config) else "memory",
    )

    run_agent(root, goal, config, usage_tracker)

def cmd_fix(args, available_models):
    root = _resolve_root(args.dir)
    if root is None:
        return

    created_fresh_config = ensure_config_file(root)
    config = load_config(root)
    requested_model = args.model or model_for(config, "fix_model")
    config["model"] = ensure_model_available(
        requested_model, available_models, role="fix_model",
        source="direct" if (args.model or created_fresh_config) else "memory",
    )
    usage_tracker = UsageTracker()

    # If nothing useful was passed on the command line, ask interactively instead
    # of just firing a vague "find and fix bugs" goal at the whole project.
    file_arg = args.file
    error_arg = args.error
    run_arg = args.run
    if not any([file_arg, error_arg, run_arg]):
        print("\nWhat should it focus on? (leave any of these blank to skip)")
        file_arg = input("Specific file to check (blank = whole project): ").strip() or None
        error_arg = input("Paste the error/traceback, if you have one: ").strip() or None
        run_arg = input("Command that reproduces the bug (e.g. 'python app.py'): ").strip() or None

    parts = ["Find and fix the bug(s) described below."]
    if file_arg:
        parts.append(f"Focus specifically on this file: {file_arg} (but check related files if the root cause lives elsewhere).")
    if error_arg:
        parts.append(f"Here is the exact error/traceback encountered:\n{error_arg}")
    if run_arg:
        parts.append(f"You can reproduce the issue by running: {run_arg}")
    if not (file_arg or error_arg or run_arg):
        parts.append("No specific file or error was given -- explore the project, look for likely bugs "
                      "(runtime errors, obvious logic mistakes, broken imports, etc.), and fix what you find.")
    parts.append(
        "Read the relevant file(s) first to understand the code before changing anything. Identify the "
        "root cause, not just the symptom. Make the smallest fix that actually resolves it -- don't "
        "refactor unrelated code. Verify the fix by re-running the reproduction command (or the project's "
        "tests, if any) before declaring done. If you can't reproduce or find a bug, say so clearly in "
        "the summary instead of inventing a change."
    )
    goal = "\n\n".join(parts)

    print(f"\nGoal for the agent:\n{goal}\n")
    run_agent(root, goal, config, usage_tracker)

def cmd_review(args, available_models):
    root = _resolve_root(args.dir)
    if root is None:
        return

    pre_existing_config = os.path.exists(os.path.join(root, CONFIG_FILENAME))
    config = load_config(root)
    requested_model = args.model or model_for(config, "review_model")
    config["model"] = ensure_model_available(
        requested_model, available_models, role="review_model",
        source="direct" if (args.model or not pre_existing_config) else "memory",
    )
    usage_tracker = UsageTracker()

    file_arg = args.file
    focus_arg = args.focus
    if not any([file_arg, focus_arg]):
        print("\nWhat should it focus on? (leave blank to skip)")
        file_arg = input("Specific file to review (blank = whole project): ").strip() or None
        focus_arg = input("Anything specific to focus on (e.g. 'security', 'performance'): ").strip() or None

    parts = []
    if file_arg:
        parts.append(f"Review this file: {file_arg} (read related files too if useful for context).")
    else:
        parts.append("Review the project as a whole -- explore it first, then focus on the files that matter most.")
    if focus_arg:
        parts.append(f"Pay particular attention to: {focus_arg}.")
    target_description = " ".join(parts)

    print(f"\nReview task:\n{target_description}\n")
    run_review(root, target_description, config, usage_tracker)

def cmd_idea(args, available_models):
    config = dict(DEFAULT_CONFIG)
    requested_model = args.model or model_for(config, "idea_model")
    config["model"] = ensure_model_available(requested_model, available_models, role="idea_model", source="direct")
    usage_tracker = UsageTracker()
    run_brainstorm(config, usage_tracker)

def cmd_chat(args, available_models):
    config = dict(DEFAULT_CONFIG)
    chat_model = args.model or model_for(config, "chat_model")
    router_model = args.model or model_for(config, "router_model")
    chat_model = ensure_model_available(chat_model, available_models, role="chat_model", source="direct")
    if router_model != chat_model:
        router_model = ensure_model_available(router_model, available_models, role="router_model", source="direct")
    usage_tracker = UsageTracker()
    run_chat(config, usage_tracker, chat_model, router_model, available_models)

def cmd_undo(args, available_models):
    root = _resolve_root(args.dir)
    if root is None:
        return
    config = load_config(root)
    git_undo_last_commit(root, config["command_timeout"])

def cmd_memory(args, available_models):
    root = _resolve_root(args.dir)
    if root is None:
        return

    project_id, prior_status = get_or_create_project_id(root)
    migrate_legacy_project(root, project_id)  # picks up a pre-existing legacy .agent_memory.json, if any
    wrapped, payload = load_workspace_memory(project_id)
    if not payload:
        print(f"\nNo saved session found for this project.")
        return

    goal = payload.get("goal", "")
    messages = payload.get("messages", [])

    print(f"\nProject folder: {root}  (id: {project_id}, status: {prior_status or 'active'})")
    print(f"Last goal: {goal}")
    print(f"Messages in session: {len(messages)}")
    print(f"Last updated: {wrapped['last_used']}")

    # Look backwards for the most recent 'done' action to show its summary.
    last_done_summary = None
    for m in reversed(messages):
        if m.get("role") != "assistant":
            continue
        try:
            parsed = json.loads(m["content"])
        except (json.JSONDecodeError, TypeError):
            continue
        if parsed.get("action") == "done":
            last_done_summary = parsed.get("summary")
            break

    if last_done_summary:
        print(f"\nLast recorded summary:\n{last_done_summary}")
    else:
        print("\n(No 'done' summary found -- this session may have ended mid-task, or was interrupted.)")

    print(f"\nTo continue this project: kitsune.py build --dir \"{root}\" --goal \"<follow-up instruction>\"")

def cmd_attempts(args, available_models):
    root = _resolve_root(args.dir)
    if root is None:
        return

    project_id, _prior_status = get_or_create_project_id(root)
    data = load_attempts(project_id, root=root)
    tasks = data.get("tasks", {})
    if not tasks:
        print(f"\nNo attempt memory found for this project yet -- it's created the first time build/fix applies a fix.")
        return

    print(f"\nProject folder: {root}  (id: {project_id})")
    for key, task in tasks.items():
        attempts = task.get("attempts", [])
        if not attempts:
            continue
        goal_preview = (task.get("goal") or "").strip().splitlines()[0][:100]
        print(f"\nTask [{key}]: {goal_preview}")
        for a in attempts:
            files = ", ".join(a.get("files", []))
            marker = {"success": "✔", "failed": "✘", "pending": "…"}.get(a.get("result"), "?")
            print(f"  {marker} #{a['id']} [{a['result']}] {a['action']} on {files} -- {a['summary']}")
            if a.get("error"):
                print(f"      error: {a['error'][:200]}")

    failed_total = sum(1 for t in tasks.values() for a in t.get("attempts", []) if a.get("result") == "failed")
    if failed_total:
        print(f"\n{failed_total} fix(es) on record as confirmed NOT to work -- future identical proposals for "
              f"the same task will be rejected automatically.")

def cmd_gc(args, available_models):
    print("Running Kitsune memory maintenance...")
    print(f"(Core storage: {kitsune_home()})\n")
    archive_after = args.archive_after_days if getattr(args, "archive_after_days", None) else 90

    result = run_memory_maintenance(archive_after_days=archive_after)
    removed, archived = result["removed"], result["archived"]

    if removed:
        print(f"{len(removed)} project(s) newly detected missing (folder no longer exists):")
        for pid, name in removed:
            print(f"  - {name} [{pid}] -- marked removed, memory preserved")
    else:
        print("No newly-missing projects detected.")

    print(f"\n{archived} workspace memory file(s) archived "
          f"(removed/archived projects untouched for {archive_after}+ days).")

    if result["quarantined"]:
        print(f"\n{len(result['quarantined'])} corrupted memory file(s) quarantined (renamed .corrupt, not deleted):")
        for mtype, pid, reason in result["quarantined"]:
            print(f"  - {mtype} memory for {pid}: {reason}")
    else:
        print("\nNo corrupted memory files found.")

    if result["deduped_entries"]:
        print(f"{result['deduped_entries']} duplicate knowledge entr(y/ies) removed.")

    print("\nKnowledge memory (fixes/patterns/decisions/architecture) and environment memory (models/config) "
          "are NEVER deleted by maintenance -- only stale workspace memory for removed/archived projects moves "
          "to core/memory/archives/ (a move, not a delete), and only exact-duplicate knowledge entries are "
          "collapsed.")

def cmd_index(args, available_models):
    root = _resolve_root(args.dir)
    if root is None:
        return

    print(f"\nIndexing {root} ...")
    index = build_repo_index(root)
    save_repo_index(root, index)

    total_files = len(index)
    total_symbols = sum(len(v) for v in index.values())
    by_type = {}
    for symbols in index.values():
        for s in symbols:
            by_type[s["type"]] = by_type.get(s["type"], 0) + 1

    print(f"Indexed {total_files} file(s), {total_symbols} symbol(s).")
    for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")
    print(f"\nSaved to {os.path.join(root, INDEX_FILENAME)}")

    if args.find:
        matches = find_symbol_in_index(index, args.find)
        print(f"\nLookup results for '{args.find}':")
        print("\n".join(matches) if matches else "  (no matches)")

