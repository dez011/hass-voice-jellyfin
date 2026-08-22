"""Guards for the rules hassfest enforces.

CI ran hassfest but nothing local did, so manifest key ordering and the
"no HTML / no URLs in translations" rules only failed after a push. These
tests catch the same violations before committing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_COMPONENT = _ROOT / "custom_components" / "voice_jellyfin"
_MANIFEST = _COMPONENT / "manifest.json"
_STRINGS = _COMPONENT / "strings.json"
_EN = _COMPONENT / "translations" / "en.json"

_URL_RE = re.compile(r"https?://")
# hassfest rejects tag-like markup. Markdown emphasis (**bold**) is fine and
# is used throughout the step descriptions, so it is deliberately not matched.
_HTML_RE = re.compile(r"<[a-zA-Z/][^>]*>")


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _walk(node, trail=""):
    """Yield (dotted_path, string) for every string in a nested structure."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{trail}.{k}" if trail else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{trail}[{i}]")
    elif isinstance(node, str):
        yield trail, node


def test_manifest_keys_sorted_the_way_hassfest_wants():
    """domain, name, then everything else alphabetically."""
    keys = list(_load(_MANIFEST).keys())
    assert keys[:2] == ["domain", "name"], f"first keys were {keys[:2]}"
    rest = keys[2:]
    assert rest == sorted(rest), f"not alphabetical after domain/name: {rest}"


def test_manifest_declares_the_components_we_import():
    """frontend.py imports homeassistant.components.{http,frontend}; both
    must be declared or HA may load us before they are ready."""
    deps = _load(_MANIFEST)["dependencies"]
    assert "http" in deps
    assert "frontend" in deps


def test_manifest_version_matches_const():
    from custom_components.voice_jellyfin.const import VERSION

    assert _load(_MANIFEST)["version"] == VERSION


@pytest.mark.parametrize("path", [_STRINGS, _EN], ids=["strings.json", "en.json"])
def test_no_urls_in_translations(path):
    offenders = [t for t, s in _walk(_load(path)) if _URL_RE.search(s)]
    assert not offenders, f"URLs must use description placeholders: {offenders}"


@pytest.mark.parametrize("path", [_STRINGS, _EN], ids=["strings.json", "en.json"])
def test_no_html_in_translations(path):
    offenders = [t for t, s in _walk(_load(path)) if _HTML_RE.search(s)]
    assert not offenders, f"tag-like markup not allowed: {offenders}"


def test_strings_and_en_translation_stay_in_sync():
    """They drifted before; a missing key means an untranslated label."""
    assert _load(_STRINGS) == _load(_EN)
