"""Test del trigger da tastiera: si alimentano direttamente i gestori, nessun listener reale."""
from __future__ import annotations

import pytest
from pynput.keyboard import Key, KeyCode

from voicecmd.events import Mode, Trigger
from voicecmd.triggers.hotkey import HotkeyError, HotkeyTrigger, parse_hotkey


class FakeListener:
    def __init__(self, on_press, on_release):
        self.on_press = on_press
        self.on_release = on_release
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def make(hotkeys):
    events: list[tuple[Mode, bool]] = []
    holder: dict = {}

    def factory(**kw):
        holder["l"] = FakeListener(**kw)
        return holder["l"]

    trig = HotkeyTrigger(hotkeys, listener_factory=factory)
    trig.start(lambda m, p: events.append((m, p)))
    return trig, events, holder["l"]


DEFAULT = {Mode.COMMAND: "<ctrl>+<alt>+space"}


def test_satisfies_protocol_and_uses_listener():
    trig, _, listener = make(DEFAULT)
    assert isinstance(trig, Trigger)
    assert listener.started
    assert listener.on_press == trig.handle_press
    trig.stop()
    assert listener.stopped


def test_full_combo_emits_single_press():
    trig, events, _ = make(DEFAULT)
    trig.handle_press(Key.ctrl)
    trig.handle_press(Key.alt)
    assert events == []
    trig.handle_press(Key.space)
    assert events == [(Mode.COMMAND, True)]


def test_autorepeat_emits_nothing_more():
    trig, events, _ = make(DEFAULT)
    for k in (Key.ctrl, Key.alt, Key.space):
        trig.handle_press(k)
    for _ in range(5):
        trig.handle_press(Key.space)
        trig.handle_press(Key.alt)
    assert events == [(Mode.COMMAND, True)]


def test_release_of_any_key_emits_release_once():
    trig, events, _ = make(DEFAULT)
    for k in (Key.ctrl, Key.alt, Key.space):
        trig.handle_press(k)
    trig.handle_release(Key.alt)
    assert events == [(Mode.COMMAND, True), (Mode.COMMAND, False)]
    trig.handle_release(Key.space)
    trig.handle_release(Key.ctrl)
    assert events == [(Mode.COMMAND, True), (Mode.COMMAND, False)]


def test_repress_after_release_fires_again():
    trig, events, _ = make(DEFAULT)
    for k in (Key.ctrl, Key.alt, Key.space):
        trig.handle_press(k)
    trig.handle_release(Key.space)
    trig.handle_press(Key.space)
    assert events == [(Mode.COMMAND, True), (Mode.COMMAND, False), (Mode.COMMAND, True)]


@pytest.mark.parametrize("ctrl", [Key.ctrl, Key.ctrl_l, Key.ctrl_r])
@pytest.mark.parametrize("alt", [Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr])
def test_generic_modifiers_accept_both_sides(ctrl, alt):
    trig, events, _ = make(DEFAULT)
    trig.handle_press(alt)
    trig.handle_press(ctrl)
    trig.handle_press(Key.space)
    assert events == [(Mode.COMMAND, True)]
    trig.handle_release(ctrl)
    assert events[-1] == (Mode.COMMAND, False)


def test_both_sides_held_release_one_keeps_active():
    trig, events, _ = make(DEFAULT)
    for k in (Key.ctrl_l, Key.ctrl_r, Key.alt, Key.space):
        trig.handle_press(k)
    trig.handle_release(Key.ctrl_r)
    assert events == [(Mode.COMMAND, True)]
    trig.handle_release(Key.ctrl_l)
    assert events == [(Mode.COMMAND, True), (Mode.COMMAND, False)]


def test_side_specific_modifier_only_matches_that_side():
    trig, events, _ = make({Mode.DICTATION: "<ctrl_r>"})
    trig.handle_press(Key.ctrl_l)
    trig.handle_release(Key.ctrl_l)
    assert events == []
    trig.handle_press(Key.ctrl_r)
    trig.handle_release(Key.ctrl_r)
    assert events == [(Mode.DICTATION, True), (Mode.DICTATION, False)]


def test_single_modifier_and_single_key():
    trig, events, _ = make({Mode.COMMAND: "<alt>", Mode.DICTATION: "<f13>"})
    trig.handle_press(Key.alt_r)
    trig.handle_release(Key.alt_r)
    trig.handle_press(Key.f13)
    trig.handle_release(Key.f13)
    assert events == [
        (Mode.COMMAND, True), (Mode.COMMAND, False),
        (Mode.DICTATION, True), (Mode.DICTATION, False),
    ]


def test_char_key_combo_with_changed_char_on_release():
    trig, events, _ = make({Mode.COMMAND: "<cmd>+<shift>+k"})
    trig.handle_press(Key.cmd)
    trig.handle_press(Key.shift)
    trig.handle_press(KeyCode(vk=40, char="K"))
    assert events == [(Mode.COMMAND, True)]
    trig.handle_release(KeyCode(vk=40, char="k"))
    assert events == [(Mode.COMMAND, True), (Mode.COMMAND, False)]


def test_two_modes_do_not_mix():
    trig, events, _ = make({Mode.COMMAND: "<ctrl>+<alt>+space", Mode.DICTATION: "<ctrl>+<shift>+d"})
    trig.handle_press(Key.ctrl)
    trig.handle_press(Key.shift)
    trig.handle_press(Key.space)
    assert events == []
    trig.handle_press(KeyCode.from_char("d"))
    assert events == [(Mode.DICTATION, True)]
    trig.handle_release(Key.shift)
    assert events == [(Mode.DICTATION, True), (Mode.DICTATION, False)]
    trig.handle_press(Key.alt)  # ctrl e space ancora giù, ma il tasto nuovo completa command
    assert events[-1] == (Mode.COMMAND, True)


def test_overlapping_combos_longest_wins_and_no_second_activation():
    trig, events, _ = make({Mode.COMMAND: "<ctrl>+<alt>+space", Mode.DICTATION: "<alt>+space"})
    trig.handle_press(Key.ctrl)
    trig.handle_press(Key.alt)
    trig.handle_press(Key.space)
    assert events == [(Mode.COMMAND, True)]
    trig.handle_release(Key.ctrl)
    assert events == [(Mode.COMMAND, True), (Mode.COMMAND, False)]


def test_while_active_other_mode_ignored():
    trig, events, _ = make({Mode.COMMAND: "<alt>+space", Mode.DICTATION: "<f13>"})
    trig.handle_press(Key.alt)
    trig.handle_press(Key.space)
    trig.handle_press(Key.f13)
    assert events == [(Mode.COMMAND, True)]


def test_injected_and_none_keys_ignored():
    trig, events, _ = make({Mode.COMMAND: "<cmd>"})
    trig.handle_press(Key.cmd, True)
    trig.handle_press(None)
    trig.handle_release(None)
    assert events == []
    assert trig.keys_released()


def test_keys_released():
    trig, _, _ = make(DEFAULT)
    assert trig.keys_released()
    trig.handle_press(KeyCode.from_char("x"))  # tasto estraneo
    assert trig.keys_released()
    trig.handle_press(Key.alt_r)
    assert not trig.keys_released()
    trig.handle_release(Key.alt_r)
    assert trig.keys_released()


def test_stop_clears_state():
    trig, events, _ = make(DEFAULT)
    trig.handle_press(Key.ctrl)
    trig.stop()
    assert trig.keys_released()


def test_callback_exception_does_not_propagate():
    trig = HotkeyTrigger({Mode.COMMAND: "<f13>"}, listener_factory=FakeListener)

    def boom(mode, pressed):
        raise RuntimeError("x")

    trig.start(boom)
    trig.handle_press(Key.f13)  # non solleva
    trig.handle_release(Key.f13)


def test_parse_formats():
    assert parse_hotkey("<ctrl>+<alt>+space") == parse_hotkey("<ctrl>+<alt>+<space>")
    assert parse_hotkey(" <CTRL> + A ") == frozenset({("mod", "ctrl"), ("char", "a")})
    assert parse_hotkey("<alt_l>") == frozenset({("side", "alt_l")})
    assert parse_hotkey("<65>") == frozenset({("vk", 65)})
    assert ("char", "+") in parse_hotkey("<ctrl>++")


@pytest.mark.parametrize("bad", ["", "   ", "<ctrl>+", "+a", "<ctrl>+<pippo>", "spazio",
                                 "<ctrl>+<ctrl>", "<>", "ab"])
def test_invalid_hotkey_clear_error(bad):
    with pytest.raises(HotkeyError) as exc:
        HotkeyTrigger({Mode.COMMAND: bad})
    msg = str(exc.value)
    assert "command" in msg.lower() or "vuota" in msg.lower()


def test_unknown_key_message_names_the_key():
    with pytest.raises(HotkeyError, match="pippo"):
        HotkeyTrigger({Mode.COMMAND: "<ctrl>+<pippo>"})


def test_same_hotkey_for_two_modes_rejected():
    with pytest.raises(HotkeyError, match="stessa hotkey"):
        HotkeyTrigger({Mode.COMMAND: "<ctrl>+a", Mode.DICTATION: "a+<ctrl>"})


def test_hotkey_error_is_value_error():
    assert issubclass(HotkeyError, ValueError)


def test_untrusted_listener_raises_and_stops():
    created = {}

    class Untrusted(FakeListener):
        IS_TRUSTED = False

        def wait(self):
            self.waited = True

    def factory(**kw):
        created["l"] = Untrusted(**kw)
        return created["l"]

    trig = HotkeyTrigger(DEFAULT, listener_factory=factory)
    with pytest.raises(RuntimeError, match="Monitoraggio input"):
        trig.start(lambda m, p: None)
    assert created["l"].waited and created["l"].stopped


def test_trusted_listener_starts():
    class Trusted(FakeListener):
        IS_TRUSTED = True

        def wait(self):
            pass

    trig = HotkeyTrigger(DEFAULT, listener_factory=Trusted)
    trig.start(lambda m, p: None)
    trig.stop()
