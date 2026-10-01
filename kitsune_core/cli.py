"""Kitsune cli subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .foundation import __version__
from .commands import *
from .config import *
from .foundation import *
from .startup import *
from .storage import *

def build_parser():
    parser = argparse.ArgumentParser(
        prog="kitsune",
        description="Local AI assistant + coding agent (Ollama-powered) -- no API key, no cost.",
    )
    parser.add_argument("--version", action="version", version=f"kitsune {__version__}")
    parser.add_argument("--quiet", "-q", action="store_true", help="Skip the startup Memory Recovery Report")
    subparsers = parser.add_subparsers(dest="command")

    p_build = subparsers.add_parser("build", help="Build or edit a project in a folder")
    p_build.add_argument("--dir", "-d", default=".", help="Project folder (default: current directory)")
    p_build.add_argument("--goal", "-g", default=None, help="Instruction for the agent (skips the prompt)")
    p_build.add_argument("--model", "-m", default=None, help="Ollama model to use (e.g. qwen2.5-coder:7b)")
    p_build.add_argument("--no-resume", action="store_true", help="Don't offer to resume a previous session")

    p_fix = subparsers.add_parser("fix", help="Read a project/file and fix bugs")
    p_fix.add_argument("--dir", "-d", default=".", help="Project folder (default: current directory)")
    p_fix.add_argument("--file", "-f", default=None, help="Specific file to focus on (optional)")
    p_fix.add_argument("--error", "-e", default=None, help="Paste the exact error/traceback (optional but helps a lot)")
    p_fix.add_argument("--run", "-r", default=None, help="Command that reproduces the bug, e.g. 'python app.py' (optional)")
    p_fix.add_argument("--model", "-m", default=None, help="Ollama model to use")

    p_review = subparsers.add_parser("review", help="Read-only code review -- never writes/edits/runs anything")
    p_review.add_argument("--dir", "-d", default=".", help="Project folder (default: current directory)")
    p_review.add_argument("--file", "-f", default=None, help="Specific file to review (optional; default: whole project)")
    p_review.add_argument("--focus", default=None, help="What to focus on, e.g. 'security', 'performance' (optional)")
    p_review.add_argument("--model", "-m", default=None, help="Ollama model to use")

    p_chat = subparsers.add_parser("chat", help="Open-ended conversation (no file/command access)")
    p_chat.add_argument("--model", "-m", default=None)

    p_idea = subparsers.add_parser("idea", help="Brainstorm project or feature ideas (single exchange)")
    p_idea.add_argument("--model", "-m", default=None)

    p_undo = subparsers.add_parser("undo", help="Revert the last git commit in a project folder")
    p_undo.add_argument("--dir", "-d", default=".")

    p_memory = subparsers.add_parser("memory", help="View a saved session in a project folder without resuming it")
    p_memory.add_argument("--dir", "-d", default=".")

    p_attempts = subparsers.add_parser("attempts", help="View the Coding Attempt Memory (fixes tried, and whether each worked) for a project")
    p_attempts.add_argument("--dir", "-d", default=".")

    p_gc = subparsers.add_parser("gc", help="Memory maintenance: detect removed projects, archive stale workspace memory (never deletes knowledge/environment memory)")
    p_gc.add_argument("--archive-after-days", type=int, default=90, help="Archive workspace memory for removed/archived projects untouched this many days (default: 90)")

    p_index = subparsers.add_parser("index", help="Build/refresh the repository symbol index")
    p_index.add_argument("--dir", "-d", default=".")
    p_index.add_argument("--find", default=None, help="Also look up a symbol name after indexing")

    return parser

def interactive_menu(available_models):
    print("=" * 60)
    print(" Kitsune -- Local AI Coding Assistant (Ollama, free)")
    print("=" * 60)
    print(f"Available local models: {', '.join(available_models) if available_models else '(none pulled yet)'}")
    print()
    print("1) Build or edit a project (agent works in a folder)")
    print("2) Fix a bug in existing code")
    print("3) Review code (read-only -- never writes/edits/runs anything)")
    print("4) Chat (open-ended conversation)")
    print("5) Brainstorm project / feature ideas (single exchange)")
    print("6) View saved session memory for a project (no resuming)")
    print("7) View coding attempt memory (fixes tried, and whether each worked)")
    print("8) Build/refresh the repository symbol index")
    print("9) Undo last git commit in a project folder")
    print("10) Run memory maintenance (detect removed projects, archive stale workspace memory)")
    print("11) Exit")
    choice = input("\nChoose [1-11]: ").strip()

    if choice == "1":
        dir_input = input("Project folder path (blank = current directory): ").strip() or "."
        cmd_build(argparse.Namespace(dir=dir_input, goal=None, model=None, no_resume=False), available_models)
    elif choice == "2":
        dir_input = input("Project folder path (blank = current directory): ").strip() or "."
        cmd_fix(argparse.Namespace(dir=dir_input, file=None, error=None, run=None, model=None), available_models)
    elif choice == "3":
        dir_input = input("Project folder path (blank = current directory): ").strip() or "."
        cmd_review(argparse.Namespace(dir=dir_input, file=None, focus=None, model=None), available_models)
    elif choice == "4":
        cmd_chat(argparse.Namespace(model=None), available_models)
    elif choice == "5":
        cmd_idea(argparse.Namespace(model=None), available_models)
    elif choice == "6":
        dir_input = input("Project folder path (blank = current directory): ").strip() or "."
        cmd_memory(argparse.Namespace(dir=dir_input), available_models)
    elif choice == "7":
        dir_input = input("Project folder path (blank = current directory): ").strip() or "."
        cmd_attempts(argparse.Namespace(dir=dir_input), available_models)
    elif choice == "8":
        dir_input = input("Project folder path (blank = current directory): ").strip() or "."
        find_input = input("Also look up a symbol now (blank to skip): ").strip() or None
        cmd_index(argparse.Namespace(dir=dir_input, find=find_input), available_models)
    elif choice == "9":
        dir_input = input("Project folder path (blank = current directory): ").strip() or "."
        cmd_undo(argparse.Namespace(dir=dir_input), available_models)
    elif choice == "10":
        cmd_gc(argparse.Namespace(archive_after_days=90), available_models)
    else:
        print("Bye!")

def main():
    parser = build_parser()
    args = parser.parse_args()

    validate_core_structure()  # always runs, even with --quiet -- directory setup/repair isn't optional

    available_models = check_ollama_running()

    if not getattr(args, "quiet", False):
        generate_recovery_report(available_models)

    if not getattr(args, "command", None):
        interactive_menu(available_models)
        return

    if args.command == "build":
        cmd_build(args, available_models)
    elif args.command == "fix":
        cmd_fix(args, available_models)
    elif args.command == "review":
        cmd_review(args, available_models)
    elif args.command == "chat":
        cmd_chat(args, available_models)
    elif args.command == "idea":
        cmd_idea(args, available_models)
    elif args.command == "memory":
        cmd_memory(args, available_models)
    elif args.command == "attempts":
        cmd_attempts(args, available_models)
    elif args.command == "gc":
        cmd_gc(args, available_models)
    elif args.command == "index":
        cmd_index(args, available_models)
    elif args.command == "undo":
        cmd_undo(args, available_models)

