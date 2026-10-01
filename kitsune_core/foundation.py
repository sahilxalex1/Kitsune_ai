"""Shared runtime imports and foundational constants for partitioned Kitsune."""

import os
import sys
import json
import time
import shutil
import difflib
import argparse
import subprocess
import platform
import re
import ast
import tempfile
import hashlib
import uuid
import datetime
import requests

__version__ = "0.1.0-ollama"
SELF_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "kitsune.py"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_CONFIG = {
    "model": "qwen3.8:27b",
    # Optional per-task model overrides -- leave any of these null to fall back to "model"
    # above. Useful for e.g. a small/fast model for routing and chat, and a stronger
    # coding-specific model for build/fix/review.
    "router_model": None,
    "chat_model": None,
    "build_model": None,
    "fix_model": None,
    "review_model": None,
    "idea_model": None,
    "max_steps": 30,
    "command_timeout": 120,
    "auto_approve": ["read_file", "list_dir", "search_files", "web_search"],
    "autonomous_apply": True,  # apply write/edit actions without asking, IF a git rollback safety net
                                # is available for this project (see confirm() and Reliability Engine);
                                # falls back to asking when git isn't available, since there'd be no undo
    "context_window": 32768,  # qwen3.8:27b natively supports up to 262K; raise further if your VRAM allows
    "max_checkpoints": 50,  # per project -- Universal Recovery Layer snapshot cap; oldest pruned first
    "max_checkpoint_storage_mb": 100,  # per project -- pruned oldest-first once exceeded
}
MEMORY_FILENAME = ".agent_memory.json"
CONFIG_FILENAME = ".agent_config.json"
ATTEMPTS_FILENAME = ".agent_attempts.json"
PROJECT_MARKER_FILENAME = ".kitsune_id"
MEMORY_SCHEMA_VERSION = 2
IS_WINDOWS = platform.system() == "Windows"
SHELL_NAME = "PowerShell" if IS_WINDOWS else "bash"
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}
