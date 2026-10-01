"""Kitsune review subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .agent_protocol import *
from .export_tests import *
from .repo import *
from .web import *

def offer_zip(root):
    if input("\nZip this project for easy sharing/backup? [y/N] ").strip().lower() == "y":
        export_zip(root)

def run_review(root, target_description, config, usage_tracker):
    """Read-only review loop -- only list_dir/search_files/web_search/read_file/done are
    ever dispatched. No write/edit/run/git action exists in this loop at all, so there's
    nothing to accidentally approve."""
    model = config["model"]
    tree = build_tree(root)

    intro = (
        f"Project folder: {os.path.abspath(root)}\n\nCurrent file tree:\n{tree}\n\n"
        f"Review task: {target_description}\n\nBegin. Respond with your first action."
    )
    messages = [{"role": "user", "content": intro}]

    for step in range(1, config["max_steps"] + 1):
        print(f"\n=== Step {step} ===")
        try:
            raw_text, action = get_next_action_generic(messages, REVIEW_SYSTEM_PROMPT, model, config, usage_tracker, label="review")
        except json.JSONDecodeError:
            print("Model returned non-JSON output, stopping.")
            break
        except Exception as e:
            print(f"API error: {e}")
            break

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
            pattern = action["pattern"]
            matches = search_in_files(root, pattern)
            result = "\n".join(matches) if matches else "No matches found."
            messages.append({"role": "user", "content": f"Search results for '{pattern}':\n{result}"})

        elif act == "find_symbol":
            name = action["name"]
            index = load_repo_index(root)
            if index is None:
                index = build_repo_index(root)
                save_repo_index(root, index)
            matches = find_symbol_in_index(index, name)
            result = "\n".join(matches) if matches else f"No symbol matching '{name}' found in the index."
            messages.append({"role": "user", "content": f"find_symbol results for '{name}':\n{result}"})

        elif act == "web_search":
            query = action["query"]
            print(f"Web search: {query}")
            result = do_web_search(query)
            print(f"  Results:\n{result}\n")
            messages.append({"role": "user", "content": f"Web search results for '{query}':\n{result}"})

        elif act == "read_file":
            rel = action["path"]
            content = read_file_safe(os.path.join(root, rel))
            result_text = content if content is not None else "FILE DOES NOT EXIST"
            messages.append({"role": "user", "content": f"Content of {rel}:\n{result_text}"})

        elif act in ("write_file", "write_project", "edit_file", "edit_files", "run_command", "git_commit", "git_remote_add", "git_push", "make_dirs"):
            print(f"[Blocked: '{act}' isn't available in review mode -- this is read-only.]")
            messages.append({"role": "user", "content": f"Error: '{act}' is not available in review mode, which is strictly read-only. Continue the review using only list_dir/search_files/web_search/read_file, then call done."})

        elif act == "done":
            report = action.get("summary", "")
            print("\n" + "=" * 70)
            print("REVIEW REPORT")
            print("=" * 70)
            print(report)
            print("\n" + usage_tracker.summary())
            if input("\nSave this report to REVIEW.md in the project folder? [y/N] ").strip().lower() == "y":
                write_one_file(root, "REVIEW.md", report)
                print(f"Saved to {os.path.join(root, 'REVIEW.md')}")
            return

        else:
            print(f"Unknown action: {act}")
            return

    print("\nReached max steps without completing the review.")
    print("\n" + usage_tracker.summary())

