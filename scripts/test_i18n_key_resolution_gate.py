"""Teeth for `scripts/i18n-key-resolution-gate.py` — proof it goes red on a bad input.

Two kinds of test here, and the second kind is the one that matters.

The first proves the gate FAILS on the defect it exists for: a `t()` key with no `en` entry.
A gate that only ever passes has certified nothing.

The rest pin FALSE POSITIVES the gate produced on its first runs against the real repo. Each
was a working call reported as broken, and each is why a lint like this normally ends up
disabled rather than fixed:

  * namespaces bind PER IDENTIFIER — GroundingSection.tsx holds
    `const { t: tKnowledge } = useTranslation('knowledge')` beside
    `const { t } = useTranslation('chat')`, and taking the file's first match blamed chat's
    keys on knowledge.json
  * `t('common.cancel', { ns: 'common' })` overrides the binding for that one call
  * `t('a.b.' + variant)` is a runtime-built key; its literal PREFIX was reported as a
    missing key ending in a dot
  * i18next takes a positional default — `t(key, 'text')` — not only `{ defaultValue }`
  * `t(key, { count })` resolves a plural SIBLING (`key_one`/`key_other`); a bare `key`
    need not exist at all, and gap.bulkPromote.cta was reported missing because of it
  * `returnObjects` reads a whole ARRAY, so a list is a legitimate leaf
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent / "i18n-key-resolution-gate.py"
_SPEC = importlib.util.spec_from_file_location("i18n_key_resolution_gate", _PATH)
gate = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = gate
_SPEC.loader.exec_module(gate)


# ── the point of the gate: a key with no bundle entry must be a finding ──────────────

def test_missing_key_does_not_resolve():
    bundle = {"panels": {"editor": {"title": "Editor"}}}
    assert gate.resolves(bundle, "panels.editor.title")
    assert not gate.resolves(bundle, "panels.editor.subtitle")
    assert not gate.resolves(bundle, "panels.missing.title")


def test_a_subtree_is_not_a_usable_leaf():
    """`t('panels.editor')` would render an object. That is a defect, not a translation."""
    bundle = {"panels": {"editor": {"title": "Editor"}}}
    assert not gate.resolves(bundle, "panels.editor")


def test_empty_bundle_resolves_nothing():
    assert not gate.resolves({}, "anything")


# ── false positives, each measured against the real repo ─────────────────────────────

def test_namespace_binds_per_identifier_not_per_file():
    src = """
      const { t: tKnowledge } = useTranslation('knowledge');
      const { t } = useTranslation('chat');
    """
    assert gate.bindings(src) == {"tKnowledge": "knowledge", "t": "chat"}


def test_plain_binding_and_extra_destructured_names():
    assert gate.bindings("const { t } = useTranslation('studio');") == {"t": "studio"}
    assert gate.bindings("const { t, i18n } = useTranslation('books');") == {"t": "books"}


def test_runtime_built_key_prefix_is_not_taken_for_a_whole_key():
    """`t('a.b.' + v)` must yield NOTHING; its prefix is not a key."""
    found = gate.call_pattern("t").findall("{t('behavior.reasoning.' + v)}")
    assert found == []


def test_complete_literal_key_is_matched_with_and_without_options():
    pattern = gate.call_pattern("t")
    assert [k for k, _ in pattern.findall("t('a.b')")] == ["a.b"]
    assert [k for k, _ in pattern.findall("t('a.b', { count: 2 })")] == ["a.b"]
    assert [k for k, _ in pattern.findall("t('a.b', 'a positional default')")] == ["a.b"]


def test_per_call_ns_option_is_captured():
    pattern = gate.call_pattern("t")
    (key, options), = pattern.findall("t('common.cancel', { ns: 'common' })")
    assert key == "common.cancel"
    assert gate.NS_OPTION.search(options).group(1) == "common"


def test_plural_siblings_resolve_without_a_bare_key():
    """i18next resolves t(key, {count}) to key_one/key_other; a bare key need not exist."""
    bundle = {"gap": {"bulkPromote": {"cta_one": "Promote 1", "cta_other": "Promote {{count}}"}}}
    assert gate.resolves(bundle, "gap.bulkPromote.cta")


def test_string_list_is_a_leaf_but_a_list_of_objects_is_not():
    """`returnObjects: true` reads a whole array — books.help.items is 3 strings."""
    assert gate.resolves({"help": {"items": ["a", "b"]}}, "help.items")
    assert not gate.resolves({"help": {"items": [{"a": 1}]}}, "help.items")


# ── the anti-vacuity guard, and its one deliberate exception ─────────────────────────

def test_full_repo_run_refuses_to_pass_on_an_empty_scan(monkeypatch, capsys):
    """Finding nothing means the call shapes drifted, not that the repo is clean."""
    monkeypatch.setattr(gate, "components", lambda staged_only: [])
    monkeypatch.setattr(sys, "argv", ["i18n-key-resolution-gate.py"])
    assert gate.main() == 1
    assert "finding nothing" in capsys.readouterr().out


def test_staged_run_passes_when_no_component_is_staged(monkeypatch, capsys):
    """A commit touching only .ts helpers legitimately stages no component. Applying the
    guard above there would block ordinary commits — which is worse than the blind spot."""
    monkeypatch.setattr(gate, "components", lambda staged_only: [])
    monkeypatch.setattr(sys, "argv", ["i18n-key-resolution-gate.py", "--staged"])
    assert gate.main() == 0
    assert "no component with t() calls staged" in capsys.readouterr().out


def test_gate_reds_on_a_component_whose_key_is_absent(tmp_path, monkeypatch, capsys):
    """End to end: a real file, a real bundle, one missing key -> exit 1."""
    en = tmp_path / "en"
    en.mkdir()
    (en / "studio.json").write_text(json.dumps({"panels": {"editor": {"title": "Editor"}}}),
                                    encoding="utf-8")
    component = tmp_path / "Panel.tsx"
    component.write_text(
        "const { t } = useTranslation('studio');\n"
        "<h1>{t('panels.editor.title')}</h1>\n"
        "<h2>{t('panels.editor.subtitle', 'Subtitle')}</h2>\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "EN", en)
    monkeypatch.setattr(gate, "REPO", tmp_path)
    monkeypatch.setattr(gate, "components", lambda staged_only: [component])
    gate.load_namespace.__defaults__ = ({},)  # drop the module-level bundle cache
    monkeypatch.setattr(sys, "argv", ["i18n-key-resolution-gate.py"])
    assert gate.main() == 1
    out = capsys.readouterr().out
    assert "panels.editor.subtitle" in out
    assert "panels.editor.title" not in out.split("FAIL", 1)[1].split("\n\n", 1)[0]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
