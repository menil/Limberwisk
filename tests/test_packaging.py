"""Guards for the packaging files, which are otherwise only exercised by a slow real build.

Each one pins something that has gone wrong, or would go wrong silently: a lazily imported
module missing from the bundle, a release asset the workflow cannot find, a secret that no
one documented.
"""

import ast
import fnmatch
import plistlib
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from muteme_flow import __version__
from muteme_flow.bundle_info import MINIMUM_MACOS, info_plist

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((ROOT / "scripts").glob("*.sh"))
BASH = shutil.which("bash")


# --- the bundle itself ---------------------------------------------------------------


def test_the_plist_is_serialisable_and_has_a_version_apple_accepts():
    plistlib.dumps(info_plist())
    assert re.fullmatch(r"\d+(\.\d+){0,2}", info_plist()["CFBundleShortVersionString"])
    assert info_plist()["CFBundleShortVersionString"] == __version__


def test_it_is_a_menu_bar_app_for_a_macos_that_has_the_login_item_api():
    assert info_plist()["LSUIElement"] is True
    assert tuple(map(int, MINIMUM_MACOS.split("."))) >= (13,)  # SMAppService


def test_the_entitlements_are_valid_and_only_relax_what_python_needs():
    entitlements = plistlib.loads((ROOT / "packaging" / "entitlements.plist").read_bytes())
    assert entitlements
    assert all(value is True for value in entitlements.values())
    dangerous = {
        "com.apple.security.get-task-allow",
        "com.apple.security.cs.disable-executable-page-protection",
        "com.apple.security.cs.allow-dyld-environment-variables",
    }
    assert not dangerous & entitlements.keys()


def py2app_lists() -> dict[str, list[str]]:
    """The `packages` and `includes` lists from packaging/setup.py, read without running it."""
    tree = ast.parse((ROOT / "packaging" / "setup.py").read_text())
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in ("packages", "includes"):
                    found[key.value] = [element.value for element in value.elts]
    return found


def test_hid_is_included_as_a_module_not_listed_as_a_package():
    # Listed under "packages", py2app copies the extension's binary into a hid.py that
    # shadows the real module (found by launching the first packaged build).
    lists = py2app_lists()
    assert "hid" not in lists["packages"]
    assert "hid" in lists["includes"]


def third_party_imports() -> set[str]:
    """Top-level third-party modules imported anywhere in the package, even inside functions."""
    found = set()
    for path in (ROOT / "src" / "muteme_flow").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                found |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found - set(sys.stdlib_module_names) - {"muteme_flow"}


def test_every_third_party_module_the_code_imports_is_bundled():
    # Lazy imports inside functions are easy for py2app's scan to miss, and a missing one
    # only fails inside the built app.
    lists = py2app_lists()
    bundled = {name.split(".")[0] for name in lists["packages"] + lists["includes"]}
    assert third_party_imports() <= bundled


def test_the_build_script_builds_the_hidapi_version_the_project_pins():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    pins = [d for d in pyproject["project"]["dependencies"] if d.startswith("hidapi==")]
    (pinned,) = re.findall(r"hidapi==([\d.]+)", pins[0])
    script = (ROOT / "scripts" / "build_app.sh").read_text()
    assert re.search(rf'HIDAPI_VERSION="?{re.escape(pinned)}"?', script)


# --- the scripts ---------------------------------------------------------------------


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.name)
def test_every_script_parses_and_is_executable(script):
    subprocess.run([BASH, "-n", str(script)], check=True)
    assert script.stat().st_mode & 0o111, f"{script.name} is not executable"


@pytest.mark.parametrize(
    ("script", "missing"),
    [("sign_app.sh", "SIGN_IDENTITY"), ("notarize.sh", "NOTARY_PROFILE")],
)
def test_signing_scripts_name_the_input_they_are_missing(script, missing):
    # A dummy path gets past the argument check to the environment check; both stop
    # before touching anything.
    result = subprocess.run(
        [BASH, str(ROOT / "scripts" / script), "dummy"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode != 0
    assert missing in result.stderr


def test_the_dmg_name_has_no_spaces_and_matches_the_pattern_the_workflow_uses():
    script = (ROOT / "scripts" / "make_dmg.sh").read_text()
    (pattern,) = re.findall(r'^dmg="(dist/[^"]+)"', script, re.M)
    assert " " not in pattern  # GitHub rewrites spaces in release asset names
    name = pattern.replace("$version", __version__).removeprefix("dist/")
    assert fnmatch.fnmatch(name, "MuteMe-Flow-*.dmg")


# --- the release workflow --------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text())


def steps(workflow, job="build"):
    return workflow["jobs"][job]["steps"]


def step_index(workflow, name):
    names = [step.get("name") for step in steps(workflow)]
    return names.index(name)


def test_it_only_runs_for_version_tags(workflow):
    # PyYAML reads the bare key `on` as the boolean True.
    assert workflow[True]["push"]["tags"] == ["v*"]


def test_only_the_final_job_can_write_and_it_runs_no_project_code(workflow):
    assert workflow["permissions"] == {"contents": "read"}
    assert "permissions" not in workflow["jobs"]["build"]
    assert workflow["jobs"]["release"]["permissions"] == {"contents": "write"}
    release_runs = " ".join(step.get("run", "") for step in steps(workflow, "release"))
    assert "scripts/" not in release_runs
    assert ".venv" not in release_runs


def test_releases_are_drafts_for_a_person_to_review(workflow):
    run = " ".join(step.get("run", "") for step in steps(workflow, "release"))
    assert "--draft" in run


def test_every_action_is_pinned_to_a_commit(workflow):
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.search(r"@[0-9a-f]{40}$", step["uses"].split(" ")[0]), step["uses"]


def test_the_downloaded_python_installer_is_verified_by_hash(workflow):
    env = workflow["jobs"]["build"]["env"]
    assert re.fullmatch(r"[0-9a-f]{64}", env["PYTHON_PKG_SHA256"])
    install = steps(workflow)[step_index(workflow, "Install a universal2 Python")]["run"]
    assert "shasum -a 256 -c" in install
    assert install.index("shasum") < install.index("installer -pkg")  # verified before installed


def test_secrets_reach_only_the_one_step_that_needs_them(workflow):
    build = workflow["jobs"]["build"]
    job_secrets = [key for key, value in build["env"].items() if "secrets." in str(value)]
    assert job_secrets == ["HAS_CERT"]  # a boolean flag, not a secret value
    for step in build["steps"]:
        uses_secrets = any("secrets." in str(v) for v in step.get("env", {}).values())
        assert uses_secrets == (step["name"] == "Import the signing certificate")


def test_the_steps_that_need_a_certificate_only_run_when_one_is_configured(workflow):
    for name in (
        "Import the signing certificate",
        "Notarize the app",
        "Notarize the DMG",
        "Remove the signing keychain",
    ):
        step = steps(workflow)[step_index(workflow, name)]
        assert "HAS_CERT" in step["if"], name


def test_the_keychain_is_removed_even_if_an_earlier_step_fails(workflow):
    step = steps(workflow)[step_index(workflow, "Remove the signing keychain")]
    assert "always()" in step["if"]


def test_steps_run_in_a_safe_order(workflow):
    order = [
        "Install a universal2 Python",
        "Check the tag matches the code's version",
        "Lint and test",
        "Import the signing certificate",
        "Build the app",
        "Notarize the app",
        "Build the DMG",
        "Notarize the DMG",
        "Stage the release files",
        "Keep the build for the release job",
    ]
    indexes = [step_index(workflow, name) for name in order]
    assert indexes == sorted(indexes)


def test_the_tag_must_match_the_codes_version_before_anything_is_built(workflow):
    check = steps(workflow)[step_index(workflow, "Check the tag matches the code's version")]
    assert "GITHUB_REF_NAME" in check["run"]
    assert step_index(workflow, "Check the tag matches the code's version") < step_index(
        workflow, "Build the app"
    )


def test_every_script_the_workflow_runs_exists_and_is_executable(workflow):
    text = " ".join(step.get("run", "") for step in steps(workflow))
    referenced = set(re.findall(r"scripts/[\w.]+\.sh", text))
    assert referenced
    for relative in referenced:
        path = ROOT / relative
        assert path.exists(), relative
        assert path.stat().st_mode & 0o111, f"{relative} is not executable"


def test_every_secret_the_workflow_uses_is_documented():
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    used = set(re.findall(r"secrets\.([A-Z_]+)", text))
    documented = (ROOT / "docs" / "releasing.md").read_text()
    missing = {name for name in used if name not in documented}
    assert not missing, f"undocumented secrets: {sorted(missing)}"


def test_the_release_job_finds_its_files_at_the_root_of_the_artifact(workflow):
    # upload-artifact keeps directory prefixes when the uploaded paths share only the
    # repository root, which broke the first real release run: the release job's glob
    # found nothing under dist/. One staged folder has no such ambiguity.
    upload = steps(workflow)[step_index(workflow, "Keep the build for the release job")]
    path = upload["with"]["path"].strip()
    assert "\n" not in path, "upload a single folder, not several paths"
    assert path.endswith("/")
    stage = steps(workflow)[step_index(workflow, "Stage the release files")]["run"]
    assert f"cp dist/MuteMe-Flow-*.dmg {path}" in stage
    assert f"{path}notes.md" in stage
    release_runs = " ".join(step.get("run", "") for step in steps(workflow, "release"))
    assert "dist/" not in release_runs
    assert "MuteMe-Flow-*.dmg" in release_runs
    assert "notes.md" in release_runs
