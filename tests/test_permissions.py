"""Test di voicecmd.permissions con i controlli sostituiti."""
import sys

import pytest

from voicecmd import permissions as p


def _ok():
    return True


def _no():
    return False


def _boom():
    raise RuntimeError("API non disponibile")


ALL_OK = {p.MICROPHONE: _ok, p.ACCESSIBILITY: _ok, p.INPUT_MONITORING: _ok}


def test_windows_returns_empty_list():
    # anche con controlli che fallirebbero: su Windows non si controlla nulla
    checks = {p.MICROPHONE: _no, p.ACCESSIBILITY: _boom}
    assert p.check_permissions(platform="win32", checks=checks, executable="X") == []


def test_all_granted_returns_empty_list():
    assert p.check_permissions(platform="darwin", checks=ALL_OK, executable="X") == []


def test_missing_permissions_listed_with_text():
    checks = {p.MICROPHONE: _no, p.ACCESSIBILITY: _ok, p.INPUT_MONITORING: _no}
    missing = p.check_permissions(platform="darwin", checks=checks,
                                  executable="Visual Studio Code")
    assert [m.name for m in missing] == ["Microfono", "Monitoraggio input"]
    mic, listen = missing
    assert mic.status == p.DENIED
    assert mic.settings_path == "Impostazioni di Sistema > Privacy e sicurezza > Microfono"
    assert "Privacy_Microphone" in mic.settings_url
    assert listen.settings_path.endswith("Privacy e sicurezza > Monitoraggio input")
    assert "Privacy_ListenEvent" in listen.settings_url
    assert mic.executable == "Visual Studio Code"
    assert "registrare la voce" in mic.explanation
    assert mic.message.startswith("Manca il permesso 'Microfono'.")
    assert '"Visual Studio Code"' in mic.message
    assert "Privacy e sicurezza > Microfono" in mic.message


def test_accessibility_text():
    checks = {p.ACCESSIBILITY: _no}
    (ax,) = p.check_permissions(platform="darwin", checks=checks, executable="Terminal")
    assert ax.name == "Accessibilità"
    assert ax.settings_path.endswith("Privacy e sicurezza > Accessibilità")
    assert "incollare" in ax.explanation
    assert '"Terminal"' in ax.message


def test_exception_in_check_becomes_unknown():
    checks = {p.MICROPHONE: _boom, p.ACCESSIBILITY: _ok, p.INPUT_MONITORING: _no}
    missing = p.check_permissions(platform="darwin", checks=checks, executable="X")
    assert [(m.name, m.status) for m in missing] == [
        ("Microfono", p.UNKNOWN), ("Monitoraggio input", p.DENIED)]
    assert missing[0].message.startswith("Impossibile verificare il permesso 'Microfono'.")


def test_exception_in_executable_resolver_falls_back():
    def bad():
        raise OSError("libproc assente")

    (m,) = p.check_permissions(platform="darwin", checks={p.MICROPHONE: _no},
                               executable=bad)
    assert m.executable  # ripiego sull'interprete, nessuna eccezione


def test_executable_not_resolved_when_nothing_missing():
    def must_not_run():
        raise AssertionError("non deve essere chiamato")

    assert p.check_permissions(platform="darwin", checks=ALL_OK,
                               executable=must_not_run) == []


# --- quale eseguibile autorizzare ------------------------------------------

PY = ("/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/"
      "3.14/Resources/Python.app/Contents/MacOS/Python")
VSCODE = "/Applications/Visual Studio Code.app/Contents/MacOS/Code"
HELPER = ("/Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper.app/"
          "Contents/MacOS/Code Helper")
TERMINAL = "/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal"

# catena reale osservata su questo Mac: python -> zsh -> claude -> zsh -> Code Helper -> Code
VSCODE_TREE = {
    100: (90, PY), 90: (80, "/bin/zsh"), 80: (70, "claude"), 70: (60, "/bin/zsh"),
    60: (50, HELPER), 50: (1, VSCODE),
}
TERMINAL_TREE = {
    100: (90, PY), 90: (80, "/bin/zsh"), 80: (70, "/usr/bin/login"), 70: (1, TERMINAL),
}


def _resolver(tree, responsible=None):
    return dict(
        pid=100,
        proc_path=lambda pid: tree[pid][1] if pid in tree else None,
        parent_pid=lambda pid: tree[pid][0] if pid in tree else None,
        responsible_pid=lambda pid: responsible,
    )


def test_app_bundle():
    assert p.app_bundle(HELPER) == "/Applications/Visual Studio Code.app"
    assert p.app_bundle("/bin/zsh") is None
    assert p.app_bundle("/Applications/Foo.app") == "/Applications/Foo.app"


def test_executable_from_responsible_process():
    assert p.find_executable_to_authorize(**_resolver(VSCODE_TREE, responsible=50)) \
        == "Visual Studio Code"


@pytest.mark.parametrize("tree,expected", [
    (VSCODE_TREE, "Visual Studio Code"),
    (TERMINAL_TREE, "Terminal"),
])
def test_executable_from_parent_chain(tree, expected):
    assert p.find_executable_to_authorize(**_resolver(tree)) == expected


def test_responsible_failure_falls_back_to_chain():
    kw = _resolver(TERMINAL_TREE)

    def boom(pid):
        raise OSError("simbolo assente")

    kw["responsible_pid"] = boom
    assert p.find_executable_to_authorize(**kw) == "Terminal"


def test_no_app_in_chain_returns_interpreter():
    tree = {100: (90, PY), 90: (1, "/usr/sbin/sshd")}
    assert p.find_executable_to_authorize(**_resolver(tree)) == \
        __import__("os").path.realpath(sys.executable)


@pytest.mark.skipif(sys.platform != "darwin", reason="solo macOS")
def test_real_check_does_not_raise():
    # controllo reale: non deve sollevare né aprire dialoghi
    result = p.check_permissions()
    assert isinstance(result, list)
    assert all(isinstance(m, p.MissingPermission) for m in result)
    assert p.find_executable_to_authorize()
