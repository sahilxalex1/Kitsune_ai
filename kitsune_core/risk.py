"""Kitsune risk subsystem. Extracted without changing the original function bodies."""

from .foundation import *
from .foundation import *

RISK_SCAN_EXTENSIONS = (".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb", ".php", ".c", ".cpp", ".h", ".cs")

RISK_SCAN_FILE_CAP = 1500

def assess_risk(root, files_changed):
    """Naive but genuinely useful dependency-impact scan: for each changed file, find
    other source files elsewhere in the project that reference its module/base name.
    This is a text-match heuristic, not a real import graph -- it will have false
    positives/negatives, but it costs nothing extra to run and catches the common
    case ('this file is imported/required elsewhere') that a rename or signature
    change would silently break."""
    all_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for fn in filenames:
            all_files.append(os.path.join(dirpath, fn))
            if len(all_files) > RISK_SCAN_FILE_CAP:
                return {"impacted_files": [], "skipped": True}

    impacted = set()
    for changed_path in files_changed:
        base = os.path.splitext(os.path.basename(changed_path))[0]
        if not base:
            continue
        for fp in all_files:
            if os.path.splitext(fp)[1] not in RISK_SCAN_EXTENSIONS:
                continue
            rel_fp = os.path.relpath(fp, root)
            if rel_fp == changed_path:
                continue
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue
            if base in content:
                impacted.add(rel_fp)
    return {"impacted_files": sorted(impacted), "skipped": False}

