"""Keeps the written documentation honest about the code it describes."""

import importlib.util
import itertools
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, fields
from pathlib import Path

import pytest

from limberwisk.menu_model import status_text
from limberwisk.settings import HOLD_THRESHOLD_CHOICES_MS

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", ROOT / "specs" / "spec.md", *sorted((ROOT / "docs").glob("*.md"))]


@dataclass
class AnyStatus:
    command_failed: bool = False
    conflict: bool = False
    open_failed: bool = False
    device_connected: bool = True
    wispr_running: bool = True
    recording: bool = False


def every_status_the_menu_can_show() -> set[str]:
    names = [field.name for field in fields(AnyStatus)]
    return {
        status_text(AnyStatus(**dict(zip(names, values, strict=True))))
        for values in itertools.product([False, True], repeat=len(names))
    }


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: path.name)
def test_every_script_a_document_mentions_exists(doc):
    mentioned = set(re.findall(r"scripts/[\w.]+\.(?:py|sh)", doc.read_text()))
    missing = {name for name in mentioned if not (ROOT / name).exists()}
    assert not missing, f"{doc.name} mentions scripts that do not exist: {sorted(missing)}"


def test_every_status_the_readme_quotes_is_one_the_menu_really_shows():
    readme = (ROOT / "README.md").read_text()
    quoted = set(re.findall(r"`(Status: [^`]+?)`", readme))
    quoted = {text.replace("\n", " ") for text in quoted}
    assert quoted, "the README should quote statuses"
    assert quoted <= every_status_the_menu_can_show()


def test_the_readme_lists_the_hold_thresholds_the_menu_offers():
    readme = (ROOT / "README.md").read_text()
    listed = tuple(int(n) for n in re.search(r"\(250, (\d+) or (\d+) ms\)", readme).groups())
    assert (250, *listed) == HOLD_THRESHOLD_CHOICES_MS


def load_measure_idle():
    spec = importlib.util.spec_from_file_location(
        "measure_idle", ROOT / "scripts" / "measure_idle.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # stdlib only, and main() is guarded
    return module


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("0:01.23", 1.23),
        ("0:00.00", 0.0),
        ("1:02.34", 62.34),
        ("1:02:03.45", 3723.45),
        ("1-02:03:04", 86400 + 2 * 3600 + 3 * 60 + 4),
    ],
)
def test_ps_cpu_time_is_parsed_in_every_format_ps_prints(text, seconds):
    assert load_measure_idle().parse_ps_time(text) == pytest.approx(seconds)


@pytest.mark.parametrize(
    ("text", "megabytes"),
    [
        ("Footprint: 44 MB", 44.0),
        ("Footprint: 512 KB", 0.5),
        ("Footprint: 1.2 GB", 1.2 * 1024),
        ("nothing useful here", None),
    ],
)
def test_footprint_output_is_parsed_into_megabytes(text, megabytes):
    assert load_measure_idle().parse_footprint_mb(text) == (
        pytest.approx(megabytes) if megabytes is not None else None
    )


def local_images(doc: Path) -> set[str]:
    targets = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", doc.read_text())
    return {target for target in targets if not target.startswith(("http://", "https://"))}


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: path.name)
def test_every_local_image_a_document_shows_exists(doc):
    missing = {t for t in local_images(doc) if not (doc.parent / t).exists()}
    assert not missing, f"{doc.name} shows images that do not exist: {sorted(missing)}"


def test_the_readme_has_its_hero_image():
    assert "docs/images/hero.svg" in local_images(ROOT / "README.md")


@pytest.mark.parametrize(
    "svg", sorted((ROOT / "docs" / "images").glob("*.svg")), ids=lambda p: p.name
)
def test_svg_images_are_well_formed_and_described_for_screen_readers(svg):
    root = ET.fromstring(svg.read_text())  # an illegal comment or stray tag fails here
    names = {element.tag.rsplit("}", 1)[-1] for element in root.iter()}
    assert {"title", "desc"} <= names
    assert root.get("role") == "img"


def test_dependabot_updates_actions_and_python_without_triggering_releases():
    import yaml

    config = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text())
    updates = {u["package-ecosystem"]: u for u in config["updates"]}
    assert set(updates) == {"github-actions", "pip"}
    for update in updates.values():
        # release-please only cuts a release for feat and fix commits.
        assert update["commit-message"]["prefix"] not in {"feat", "fix"}


def test_the_bug_report_form_asks_for_the_diagnostics_the_menu_copies():
    import yaml

    form = yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").read_text())
    fields = [f for f in form["body"] if f.get("id") == "diagnostics"]
    assert len(fields) == 1, f"expected one diagnostics field in the form, found {len(fields)}"
    diagnostics = fields[0]
    assert diagnostics["validations"]["required"] is True
    assert "Copy Diagnostics" in diagnostics["attributes"]["description"]
    # The menu item the form names must exist under that name.
    assert '"Copy Diagnostics"' in (ROOT / "src" / "limberwisk" / "app.py").read_text()
