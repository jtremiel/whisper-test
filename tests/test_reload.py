"""Test della ricarica della configurazione (T22): watcher reale su file temporanei."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from voicecmd.app import VoiceCmdApp, restart_required
from voicecmd.events import AppState, Mode
from voicecmd.schema import Config

from tests.test_app import CONFIG_YAML, Env

DEBOUNCE_MS = 50


def make(qtbot, tmp_path, **kw):
    env = Env(tmp_path, **kw)
    created = {"hk": [], "mouse": []}
    hk_factory, mouse_factory = env.factories.hotkey_trigger, env.factories.mouse_trigger

    def hk(m):
        t = hk_factory(m)
        created["hk"].append(t)
        return t

    def mouse(m):
        t = mouse_factory(m)
        created["mouse"].append(t)
        return t

    env.factories.hotkey_trigger, env.factories.mouse_trigger = hk, mouse
    app = VoiceCmdApp(env.cfg_path, env.factories, reload_debounce_ms=DEBOUNCE_MS)
    qtbot.waitUntil(lambda: app.controller is not None, timeout=3000)
    env.created = created
    return env, app


def titles(env):
    return [m[0] for m in env.notifier.messages]


def test_valid_edit_applied(qtbot, tmp_path):
    env, app = make(qtbot, tmp_path)
    env.cfg_path.write_text(CONFIG_YAML + "matching: {threshold: 70}\n", encoding="utf-8")
    qtbot.waitUntil(lambda: app.config.matching.threshold == 70, timeout=3000)
    assert app.controller.config.matching.threshold == 70
    assert env.notifier.messages[-1] == ("Configurazione ricaricata", "Le modifiche sono attive.", False)
    assert len(env.created["hk"]) == 1  # binding invariati: trigger non riavviati
    app.shutdown()


def test_invalid_edit_rejected_and_config_kept(qtbot, tmp_path):
    env, app = make(qtbot, tmp_path)
    before = app.config
    env.cfg_path.write_text(CONFIG_YAML + "matching: {threshold: 500}\n", encoding="utf-8")
    qtbot.waitUntil(lambda: "Configurazione non valida" in titles(env), timeout=3000)
    title, text, error = env.notifier.messages[-1]
    assert "matching.threshold" in text and "precedente" in text and error
    assert app.config is before and app.controller.config is before
    app.shutdown()


def test_replaced_file_still_watched(qtbot, tmp_path):
    env, app = make(qtbot, tmp_path)
    # come vim/VS Code: si scrive un file nuovo e lo si rinomina sopra l'originale, due volte
    for threshold in (70, 60):
        tmp = tmp_path / "config.yaml.tmp"
        tmp.write_text(CONFIG_YAML + f"matching: {{threshold: {threshold}}}\n", encoding="utf-8")
        os.replace(tmp, env.cfg_path)
        qtbot.waitUntil(lambda: app.config.matching.threshold == threshold, timeout=3000)
    assert str(env.cfg_path) in app.watcher.files()
    app.shutdown()


def test_unchanged_content_and_other_files_ignored(qtbot, tmp_path):
    env, app = make(qtbot, tmp_path)
    n = len(env.notifier.messages)
    (tmp_path / "altro.txt").write_text("x", encoding="utf-8")
    env.cfg_path.write_text(env.cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
    qtbot.wait(DEBOUNCE_MS * 6)
    assert len(env.notifier.messages) == n
    app.shutdown()


def test_burst_of_writes_reloads_once(qtbot, tmp_path):
    env, app = make(qtbot, tmp_path)
    for t in (71, 72, 73):
        env.cfg_path.write_text(CONFIG_YAML + f"matching: {{threshold: {t}}}\n", encoding="utf-8")
    qtbot.waitUntil(lambda: app.config.matching.threshold == 73, timeout=3000)
    qtbot.wait(DEBOUNCE_MS * 4)
    assert titles(env).count("Configurazione ricaricata") == 1
    app.shutdown()


SWAPPED = CONFIG_YAML.replace(
    '  command:\n    hotkey: "<ctrl>+<alt>+space"\n  dictation:\n    mouse_button: x2\n',
    '  command:\n    mouse_button: x2\n  dictation:\n    hotkey: "<ctrl>+<alt>+space"\n',
)


def test_binding_change_restarts_triggers(qtbot, tmp_path):
    env, app = make(qtbot, tmp_path)
    old_hk, old_mouse = env.created["hk"][0], env.created["mouse"][0]
    env.cfg_path.write_text(SWAPPED, encoding="utf-8")
    qtbot.waitUntil(lambda: len(env.created["hk"]) == 2, timeout=3000)
    assert old_hk.stopped and old_mouse.stopped
    new_hk, new_mouse = env.created["hk"][1], env.created["mouse"][1]
    assert new_hk.mapping == {Mode.DICTATION: "<ctrl>+<alt>+space"}
    assert new_mouse.mapping == {Mode.COMMAND: "x2"}
    assert app.triggers == [new_hk, new_mouse]
    assert new_hk.on_event is not None and new_mouse.on_event is not None
    # il trigger nuovo comanda davvero il controller
    clock = [0.0]
    app.controller._clock = lambda: clock[0]
    new_mouse.on_event(Mode.COMMAND, True)
    clock[0] += 1.0
    new_mouse.on_event(Mode.COMMAND, False)
    qtbot.waitUntil(lambda: len(env.open.specs) == 1, timeout=3000)
    app.shutdown()


def test_binding_change_during_cycle_waits_for_idle(qtbot, tmp_path):
    env, app = make(qtbot, tmp_path)
    clock = [0.0]
    app.controller._clock = lambda: clock[0]
    env.hk.on_event(Mode.COMMAND, True)  # in ascolto
    assert app.controller.state is AppState.LISTENING
    env.cfg_path.write_text(SWAPPED, encoding="utf-8")
    qtbot.waitUntil(lambda: "Configurazione ricaricata" in titles(env), timeout=3000)
    assert len(env.created["hk"]) == 1 and not env.hk.stopped  # rilascio non perso
    clock[0] += 1.0
    env.created["hk"][0].on_event(Mode.COMMAND, False)
    qtbot.waitUntil(lambda: len(env.created["hk"]) == 2, timeout=3000)
    assert env.created["hk"][0].stopped
    assert len(env.open.specs) == 1  # il ciclo in corso ha usato la config vecchia
    app.shutdown()


def test_stt_change_asks_restart(qtbot, tmp_path):
    env, app = make(qtbot, tmp_path)
    env.cfg_path.write_text(CONFIG_YAML + "stt: {model: small}\nlanguage: en\n", encoding="utf-8")
    qtbot.waitUntil(lambda: "Configurazione ricaricata" in titles(env), timeout=3000)
    title, text, warn = env.notifier.messages[-1]
    assert "Riavvia voicecmd" in text and "stt.model" in text and "language" in text and warn
    app.shutdown()


def test_menu_reload_uses_same_path(qtbot, tmp_path):
    env, app = make(qtbot, tmp_path)
    env.tray.reload_config_requested.emit()  # anche senza modifiche
    assert env.notifier.messages[-1][0] == "Configurazione ricaricata"
    app.shutdown()


def test_no_reload_after_shutdown(qtbot, tmp_path):
    env, app = make(qtbot, tmp_path)
    app.shutdown()
    assert app.watcher.files() == [] and app.watcher.directories() == []
    env.cfg_path.write_text(CONFIG_YAML + "matching: {threshold: 70}\n", encoding="utf-8")
    qtbot.wait(DEBOUNCE_MS * 4)
    assert app.config.matching.threshold == 80


def test_restart_required_fields():
    base = Config()
    assert restart_required(base, base) == []
    new = Config.model_validate({"stt": {"device": "cpu", "compute_type": "int8"},
                                 "audio": {"preroll_ms": 100}, "matching": {"threshold": 50}})
    assert restart_required(base, new) == ["stt.device", "stt.compute_type", "audio.preroll_ms"]


def test_hotwords_change_needs_no_restart():
    base = Config()
    new = Config.model_validate({"stt": {"hotwords": False}})
    assert restart_required(base, new) == []
