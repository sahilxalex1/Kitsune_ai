"""Kitsune export_tests subsystem. Extracted without changing the original function bodies."""

from .foundation import *

def export_zip(root):
    root = os.path.abspath(root)
    base_name = os.path.basename(root.rstrip(os.sep)) or "project"
    parent = os.path.dirname(root)
    out_base = os.path.join(parent, base_name)
    zip_path = shutil.make_archive(out_base, "zip", root_dir=parent, base_dir=base_name)
    print(f"Zipped project to: {zip_path}")
    return zip_path

def detect_test_command(root):
    """Best-effort detection of how to run this project's tests, for the automatic
    test-fix verification loop. Returns a shell command string, or None if nothing
    recognizable was found."""
    def exists(*parts):
        return os.path.exists(os.path.join(root, *parts))

    if exists("pytest.ini") or exists("pyproject.toml") or exists("setup.cfg"):
        if exists("tests") or any(f.startswith("test_") and f.endswith(".py") for f in os.listdir(root) if os.path.isfile(os.path.join(root, f))):
            return "pytest -q"
    if exists("tests") and os.path.isdir(os.path.join(root, "tests")):
        return "pytest -q"

    if exists("package.json"):
        try:
            with open(os.path.join(root, "package.json"), "r", encoding="utf-8") as f:
                pkg = json.load(f)
            test_script = pkg.get("scripts", {}).get("test", "")
            if test_script and "no test specified" not in test_script.lower():
                return "npm test"
        except (json.JSONDecodeError, OSError):
            pass

    if exists("Cargo.toml"):
        return "cargo test"
    if exists("go.mod"):
        return "go test ./..."
    if exists("pom.xml"):
        return "mvn test"
    if exists("build.gradle") or exists("build.gradle.kts"):
        return "./gradlew test"

    return None

