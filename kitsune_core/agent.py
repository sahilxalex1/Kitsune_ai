"""Kitsune agent subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .agent_io import *
from .agent_protocol import *
from .attempts import *
from .checkpoints import *
from .export_tests import *
from .foundation import *
from .git import *
from .memory_types import *
from .migration import *
from .recovery_git import *
from .registry import *
from .regression import *
from .repo import *
from .review import *
from .risk import *
from .sanity import *
from .web import *

def run_agent(root, goal, config, usage_tracker, messages=None):
    model = config["model"]
    timeout = config["command_timeout"]
    resuming = messages is not None
    decline_counts = {}  # signature -> consecutive-decline count, resets on any accepted action
    MAX_REPEAT_DECLINES = 2  # after this many declines of the *same* action, stop the loop
    MAX_AUTO_VERIFY_ATTEMPTS = 3

    project_id, _prior_status = get_or_create_project_id(root)
    migrate_legacy_project(root, project_id)

    attempt_memory = AttemptMemory(root, goal, project_id)
    duplicate_fix_counts = {}  # fingerprint -> consecutive times the agent re-proposed an already-failed fix
    MAX_DUPLICATE_FIX_ATTEMPTS = 2  # stop the loop rather than let it cycle on a known-bad fix

    def persist_session(status="active"):
        """Writes ONLY to core workspace memory now -- no file is written into the
        project folder for this. (Previously this also wrote legacy .agent_memory.json
        into the project folder for backward compatibility; that dual-write has been
        removed so project folders stay clean, per the 'memory must never live inside
        a project folder' rule. Old .agent_memory.json files from before this change
        are still read once by migrate_legacy_project() and then left alone.)"""
        save_workspace_memory(project_id, goal, status, messages)

    # --- Reliability Engine setup: rollback safety net + regression tracking -------
    regression_guard = RegressionGuard()
    session = {
        "recovery_commit": create_recovery_point(root, f"session start: {goal[:80]}"),
        "regression_detected": False,
    }
    snapshot_ready = snapshot_recovery_available(project_id)
    if snapshot_ready:
        prune_checkpoints(project_id, max_count=config.get("max_checkpoints"),
                           max_mb=config.get("max_checkpoint_storage_mb"))
    # Universal Recovery Layer: rollback is "ready" (safe to auto-apply changes without
    # asking) if EITHER git succeeded OR the snapshot fallback is available -- git is
    # tried first when both exist (see recover()), snapshot only if git can't.
    config["_rollback_ready"] = (session["recovery_commit"] is not None) or snapshot_ready
    if session["recovery_commit"] is None:
        if snapshot_ready:
            print("Note: git isn't available (or couldn't be initialized) in this project folder -- "
                  "using the snapshot-based recovery fallback instead. Automatic rollback still works.")
        else:
            print("Note: neither git nor snapshot recovery could be initialized for this project -- "
                  "automatic rollback is disabled, so every file change will ask for confirmation as before.")

    def new_recovery_point(label):
        commit = create_recovery_point(root, label)
        if commit:
            session["recovery_commit"] = commit

    def protect_files(files, reason):
        """Snapshot Recovery: called right before a file-mutating action is applied,
        so there's always a way back to this exact moment even if git rollback fails
        or was never available for this project."""
        if not files:
            return
        create_checkpoint(root, project_id, files, reason,
                           attempt_id=attempt_memory.task.get("next_id", 0) - 1)

    def maybe_rollback(reason):
        """Automatic Rollback (Feature 3) + Automatic Recovery Selection (Universal
        Recovery Layer requirement 3): tries git first, falls back to the latest
        snapshot checkpoint if git is unavailable/fails, and reports to the
        autonomous fix loop either way. Never silently does nothing -- a failed
        recovery is reported as such, not swallowed."""
        result = recover(root, project_id, reason, session_recovery_commit=session["recovery_commit"])
        if result["ok"]:
            print(f"\n↩ Automatic rollback ({result['method']}): {reason}")
            messages.append({"role": "user", "content": (
                f"The project was automatically rolled back ({result['method']} recovery) because: {reason}\n"
                f"{result['detail']}\nYour previous change has been undone. Analyze what went wrong and try "
                f"a different approach."
            )})
        else:
            print(f"\n⚠ Automatic rollback FAILED: {reason} -- {result['detail']}")
            messages.append({"role": "user", "content": (
                f"A rollback was needed because: {reason}, but recovery was unavailable ({result['detail']}). "
                f"The project may be in a broken state -- be careful, verify current file contents before "
                f"making further changes."
            )})
        return result["ok"]

    def record_fix_success(attempt):
        successes, failures = similar_fix_history(project_id, attempt["files"])
        confidence, reasons = compute_confidence(True, session["regression_detected"], successes, failures)
        print(f"\nConfidence: {confidence}%")
        for r in reasons:
            print(f"  - {r}")
        record_knowledge_entry(project_id, attempt["summary"], attempt["files"], kind="fix", result="success",
                                problem=goal, cause=attempt.get("error"), confidence=confidence)
        new_recovery_point(f"verified fix: {attempt['summary'][:80]}")

    def record_fix_failure(attempt):
        record_knowledge_entry(project_id, attempt["summary"], attempt["files"], kind="fix", result="failed",
                                problem=goal, cause=attempt.get("error"), confidence=None)

    def register_duplicate(fp):
        duplicate_fix_counts[fp] = duplicate_fix_counts.get(fp, 0) + 1
        return duplicate_fix_counts[fp]

    def clear_duplicate(fp):
        duplicate_fix_counts.pop(fp, None)

    def reject_if_duplicate(action_name, files_changed):
        """Checks a proposed change against attempt memory. Returns one of:
          ("new", fingerprint)        -- genuinely new fix; caller proceeds normally,
                                          then calls attempt_memory.record_attempt() on apply.
          ("duplicate", fingerprint)  -- rejected; a corrective message was appended to
                                          `messages`, caller should just `continue`.
          ("stop", fingerprint)       -- rejected too many times in a row; caller must
                                          `return messages` immediately (memory already saved).
        """
        fp, prior = attempt_memory.check(files_changed)
        if prior is None:
            return "new", fp
        print(f"⚠ Duplicate fix rejected: identical to Attempt #{prior['id']}, already recorded as failed.")
        if register_duplicate(fp) >= MAX_DUPLICATE_FIX_ATTEMPTS:
            print(f"\nStopping: the agent proposed the same already-failed fix {MAX_DUPLICATE_FIX_ATTEMPTS} "
                  f"times in a row ({action_name}, matches Attempt #{prior['id']}).")
            persist_session()
            return "stop", fp
        err = prior.get("error") or "the follow-up verification still failed afterward"
        messages.append({"role": "user", "content": (
            f"Error: this exact fix was already attempted as Attempt #{prior['id']} ({prior['summary']}) "
            f"and did NOT resolve the issue -- {err}\n\n"
            f"Do NOT propose this same change again. The root cause is not what you think it is: read more "
            f"of the surrounding code, consider a different file, or reconsider the diagnosis entirely."
        )})
        return "duplicate", fp

    def register_success(sig):
        decline_counts.pop(sig, None)

    auto_verify_enabled = None  # None = not yet asked; True/False once decided for this session
    auto_verify_attempts_left = MAX_AUTO_VERIFY_ATTEMPTS
    verified_ok = False

    tree = build_tree(root)
    failed_summary = attempt_memory.failed_summary()
    attempt_memory_block = (
        f"Coding Attempt Memory for this task -- fixes already tried and confirmed NOT to resolve "
        f"the issue (do not propose any of these again):\n{failed_summary}\n\n"
    ) if failed_summary else ""

    # Memory-Aware Development (Feature 11): load architecture memory, decision memory,
    # and past-fix/confidence history -- scoped strictly to THIS project's ID, never any
    # other project's memory -- so the model understands the "why", not just the "how".
    architecture = load_architecture_memory(project_id).get("systems", [])
    architecture_block = ""
    if architecture:
        lines = [f"  - {s['name']}: {s.get('description', '')} (files: {', '.join(s.get('files', [])) or 'n/a'})"
                  for s in architecture]
        architecture_block = "Known Architecture (systems recorded for this project so far):\n" + "\n".join(lines) + "\n\n"

    decisions = load_decision_memory(project_id).get("entries", [])
    decisions_block = ""
    if decisions:
        lines = [f"  - Decision: {d['decision']} -- Reason: {d['reason']}" for d in decisions[-10:]]
        decisions_block = "Past Decisions recorded for this project (respect these unless the user says otherwise):\n" + "\n".join(lines) + "\n\n"

    past_knowledge = load_knowledge_memory(project_id).get("entries", [])
    recent_fixes = [e for e in past_knowledge if e.get("kind") == "fix"][-6:]
    knowledge_block = ""
    if recent_fixes:
        lines = [f"  - [{e['result']}] {e['summary']} (files: {', '.join(e.get('files', [])) or 'n/a'})"
                  + (f", confidence was {e['confidence']}%" if e.get("confidence") is not None else "")
                  for e in recent_fixes]
        knowledge_block = "Recent fix history for this project (from prior sessions):\n" + "\n".join(lines) + "\n\n"

    memory_context_block = architecture_block + decisions_block + knowledge_block + attempt_memory_block

    if not resuming:
        plan = generate_plan(goal, tree, model, config, usage_tracker)
        print("\n" + "=" * 50)
        print("Proposed plan:")
        print(plan)
        print("=" * 50)
        if input("\nProceed with this plan? [y/N] ").strip().lower() != "y":
            print("Cancelled.")
            return None

        intro = (
            f"{memory_context_block}"
            f"Project folder: {os.path.abspath(root)}\n\nCurrent file tree:\n{tree}\n\n"
            f"Goal: {goal}\n\nApproved plan:\n{plan}\n\nBegin executing. Respond with your first action."
        )
        messages = [{"role": "user", "content": intro}]
    else:
        follow_up = (
            f"{memory_context_block}"
            f"Resuming this project. Current file tree (may have changed):\n{tree}\n\n"
            f"New instruction: {goal}\n\nContinue. Respond with your next action."
        )
        messages.append({"role": "user", "content": follow_up})

    json_retry_count = 0
    MAX_JSON_RETRIES = 3
    fail_counts = {}  # signature -> consecutive-failure count (syntax errors, malformed
    MAX_CONSEC_FAILURES = 3  # actions, repeated failing commands) -- distinct from user declines

    def register_fail(sig):
        fail_counts[sig] = fail_counts.get(sig, 0) + 1
        return fail_counts[sig]

    def clear_fail(sig):
        fail_counts.pop(sig, None)

    for step in range(1, config["max_steps"] + 1):
        print(f"\n=== Step {step} ===")
        try:
            raw_text, action = get_next_action(messages, model, config, usage_tracker)
        except ActionParseError as e:
            json_retry_count += 1
            messages.append({"role": "assistant", "content": e.raw_text})
            print(f"Model response wasn't a usable action ({e.reason}) -- attempt {json_retry_count}/{MAX_JSON_RETRIES}.")
            if json_retry_count >= MAX_JSON_RETRIES:
                print("Giving up after repeated invalid responses. (Local models can be less reliable at")
                print("strict JSON output than cloud models -- try a smaller task or a stronger model.)")
                persist_session()
                return messages
            messages.append({
                "role": "user",
                "content": (
                    f"Error: {e.reason}. Respond with ONLY a single valid JSON object matching one of "
                    f"the action schemas exactly -- no markdown fences, no commentary before or after."
                ),
            })
            continue
        except Exception as e:
            print(f"Error: {e}")
            break

        json_retry_count = 0
        messages.append({"role": "assistant", "content": raw_text})
        act = action.get("action")

        if act == "list_dir":
            rel = action.get("path", ".")
            target = os.path.join(root, rel)
            if os.path.isdir(target):
                messages.append({"role": "user", "content": f"Contents of {rel}:\n{build_tree(target)}"})
            else:
                messages.append({"role": "user", "content": f"Error: {rel} is not a directory."})

        elif act == "search_files":
            missing = missing_required(action, "pattern")
            if missing:
                messages.append({"role": "user", "content": field_error_message(act, missing)})
                continue
            pattern = action["pattern"]
            matches = search_in_files(root, pattern)
            result = "\n".join(matches) if matches else "No matches found."
            messages.append({"role": "user", "content": f"Search results for '{pattern}':\n{result}"})

        elif act == "find_symbol":
            missing = missing_required(action, "name")
            if missing:
                messages.append({"role": "user", "content": field_error_message(act, missing)})
                continue
            name = action["name"]
            index = load_repo_index(root)
            if index is None:
                index = build_repo_index(root)
                save_repo_index(root, index)
            matches = find_symbol_in_index(index, name)
            result = "\n".join(matches) if matches else f"No symbol matching '{name}' found in the index."
            messages.append({"role": "user", "content": f"find_symbol results for '{name}':\n{result}"})

        elif act == "read_file":
            missing = missing_required(action, "path")
            if missing:
                messages.append({"role": "user", "content": field_error_message(act, missing)})
                continue
            rel = action["path"]
            content = read_file_safe(os.path.join(root, rel))
            result_text = content if content is not None else "FILE DOES NOT EXIST"
            messages.append({"role": "user", "content": f"Content of {rel}:\n{result_text}"})

        elif act == "web_search":
            missing = missing_required(action, "query")
            if missing:
                messages.append({"role": "user", "content": field_error_message(act, missing)})
                continue
            query = action["query"]
            print(f"Web search: {query}")
            if confirm("web_search", config, "Run this search?"):
                result = do_web_search(query)
                print(f"  Results:\n{result}\n")
                messages.append({"role": "user", "content": f"Web search results for '{query}':\n{result}"})
            else:
                messages.append({"role": "user", "content": "User declined the web search. Choose a different action."})

        elif act == "make_dirs":
            missing = missing_required(action, "paths")
            if missing:
                messages.append({"role": "user", "content": field_error_message(act, missing)})
                continue
            paths = action["paths"]
            print(f"Create folders: {', '.join(paths)} — {action.get('note', '')}")
            if confirm("make_dirs", config):
                for p in paths:
                    make_dirs(root, p)
                messages.append({"role": "user", "content": f"Created folders: {', '.join(paths)}"})
            else:
                messages.append({"role": "user", "content": "User declined folder creation. Choose a different action."})

        elif act == "record_decision":
            missing = missing_required(action, "decision")
            if missing:
                messages.append({"role": "user", "content": field_error_message(act, missing)})
                continue
            record_decision(project_id, action["decision"], action.get("reason", ""))
            print(f"Decision recorded: {action['decision']}")
            messages.append({"role": "user", "content": "Decision recorded to memory. Continue."})

        elif act == "record_architecture":
            missing = missing_required(action, "name")
            if missing:
                messages.append({"role": "user", "content": field_error_message(act, missing)})
                continue
            record_architecture_system(project_id, action["name"], action.get("description", ""),
                                        action.get("files", []))
            print(f"Architecture memory updated: {action['name']}")
            messages.append({"role": "user", "content": "Architecture memory updated. Continue."})

        elif act == "write_file":
            missing = missing_required(action, "path", "content")
            if missing:
                messages.append({"role": "user", "content": field_error_message(act, missing)})
                continue
            rel = action["path"]
            content = action["content"]
            full_path = os.path.join(root, rel)
            if os.path.abspath(full_path) == SELF_PATH:
                print(f"Blocked: refusing to let the agent write to its own script file ({rel}).")
                messages.append({"role": "user", "content": f"Error: {rel} is the agent's own script file and cannot be modified. Choose a different file or action."})
                continue

            syntax_error = check_syntax(rel, content)
            if syntax_error:
                sig = f"syntax:{rel}"
                print(f"⚠ Syntax check failed for {rel} -- NOT written:\n  {syntax_error}")
                if register_fail(sig) >= MAX_CONSEC_FAILURES:
                    print(f"\nStopping: {rel} failed its syntax check {MAX_CONSEC_FAILURES} times in a row.")
                    persist_session()
                    return messages
                messages.append({"role": "user", "content": (
                    f"Error: the content for {rel} has a syntax error and was NOT written to disk:\n{syntax_error}\n\n"
                    f"Fix it and write the file again."
                )})
                continue

            current = read_file_safe(full_path)

            status, fp = reject_if_duplicate("write_file", [(rel, current, content)])
            if status == "stop":
                return messages
            if status == "duplicate":
                continue

            print(f"Write: {rel} — {action.get('note', '')}")
            if current is not None:
                risk = assess_risk(root, [rel])
                if risk["impacted_files"]:
                    print(f"  Risk analysis: {rel} is referenced by {len(risk['impacted_files'])} other file(s): "
                          f"{', '.join(risk['impacted_files'][:5])}{'...' if len(risk['impacted_files']) > 5 else ''}")
                    MEMORY_LOG.info(f"Risk analysis for overwrite of {rel}: impacts {risk['impacted_files']}")
            show_diff(current, content, rel)
            if confirm("write_file", config):
                protect_files([rel], f"before write_file: {action.get('note', '')[:80]}")
                write_one_file(root, rel, content)
                register_success(f"write_file:{rel}")
                clear_fail(f"syntax:{rel}")
                clear_duplicate(fp)
                attempt_memory.record_attempt("write_file", fp, [rel], action.get("note", ""))
                messages.append({"role": "user", "content": f"Wrote {rel} successfully."})
            else:
                sig = f"write_file:{rel}"
                if register_decline(sig) >= MAX_REPEAT_DECLINES:
                    print(f"\nStopping: the agent tried the same declined action ({sig}) {MAX_REPEAT_DECLINES} times in a row.")
                    persist_session()
                    return messages
                messages.append({"role": "user", "content": f"User declined writing {rel}. Choose a different action."})

        elif act == "write_project":
            missing = missing_required(action, "files")
            if missing:
                messages.append({"role": "user", "content": field_error_message(act, missing)})
                continue
            files = action["files"]
            bad_items = [f for f in files if missing_required(f, "path", "content")]
            if bad_items:
                messages.append({"role": "user", "content": 'Error: one or more entries in "files" is missing "path" and/or "content". Resend write_project with every file entry complete.'})
                continue
            blocked = [f["path"] for f in files if os.path.abspath(os.path.join(root, f["path"])) == SELF_PATH]
            if blocked:
                print(f"Blocked: refusing to let the agent write to its own script file ({blocked[0]}).")
                messages.append({"role": "user", "content": f"Error: {blocked[0]} is the agent's own script file and cannot be modified. Remove it from the scaffold and try again."})
                continue

            syntax_errors = [(f["path"], check_syntax(f["path"], f["content"])) for f in files]
            syntax_errors = [(p, e) for p, e in syntax_errors if e]
            if syntax_errors:
                sig = "syntax:project:" + ",".join(sorted(p for p, _ in syntax_errors))
                print("⚠ Syntax check failed -- NO files in this scaffold were written:")
                for p, e in syntax_errors:
                    print(f"  {e}")
                if register_fail(sig) >= MAX_CONSEC_FAILURES:
                    print(f"\nStopping: the same scaffold failed its syntax check {MAX_CONSEC_FAILURES} times in a row.")
                    persist_session()
                    return messages
                error_text = "\n".join(e for _, e in syntax_errors)
                messages.append({"role": "user", "content": (
                    f"Error: the following file(s) have syntax errors, so NONE of the {len(files)} files "
                    f"in this scaffold were written:\n{error_text}\n\nFix them and resend write_project."
                )})
                continue

            print(f"Scaffold {len(files)} file(s) — {action.get('note', '')}")
            files_changed = []
            for f in files:
                current = read_file_safe(os.path.join(root, f["path"]))
                files_changed.append((f["path"], current, f["content"]))
                show_diff(current, f["content"], f["path"])

            status, fp = reject_if_duplicate("write_project", files_changed)
            if status == "stop":
                return messages
            if status == "duplicate":
                continue

            if confirm("write_project", config, "Apply all?"):
                protect_files([f["path"] for f in files], f"before write_project: {action.get('note', '')[:80]}")
                for f in files:
                    write_one_file(root, f["path"], f["content"])
                    clear_fail(f"syntax:{f['path']}")
                register_success("write_project:" + ",".join(sorted(f["path"] for f in files)))
                clear_duplicate(fp)
                attempt_memory.record_attempt("write_project", fp, [f["path"] for f in files], action.get("note", ""))
                messages.append({"role": "user", "content": f"Created/updated {len(files)} files successfully."})
            else:
                sig = "write_project:" + ",".join(sorted(f["path"] for f in files))
                if register_decline(sig) >= MAX_REPEAT_DECLINES:
                    print(f"\nStopping: the agent tried the same declined scaffold {MAX_REPEAT_DECLINES} times in a row.")
                    persist_session()
                    return messages
                messages.append({"role": "user", "content": "User declined the project scaffold. Choose a different action."})

        elif act == "edit_file":
            missing = missing_required(action, "path", "old_text", "new_text")
            if missing:
                messages.append({"role": "user", "content": field_error_message(act, missing)})
                continue
            rel = action["path"]
            old_text = action["old_text"]
            new_text = action["new_text"]
            full_path = os.path.join(root, rel)
            if os.path.abspath(full_path) == SELF_PATH:
                print(f"Blocked: refusing to let the agent edit its own script file ({rel}).")
                messages.append({"role": "user", "content": f"Error: {rel} is the agent's own script file and cannot be modified. Choose a different file or action."})
                continue
            current = read_file_safe(full_path)
            print(f"Edit: {rel} — {action.get('note', '')}")

            if current is None:
                messages.append({"role": "user", "content": f"Error: {rel} does not exist, cannot edit."})
                continue
            occurrences = current.count(old_text)
            if occurrences != 1:
                messages.append({"role": "user", "content": f"Error: old_text found {occurrences} times in {rel}, expected exactly 1. Re-check exact text and try again."})
                continue

            new_content = current.replace(old_text, new_text)

            syntax_error = check_syntax(rel, new_content)
            if syntax_error:
                sig = f"syntax:{rel}"
                print(f"⚠ Syntax check failed for {rel} -- edit NOT applied:\n  {syntax_error}")
                if register_fail(sig) >= MAX_CONSEC_FAILURES:
                    print(f"\nStopping: {rel} failed its syntax check {MAX_CONSEC_FAILURES} times in a row.")
                    persist_session()
                    return messages
                messages.append({"role": "user", "content": (
                    f"Error: applying this edit to {rel} would introduce a syntax error, so it was NOT applied:\n{syntax_error}\n\n"
                    f"Adjust old_text/new_text and try again."
                )})
                continue

            status, fp = reject_if_duplicate("edit_file", [(rel, current, new_content)])
            if status == "stop":
                return messages
            if status == "duplicate":
                continue

            risk = assess_risk(root, [rel])
            if risk["impacted_files"]:
                print(f"  Risk analysis: {rel} is referenced by {len(risk['impacted_files'])} other file(s): "
                      f"{', '.join(risk['impacted_files'][:5])}{'...' if len(risk['impacted_files']) > 5 else ''}")
                MEMORY_LOG.info(f"Risk analysis for edit to {rel}: impacts {risk['impacted_files']}")

            show_diff(current, new_content, rel)
            if confirm("edit_file", config):
                protect_files([rel], f"before edit_file: {action.get('note', '')[:80]}")
                write_one_file(root, rel, new_content)
                register_success(f"edit_file:{rel}")
                clear_fail(f"syntax:{rel}")
                clear_duplicate(fp)
                attempt_memory.record_attempt("edit_file", fp, [rel], action.get("note", ""))
                messages.append({"role": "user", "content": f"Edited {rel} successfully."})
            else:
                sig = f"edit_file:{rel}"
                if register_decline(sig) >= MAX_REPEAT_DECLINES:
                    print(f"\nStopping: the agent tried the same declined edit ({sig}) {MAX_REPEAT_DECLINES} times in a row.")
                    persist_session()
                    return messages
                messages.append({"role": "user", "content": f"User declined editing {rel}. Choose a different action."})

        elif act == "edit_files":
            missing = missing_required(action, "edits")
            if missing:
                messages.append({"role": "user", "content": field_error_message(act, missing)})
                continue
            edits = action["edits"]
            bad_items = [e for e in edits if missing_required(e, "path", "old_text", "new_text")]
            if bad_items:
                messages.append({"role": "user", "content": 'Error: one or more entries in "edits" is missing "path", "old_text", and/or "new_text". Resend edit_files with every entry complete.'})
                continue
            blocked = [e["path"] for e in edits if os.path.abspath(os.path.join(root, e["path"])) == SELF_PATH]
            if blocked:
                print(f"Blocked: refusing to let the agent edit its own script file ({blocked[0]}).")
                messages.append({"role": "user", "content": f"Error: {blocked[0]} is the agent's own script file and cannot be modified. Remove it and try again."})
                continue
            print(f"Multi-file edit ({len(edits)} file(s)) — {action.get('note', '')}")
            prepared = []
            error = None
            for e in edits:
                rel = e["path"]
                current = read_file_safe(os.path.join(root, rel))
                if current is None:
                    error = f"Error: {rel} does not exist, cannot edit."
                    break
                occurrences = current.count(e["old_text"])
                if occurrences != 1:
                    error = f"Error: old_text found {occurrences} times in {rel}, expected exactly 1."
                    break
                new_content = current.replace(e["old_text"], e["new_text"])
                syntax_error = check_syntax(rel, new_content)
                if syntax_error:
                    error = f"Error: applying this edit to {rel} would introduce a syntax error:\n{syntax_error}"
                    break
                prepared.append((rel, current, new_content))
                show_diff(current, new_content, rel)

            if error:
                sig = "syntax:" + ",".join(sorted(e["path"] for e in edits))
                if "syntax error" in error and register_fail(sig) >= MAX_CONSEC_FAILURES:
                    print(f"\nStopping: the same multi-file edit failed {MAX_CONSEC_FAILURES} times in a row.")
                    persist_session()
                    return messages
                messages.append({"role": "user", "content": error + " None of these edits were applied. Re-check exact text and try again."})
                continue

            status, fp = reject_if_duplicate("edit_files", [(rel, before, after) for rel, before, after in prepared])
            if status == "stop":
                return messages
            if status == "duplicate":
                continue

            risk = assess_risk(root, [rel for rel, _b, _a in prepared])
            if risk["impacted_files"]:
                print(f"  Risk analysis: these edits are referenced by {len(risk['impacted_files'])} other file(s): "
                      f"{', '.join(risk['impacted_files'][:5])}{'...' if len(risk['impacted_files']) > 5 else ''}")
                MEMORY_LOG.info(f"Risk analysis for multi-file edit: impacts {risk['impacted_files']}")

            if confirm("edit_files", config, "Apply all edits?"):
                protect_files([rel for rel, _b, _a in prepared], f"before edit_files: {action.get('note', '')[:80]}")
                for rel, _before, new_content in prepared:
                    write_one_file(root, rel, new_content)
                    clear_fail(f"syntax:{rel}")
                register_success("edit_files:" + ",".join(sorted(e["path"] for e in edits)))
                clear_duplicate(fp)
                attempt_memory.record_attempt("edit_files", fp, [e["path"] for e in edits], action.get("note", ""))
                messages.append({"role": "user", "content": f"Edited {len(prepared)} files successfully."})
            else:
                sig = "edit_files:" + ",".join(sorted(e["path"] for e in edits))
                if register_decline(sig) >= MAX_REPEAT_DECLINES:
                    print(f"\nStopping: the agent tried the same declined multi-file edit {MAX_REPEAT_DECLINES} times in a row.")
                    persist_session()
                    return messages
                messages.append({"role": "user", "content": "User declined the multi-file edit. Choose a different action."})

        elif act == "run_command":
            missing = missing_required(action, "command")
            if missing:
                messages.append({"role": "user", "content": field_error_message(act, missing)})
                continue
            command = action["command"]
            print(f"Command: {command}")
            print(f"Reason: {action.get('note', '')}")
            if confirm("run_command", config, "Run this command?"):
                output = run_shell_command(command, cwd=root, timeout=timeout)
                print(f"  Output:\n{output}")
                cmd_sig = f"cmd:{command}"
                success = output.strip().startswith("exit code: 0")
                is_regression = regression_guard.record_result(command, success)
                if success:
                    register_success(f"run_command:{command}")
                    clear_fail(cmd_sig)
                    attempt_memory.resolve_pending(success=True, on_success=record_fix_success)
                    messages.append({"role": "user", "content": f"Command SUCCEEDED (exit code 0):\n{output}"})
                else:
                    fails = register_fail(cmd_sig)
                    attempt_memory.resolve_pending(success=False, error=output, on_failure=record_fix_failure)
                    if is_regression:
                        session["regression_detected"] = True
                        MEMORY_LOG.info(f"Regression Guard: '{command}' previously passed this session, now fails.")
                        maybe_rollback(f"'{command}' used to pass and now fails -- previously-working "
                                        f"functionality regressed")
                        continue
                    interactive_hint = interactive_input_failure_hint(command, output)
                    if fails >= MAX_CONSEC_FAILURES:
                        print(f"\nStopping: the exact command `{command}` failed {MAX_CONSEC_FAILURES} times in a "
                              f"row without a change of approach.")
                        persist_session()
                        return messages
                    if interactive_hint:
                        nudge = interactive_hint
                    elif fails >= 2:
                        nudge = (
                            f"\n\nThis exact command has now failed {fails} time(s) in a row. Don't just re-run it "
                            f"verbatim -- read the output above, diagnose the actual root cause (missing dependency, "
                            f"wrong path, bug in a file, wrong syntax for this shell, etc.), fix that, and only then "
                            f"try running something again."
                        )
                    else:
                        nudge = ""
                    messages.append({"role": "user", "content": f"Command FAILED:\n{output}{nudge}"})
            else:
                sig = f"run_command:{command}"
                if register_decline(sig) >= MAX_REPEAT_DECLINES:
                    print(f"\nStopping: the agent tried the same declined command {MAX_REPEAT_DECLINES} times in a row.")
                    persist_session()
                    return messages
                messages.append({"role": "user", "content": "User declined running this command. Choose a different action."})

        elif act == "git_commit":
            message = action.get("message", "Update project")
            git_ensure_repo(root, timeout)
            print("Git status:")
            print(git_status(root, timeout))
            print(f"Commit message: {message}")
            if confirm("git_commit", config, "Commit?"):
                output = git_commit(root, message, timeout)
                print(output)
                messages.append({"role": "user", "content": f"Git commit result:\n{output}"})
            else:
                messages.append({"role": "user", "content": "User declined the git commit. Choose a different action."})

        elif act == "git_remote_add":
            url = action.get("url", "")
            name = action.get("name", "origin")
            print(f"Add git remote '{name}' -> {url}")
            if confirm("git_remote_add", config, "Add/update this remote?"):
                git_ensure_repo(root, timeout)
                output = git_add_remote(root, url, name, timeout)
                print(output)
                messages.append({"role": "user", "content": f"git remote add/set result:\n{output}"})
            else:
                messages.append({"role": "user", "content": "User declined adding the git remote. Choose a different action."})

        elif act == "git_push":
            remote = action.get("remote", "origin")
            branch = action.get("branch")
            print(f"Push to remote '{remote}'" + (f" branch '{branch}'" if branch else " (current branch)"))
            if confirm("git_push", config, "Push now?"):
                output = git_push(root, remote, branch, timeout)
                print(output)
                messages.append({"role": "user", "content": f"git push result:\n{output}"})
            else:
                messages.append({"role": "user", "content": "User declined the git push. Choose a different action."})

        elif act == "done":
            if not verified_ok:
                test_cmd = detect_test_command(root)
                if test_cmd:
                    if auto_verify_enabled is None:
                        # Verification is a check, not a destructive action -- the Core
                        # Principle says this should happen automatically, not be asked
                        # about, as long as a rollback safety net exists to undo a bad
                        # auto-fix attempt. Without git available, fall back to asking.
                        auto_verify_enabled = config.get("autonomous_apply", True) and config.get("_rollback_ready")
                        if not auto_verify_enabled:
                            ans = input(
                                f"\nDetected a test command: '{test_cmd}'.\n"
                                f"Automatically run it to verify before finishing (auto-fixing up to "
                                f"{MAX_AUTO_VERIFY_ATTEMPTS} times if it fails)? [y/N] "
                            ).strip().lower()
                            auto_verify_enabled = (ans == "y")
                        else:
                            print(f"\n[Auto-verify enabled automatically -- rollback safety net is active. "
                                  f"Will run '{test_cmd}' and auto-fix up to {MAX_AUTO_VERIFY_ATTEMPTS} times if needed.]")

                    if auto_verify_enabled and auto_verify_attempts_left > 0:
                        print(f"\n[Auto-verifying with: {test_cmd}]")
                        output = run_shell_command(test_cmd, cwd=root, timeout=timeout)
                        print(output)
                        auto_verify_attempts_left -= 1
                        success = output.strip().startswith("exit code: 0")
                        is_regression = regression_guard.record_result(test_cmd, success)
                        if success:
                            verified_ok = True
                            attempt_memory.resolve_pending(success=True, on_success=record_fix_success)
                        else:
                            attempt_memory.resolve_pending(success=False, error=output, on_failure=record_fix_failure)
                            if is_regression:
                                session["regression_detected"] = True
                                MEMORY_LOG.info(f"Regression Guard: '{test_cmd}' previously passed this session, now fails.")
                                maybe_rollback(f"'{test_cmd}' used to pass and now fails after the latest change")
                                continue
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"Automatic verification failed after you declared done. Test output:\n{output}\n\n"
                                    f"Fix the issue(s) causing this failure, then call done again. "
                                    f"({auto_verify_attempts_left} auto-verify attempt(s) left.)"
                                ),
                            })
                            continue  # give the model another turn to fix it
                    elif auto_verify_enabled and auto_verify_attempts_left <= 0:
                        print(f"\n[Auto-verification exhausted after {MAX_AUTO_VERIFY_ATTEMPTS} attempts -- "
                              f"finishing anyway. You may want to check '{test_cmd}' manually.]")
                elif config.get("autonomous_apply", True) and config.get("_rollback_ready") and auto_verify_attempts_left > 0:
                    # Auto Test Generation (Feature 7), deliberately scoped: no test command
                    # exists in this project at all, so generate and run ONE minimal smoke
                    # test (does the entry point load without crashing?) rather than a full
                    # suite -- see generate_smoke_test()'s docstring for why this is the
                    # limit of what's realistically automatable here.
                    print("\n[No test command detected -- generating a minimal smoke test to sanity-check the result...]")
                    auto_verify_attempts_left -= 1
                    smoke = generate_smoke_test(root, tree, model, config, usage_tracker)
                    if smoke:
                        print(f"  Smoke test: {smoke['command']}\n{smoke['output']}")
                        is_regression = regression_guard.record_result(smoke["command"], smoke["success"])
                        if smoke["success"]:
                            verified_ok = True
                            record_knowledge_entry(project_id, f"Generated smoke test: {smoke['command']}", [],
                                                    kind="pattern", result="success")
                        else:
                            record_knowledge_entry(project_id, f"Generated smoke test: {smoke['command']}", [],
                                                    kind="pattern", result="failed", cause=smoke["output"][:300])
                            if is_regression:
                                session["regression_detected"] = True
                                maybe_rollback(f"generated smoke test '{smoke['command']}' used to pass and now fails")
                                continue
                            messages.append({"role": "user", "content": (
                                f"A generated smoke test failed, suggesting the main entry point doesn't load "
                                f"cleanly:\n{smoke['output']}\n\nCommand: {smoke['command']}\n\n"
                                f"Investigate and fix, then call done again."
                            )})
                            continue
                    else:
                        print("  (Could not generate a usable smoke test -- finishing without automated verification.)")

            sanity_issues = run_sanity_checks(root, project_id)
            if sanity_issues:
                print("\nSanity check warnings (non-blocking):")
                for issue in sanity_issues:
                    print(f"  - {issue}")
                MEMORY_LOG.info(f"Sanity check issues at done: {sanity_issues}")

            summary = action.get("summary", "")
            root_cause = action.get("root_cause") or {}
            touched_files = sorted({f for a in attempt_memory.task["attempts"] for f in a.get("files", [])})
            successes, failures = similar_fix_history(project_id, touched_files) if touched_files else (0, 0)
            task_confidence, task_reasons = compute_confidence(verified_ok, session["regression_detected"],
                                                                 successes, failures, len(sanity_issues))

            print(f"\n✔ Done: {summary}")
            if verified_ok:
                print("  (Verified: automatic test run passed.)")
            print(f"\nConfidence: {task_confidence}%")
            print("Reason:")
            for r in task_reasons:
                print(f"  - {r}")

            record_knowledge_entry(
                project_id, summary, touched_files, kind="fix",
                result="success" if verified_ok or not detect_test_command(root) else "failed",
                problem=root_cause.get("problem") or goal,
                cause=root_cause.get("cause"),
                confidence=task_confidence,
            )
            persist_session(status="completed")
            print("\n" + usage_tracker.summary())
            offer_zip(root)
            return messages

        else:
            print(f"Unknown action: {act}")
            persist_session()
            return messages

    print("\nReached max steps without completion.")
    persist_session()
    print("\n" + usage_tracker.summary())
    return messages

