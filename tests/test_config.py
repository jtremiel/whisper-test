from pathlib import Path

import pytest

from voicecmd import config as cfgmod
from voicecmd.config import ConfigError, config_path, ensure_config, load_config, open_in_editor
from voicecmd.schema import Config


def test_config_path_uses_platformdirs():
    p = config_path()
    assert p.name == "config.yaml"
    assert p.parent.name == "voicecmd"


def test_ensure_config_creates_on_first_run(tmp_path: Path):
    target = tmp_path / "sub" / "config.yaml"
    assert ensure_config(target) == target
    assert target.read_text(encoding="utf-8") == cfgmod.default_config_text()
    cfg = load_config(target)
    assert isinstance(cfg, Config)
    assert cfg.commands


def test_ensure_config_does_not_overwrite(tmp_path: Path):
    target = tmp_path / "config.yaml"
    target.write_text("language: en\n", encoding="utf-8")
    ensure_config(target)
    assert target.read_text(encoding="utf-8") == "language: en\n"


def test_load_valid(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "language: it\n"
        "commands:\n"
        "  - name: Apri\n"
        "    phrases: [apri]\n"
        "    action: {type: open, target: 'https://example.com'}\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.commands[0].name == "Apri"


def test_empty_file_gives_defaults(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("", encoding="utf-8")
    assert load_config(p) == Config()


def test_missing_file(tmp_path: Path):
    with pytest.raises(ConfigError, match="non trovato"):
        load_config(tmp_path / "nope.yaml")


def test_malformed_yaml(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("language: it\nstt:\n  model: [turbo\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        load_config(p)
    msg = str(ei.value)
    assert "YAML" in msg and "riga" in msg


def test_top_level_not_mapping(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="chiave: valore"):
        load_config(p)


def test_unknown_field(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("matching:\n  treshold: 70\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        load_config(p)
    assert "'matching.treshold': campo sconosciuto" in str(ei.value)


def test_out_of_range(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("matching:\n  threshold: 150\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        load_config(p)
    assert "'matching.threshold': valore troppo alto" in str(ei.value)


def test_empty_phrases_and_index_in_path(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "commands:\n"
        "  - name: A\n"
        "    phrases: []\n"
        "    action: {type: open, target: x}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as ei:
        load_config(p)
    assert "'commands[0].phrases'" in str(ei.value)


def test_unknown_action_type(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "commands:\n"
        "  - name: A\n"
        "    phrases: [a]\n"
        "    action: {type: telnet}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as ei:
        load_config(p)
    msg = str(ei.value)
    assert "'commands[0].action'" in msg and "tipo di azione sconosciuto" in msg and "telnet" in msg


def test_italian_validator_message(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("triggers:\n  command: {hotkey: 'a', mouse_button: x1}\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        load_config(p)
    msg = str(ei.value)
    assert "'triggers.command'" in msg and "esattamente uno" in msg


def test_duplicate_names_message(tmp_path: Path):
    p = tmp_path / "c.yaml"
    cmd = "  - name: A\n    phrases: [a]\n    action: {type: open, target: x}\n"
    p.write_text("commands:\n" + cmd + cmd, encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicato"):
        load_config(p)


@pytest.mark.parametrize(
    "platform, expected",
    [("darwin", ("popen", ["open"])), ("linux", ("popen", ["xdg-open"])), ("win32", ("startfile", None))],
)
def test_open_in_editor(monkeypatch, tmp_path: Path, platform, expected):
    calls = []
    monkeypatch.setattr(cfgmod.sys, "platform", platform)
    monkeypatch.setattr(cfgmod.subprocess, "Popen", lambda args: calls.append(("popen", args)))
    monkeypatch.setattr(cfgmod.os, "startfile", lambda p: calls.append(("startfile", p)), raising=False)
    target = tmp_path / "config.yaml"
    open_in_editor(target)
    assert len(calls) == 1
    kind, arg = calls[0]
    assert kind == expected[0]
    if kind == "popen":
        assert arg == expected[1] + [str(target)]
    else:
        assert arg == str(target)
