from importlib import resources

import pytest
import yaml
from pydantic import ValidationError

from voicecmd.schema import Command, Config, OpenAction, ShellAction

PRD_EXAMPLE = """
language: it
stt:
  model: turbo
  compute_type: int8
triggers:
  command:
    hotkey: "<ctrl>+<alt>+space"
  dictation:
    mouse_button: x2
matching:
  threshold: 80
  margin: 5
feedback:
  tray: true
  sounds: true
  overlay: true
  notifications: true
commands:
  - name: Apri browser
    phrases: ["apri il browser", "apri chrome"]
    action:
      type: open
      target: "https://www.google.com"
  - name: Blocca schermo
    phrases: ["blocca lo schermo"]
    action:
      type: shell
      mac: "pmset displaysleepnow"
      windows: "rundll32.exe user32.dll,LockWorkStation"
"""


def _data() -> dict:
    return yaml.safe_load(PRD_EXAMPLE)


def test_default_config_valid():
    text = (resources.files("voicecmd") / "default_config.yaml").read_text(encoding="utf-8")
    cfg = Config.model_validate(yaml.safe_load(text))
    assert 3 <= len(cfg.commands) <= 4


def test_prd_example_valid():
    cfg = Config.model_validate(_data())
    assert cfg.triggers.dictation.mouse_button == "x2"
    assert isinstance(cfg.commands[0], Command)
    assert isinstance(cfg.commands[0].action, OpenAction)
    assert isinstance(cfg.commands[1].action, ShellAction)
    assert cfg.commands[1].action.timeout == 30
    assert cfg.matching.threshold == 80


def test_defaults_on_empty_config():
    cfg = Config.model_validate({})
    assert cfg.commands == []
    assert cfg.triggers.command.hotkey


@pytest.mark.parametrize("trigger", [
    {"hotkey": "<ctrl>+a", "mouse_button": "x1"},
    {},
])
def test_trigger_needs_exactly_one(trigger):
    d = _data()
    d["triggers"]["command"] = trigger
    with pytest.raises(ValidationError):
        Config.model_validate(d)


def test_bad_mouse_button():
    d = _data()
    d["triggers"]["dictation"] = {"mouse_button": "left"}
    with pytest.raises(ValidationError):
        Config.model_validate(d)


@pytest.mark.parametrize("phrases", [[], [""]])
def test_empty_phrases(phrases):
    d = _data()
    d["commands"][0]["phrases"] = phrases
    with pytest.raises(ValidationError):
        Config.model_validate(d)


def test_unknown_action_type():
    d = _data()
    d["commands"][0]["action"] = {"type": "teleport", "target": "x"}
    with pytest.raises(ValidationError):
        Config.model_validate(d)


def test_shell_without_command():
    d = _data()
    d["commands"][1]["action"] = {"type": "shell", "timeout": 5}
    with pytest.raises(ValidationError):
        Config.model_validate(d)


def test_shell_single_command_ok():
    d = _data()
    d["commands"][1]["action"] = {"type": "shell", "command": "ls"}
    Config.model_validate(d)


def test_duplicate_names():
    d = _data()
    d["commands"][1]["name"] = d["commands"][0]["name"]
    with pytest.raises(ValidationError, match="duplicato"):
        Config.model_validate(d)


def test_unknown_fields_rejected():
    d = _data()
    d["bogus"] = 1
    with pytest.raises(ValidationError):
        Config.model_validate(d)
    d = _data()
    d["commands"][0]["action"]["extra"] = 1
    with pytest.raises(ValidationError):
        Config.model_validate(d)


def test_stt_defaults_are_auto():
    stt = Config().stt
    assert (stt.device, stt.model, stt.compute_type) == ("auto", "auto", "auto")


def test_stt_device_rejects_unknown():
    with pytest.raises(ValidationError):
        Config.model_validate({"stt": {"device": "cuda"}})


def test_stt_vad_filter_default_on():
    assert Config().stt.vad_filter is True
