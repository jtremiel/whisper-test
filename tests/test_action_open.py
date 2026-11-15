"""Test dell'azione `open`: subprocess, webbrowser e os.startfile sono sostituiti."""
import subprocess

import pytest

from voicecmd.actions import open as open_mod
from voicecmd.actions.open import OpenActionRunner, is_url
from voicecmd.events import Action
from voicecmd.schema import OpenAction


class Calls:
    """Registra le chiamate ai finti subprocess.run, webbrowser.open e os.startfile."""

    def __init__(self) -> None:
        self.run: list[list[str]] = []
        self.browser: list[str] = []
        self.startfile: list[str] = []
        self.returncode = 0
        self.stderr = ""
        self.browser_ok = True
        self.startfile_exc: Exception | None = None


@pytest.fixture
def calls(monkeypatch):
    c = Calls()

    def fake_run(args, **kwargs):
        c.run.append(list(args))
        return subprocess.CompletedProcess(args, c.returncode, stdout="", stderr=c.stderr)

    def fake_browser(url, *a, **k):
        c.browser.append(url)
        return c.browser_ok

    def fake_startfile(path, *a, **k):
        c.startfile.append(path)
        if c.startfile_exc:
            raise c.startfile_exc

    monkeypatch.setattr(open_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(open_mod.webbrowser, "open", fake_browser)
    monkeypatch.setattr(open_mod.os, "startfile", fake_startfile, raising=False)
    return c


def run(target: str):
    return OpenActionRunner().run(OpenAction(type="open", target=target))


def set_platform(monkeypatch, name: str) -> None:
    monkeypatch.setattr(open_mod.sys, "platform", name)


PLATFORMS = ["darwin", "win32"]


def test_satisfies_action_protocol():
    assert isinstance(OpenActionRunner(), Action)


@pytest.mark.parametrize(
    "target,expected",
    [
        ("https://www.google.com", True),
        ("http://example.org/a?b=1", True),
        ("mailto:a@b.it", True),
        ("C:\\Users\\me\\file.txt", False),
        ("/Applications/Safari.app", False),
        ("Safari", False),
    ],
)
def test_is_url(target, expected):
    assert is_url(target) is expected


@pytest.mark.parametrize("platform", PLATFORMS)
def test_url_goes_to_browser(monkeypatch, calls, platform):
    set_platform(monkeypatch, platform)
    res = run("https://www.google.com")
    assert res.ok
    assert calls.browser == ["https://www.google.com"]
    assert calls.run == [] and calls.startfile == []


@pytest.mark.parametrize("platform", PLATFORMS)
def test_url_browser_failure(monkeypatch, calls, platform):
    set_platform(monkeypatch, platform)
    calls.browser_ok = False
    res = run("https://www.google.com")
    assert not res.ok
    assert "URL" in res.message


def test_mac_existing_file(monkeypatch, calls, tmp_path):
    set_platform(monkeypatch, "darwin")
    f = tmp_path / "doc.txt"
    f.write_text("x")
    res = run(str(f))
    assert res.ok
    assert calls.run == [["open", str(f)]]


def test_mac_existing_folder(monkeypatch, calls, tmp_path):
    set_platform(monkeypatch, "darwin")
    res = run(str(tmp_path))
    assert res.ok
    assert calls.run == [["open", str(tmp_path)]]


def test_mac_app_name(monkeypatch, calls):
    set_platform(monkeypatch, "darwin")
    res = run("Safari")
    assert res.ok
    assert calls.run == [["open", "-a", "Safari"]]


def test_mac_app_not_found(monkeypatch, calls):
    set_platform(monkeypatch, "darwin")
    calls.returncode = 1
    calls.stderr = "Unable to find application named 'Pippo'\n"
    res = run("Pippo")
    assert not res.ok
    assert "Pippo" in res.message
    assert "Unable to find application" in res.message


def test_mac_open_timeout_becomes_error(monkeypatch, calls):
    set_platform(monkeypatch, "darwin")

    def boom(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 10)

    monkeypatch.setattr(open_mod.subprocess, "run", boom)
    res = run("Safari")
    assert not res.ok
    assert "Safari" in res.message


def test_windows_existing_file(monkeypatch, calls, tmp_path):
    set_platform(monkeypatch, "win32")
    f = tmp_path / "doc.txt"
    f.write_text("x")
    res = run(str(f))
    assert res.ok
    assert calls.startfile == [str(f)]
    assert calls.run == []


def test_windows_app_name(monkeypatch, calls):
    set_platform(monkeypatch, "win32")
    res = run("notepad")
    assert res.ok
    assert calls.startfile == ["notepad"]


def test_windows_startfile_error(monkeypatch, calls):
    set_platform(monkeypatch, "win32")
    calls.startfile_exc = FileNotFoundError(2, "Impossibile trovare il file specificato")
    res = run("pippo")
    assert not res.ok
    assert "pippo" in res.message
    assert "Impossibile trovare" in res.message


@pytest.mark.parametrize("platform", PLATFORMS)
def test_missing_path_is_error_without_calls(monkeypatch, calls, tmp_path, platform):
    set_platform(monkeypatch, platform)
    missing = tmp_path / "non-esiste.txt"
    res = run(str(missing))
    assert not res.ok
    assert "non esiste" in res.message
    assert calls.run == [] and calls.startfile == [] and calls.browser == []


@pytest.mark.parametrize("platform", PLATFORMS)
def test_tilde_expansion(monkeypatch, calls, tmp_path, platform):
    set_platform(monkeypatch, platform)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "note.txt").write_text("x")
    res = run("~/note.txt")
    assert res.ok
    expected = str(tmp_path / "note.txt")
    assert (calls.run == [["open", expected]]) if platform == "darwin" else (calls.startfile == [expected])


@pytest.mark.parametrize("platform", PLATFORMS)
def test_env_var_expansion(monkeypatch, calls, tmp_path, platform):
    set_platform(monkeypatch, platform)
    monkeypatch.setenv("VOICECMD_TEST_DIR", str(tmp_path))
    res = run("$VOICECMD_TEST_DIR")
    assert res.ok
    assert (calls.run == [["open", str(tmp_path)]]) if platform == "darwin" else (
        calls.startfile == [str(tmp_path)]
    )


def test_unexpected_exception_becomes_error(monkeypatch, calls):
    set_platform(monkeypatch, "darwin")

    def boom(*a, **k):
        raise RuntimeError("guasto")

    monkeypatch.setattr(open_mod.webbrowser, "open", boom)
    res = run("https://www.google.com")
    assert not res.ok
    assert "guasto" in res.message
