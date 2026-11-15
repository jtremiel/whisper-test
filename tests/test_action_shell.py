"""Test dell'azione shell con comandi reali e innocui."""
from __future__ import annotations

import sys
import time

import pytest

from voicecmd.actions.shell import ShellActionRunner, select_command
from voicecmd.events import Action, ActionResult
from voicecmd.schema import ShellAction

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="comandi POSIX")


def spec(**kw) -> ShellAction:
    return ShellAction(type="shell", **kw)


def test_satisfies_action_protocol() -> None:
    assert isinstance(ShellActionRunner(), Action)


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("darwin", "M"), ("win32", "W"), ("linux", "C")],
)
def test_select_prefers_platform_variant(platform: str, expected: str) -> None:
    s = spec(command="C", mac="M", windows="W")
    assert select_command(s, platform) == expected


def test_select_falls_back_to_command() -> None:
    s = spec(command="C", windows="W")
    assert select_command(s, "darwin") == "C"


def test_missing_variant_for_platform() -> None:
    s = spec(windows="echo solo windows")
    res = ShellActionRunner(platform="darwin").run(s)
    assert isinstance(res, ActionResult)
    assert res.ok is False
    assert "sistema" in res.message


def test_success() -> None:
    res = ShellActionRunner().run(spec(command="echo ciao"))
    assert res.ok is True
    assert "ciao" in res.message


@posix_only
def test_success_with_platform_variant_on_current_system() -> None:
    s = spec(mac="echo mac", command="echo generico", windows="echo win")
    res = ShellActionRunner().run(s)
    assert res.ok is True
    expected = "mac" if sys.platform == "darwin" else "generico"
    assert expected in res.message


@posix_only
def test_nonzero_exit_reports_code_and_stderr() -> None:
    cmd = "echo riga1 >&2; echo riga2 >&2; exit 3"
    res = ShellActionRunner().run(spec(command=cmd))
    assert res.ok is False
    assert "3" in res.message
    assert "riga2" in res.message


def test_exit_1() -> None:
    res = ShellActionRunner().run(spec(command="exit 1"))
    assert res.ok is False
    assert "1" in res.message


@posix_only
def test_stderr_tail_is_truncated() -> None:
    cmd = "for i in 1 2 3 4 5 6 7 8 9; do echo err$i >&2; done; exit 2"
    res = ShellActionRunner().run(spec(command=cmd))
    assert res.ok is False
    assert "err9" in res.message
    assert "err1\n" not in res.message + "\n"  # le prime righe sono tagliate


def test_unknown_command_fails() -> None:
    res = ShellActionRunner().run(spec(command="comando_inesistente_voicecmd_xyz"))
    assert res.ok is False


@posix_only
@pytest.mark.parametrize("cmd", ["sleep 5", "sleep 5; echo fine"])
def test_timeout_kills_command(cmd: str) -> None:
    t0 = time.monotonic()
    res = ShellActionRunner().run(spec(command=cmd, timeout=0.3))
    elapsed = time.monotonic() - t0
    assert res.ok is False
    assert "Tempo scaduto" in res.message
    assert elapsed < 3, f"il timeout non ha interrotto il comando ({elapsed:.1f} s)"
