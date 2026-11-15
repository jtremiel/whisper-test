"""Test dell'azione dettatura con clipboard, tastiera e orologio finti."""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from voicecmd.actions import dictation
from voicecmd.actions.dictation import PynputKeyboard, paste_modifier, paste_text


class FakeClipboard:
    def __init__(self, log: list, content: str = "vecchio", fail_paste: bool = False) -> None:
        self.log = log
        self.content = content
        self.fail_paste = fail_paste

    def paste(self) -> str:
        self.log.append(("save", self.content))
        if self.fail_paste:
            raise RuntimeError("clipboard non leggibile")
        return self.content

    def copy(self, text: str) -> None:
        self.log.append(("copy", text))
        self.content = text


class FakeKeyboard:
    def __init__(self, log: list, fail: bool = False) -> None:
        self.log = log
        self.fail = fail

    def send_shortcut(self, modifier: str, key: str) -> None:
        self.log.append(("shortcut", modifier, key))
        if self.fail:
            raise RuntimeError("tastiera rotta")


class FakeClock:
    """Orologio finto: `sleep` fa avanzare il tempo senza attendere."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.now += s


def _run(text="ciao è così", *, log=None, clip=None, kb=None, **kw):
    log = [] if log is None else log
    clock = FakeClock()
    clip = clip or FakeClipboard(log)
    kb = kb or FakeKeyboard(log)
    kw.setdefault("platform", "darwin")
    res = paste_text(text, clipboard=clip, keyboard=kb, sleep=clock.sleep, clock=clock, **kw)
    return res, log, clip, clock


def test_sequence_save_copy_paste_restore():
    res, log, clip, _ = _run()
    assert res.ok
    assert log == [
        ("save", "vecchio"),
        ("copy", "ciao è così"),
        ("shortcut", "cmd", "v"),
        ("copy", "vecchio"),
    ]
    assert clip.content == "vecchio"


@pytest.mark.parametrize("platform,mod", [("darwin", "cmd"), ("win32", "ctrl")])
def test_shortcut_per_platform(platform, mod):
    res, log, _, _ = _run(platform=platform)
    assert ("shortcut", mod, "v") in log
    assert paste_modifier(platform) == mod


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_text_does_nothing(text):
    res, log, _, _ = _run(text)
    assert not res.ok
    assert log == []


def test_waits_for_keys_released():
    log: list = []
    calls = {"n": 0}

    def keys_released() -> bool:
        calls["n"] += 1
        log.append(("check", calls["n"]))
        return calls["n"] >= 3

    res, log, _, _ = _run(log=log, keys_released=keys_released)
    assert res.ok
    # i controlli avvengono tutti prima di toccare la clipboard
    assert log[:3] == [("check", 1), ("check", 2), ("check", 3)]
    assert log[3] == ("save", "vecchio")


def test_release_timeout_aborts_without_touching_clipboard():
    res, log, clip, clock = _run(keys_released=lambda: False, release_timeout=0.5)
    assert not res.ok
    assert "premuti" in res.message
    assert log == []
    assert clip.content == "vecchio"
    assert 0.5 <= clock.now < 0.6


def test_clipboard_restored_when_paste_raises():
    log: list = []
    res, log, clip, _ = _run(log=log, kb=FakeKeyboard(log, fail=True))
    assert not res.ok
    assert log[-1] == ("copy", "vecchio")
    assert clip.content == "vecchio"


def test_unreadable_clipboard_still_pastes():
    log: list = []
    clip = FakeClipboard(log, fail_paste=True)
    res, log, _, _ = _run(log=log, clip=clip)
    assert res.ok
    assert ("shortcut", "cmd", "v") in log
    assert log[-1] == ("shortcut", "cmd", "v")  # niente da ripristinare


def test_restore_delay_respected():
    res, _, _, clock = _run(restore_delay=0.3)
    assert res.ok
    assert clock.now >= 0.3


def test_pynput_keyboard_adapter_uses_modifier():
    log: list = []

    class FakeKey:
        cmd = "KEY_CMD"
        ctrl = "KEY_CTRL"

    class FakeController:
        @contextmanager
        def pressed(self, *keys):
            log.append(("down", keys))
            try:
                yield
            finally:
                log.append(("up", keys))

        def tap(self, key):
            log.append(("tap", key))

    PynputKeyboard(FakeController(), FakeKey).send_shortcut("ctrl", "v")
    assert log == [("down", ("KEY_CTRL",)), ("tap", "v"), ("up", ("KEY_CTRL",))]


def test_module_import_has_no_side_effects():
    assert "pyperclip" not in vars(dictation)
    assert "pynput" not in vars(dictation)
