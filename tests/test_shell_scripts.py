"""The bash wrappers, run for real: interpreter discovery and curl's TLS flags.

Stub `python`/`curl` executables keep this offline — no cluster, no token. On
macOS it runs under /bin/bash 3.2, the oldest bash the scripts must support.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _find_bash():
    if sys.platform == "darwin":
        return "/bin/bash"                     # Apple's 3.2, not Homebrew's
    if os.name != "nt":
        return shutil.which("bash")
    # Git Bash: the bash.exe on a Windows PATH is often WSL's, which cannot run these.
    git = shutil.which("git")
    for d in Path(git).resolve().parents if git else ():
        if (d / "usr" / "bin" / "bash.exe").is_file():
            return str(d / "usr" / "bin" / "bash.exe")
    return None


BASH = _find_bash()
pytestmark = pytest.mark.skipif(not BASH, reason="needs bash (Git Bash on Windows)")


def _stub(path, body):
    path.write_bytes(("#!/bin/sh\n" + body + "\n").encode())   # LF, even on Windows
    path.chmod(0o755)


@pytest.fixture
def bin_dir(tmp_path):
    """python3: the real interpreter, but with a canned token and deployment.
    curl: records its arguments and answers like the chat endpoint."""
    d = tmp_path / "bin"
    d.mkdir()
    _stub(d / "python3",
          'case "$2" in token) echo fake-token ;; resolve-deployment) echo dep-1 ;;\n'
          f'  *) exec "{Path(sys.executable).as_posix()}" "$@" ;; esac')
    _stub(d / "curl", f'printf "%s\\n" "$@" > "{(tmp_path / "curl.args").as_posix()}"\n'
                      """echo '{"choices": [{"message": {"content": "hi"}}]}'""")
    return d


def run(script, bin_dir, *args, **env):
    # Stubs first, then bash's own directory for dirname & co., as Git Bash has.
    path = os.pathsep.join([str(bin_dir), str(Path(BASH).parent), os.environ["PATH"]])
    env = dict(os.environ, PATH=path, **env)
    return subprocess.run([BASH, (SCRIPTS / script).as_posix(), *args], env=env,
                          capture_output=True, encoding="utf-8", errors="replace")


# Each discovery test defines both python3 and python in bin_dir, so a real
# interpreter elsewhere on PATH can never be picked up by mistake.

def test_a_broken_python3_falls_back_to_python(bin_dir):
    (bin_dir / "python3").rename(bin_dir / "python")
    _stub(bin_dir / "python3", "exit 1")       # e.g. the Windows Store alias stub
    r = run("cpd_token.sh", bin_dir)
    assert r.stdout.strip() == "fake-token", r.stderr


def test_cpd_python_overrides_discovery(bin_dir):
    (bin_dir / "python3").rename(bin_dir / "chosen")
    _stub(bin_dir / "python3", "exit 1")
    _stub(bin_dir / "python", "exit 1")
    r = run("cpd_token.sh", bin_dir, CPD_PYTHON=(bin_dir / "chosen").as_posix())
    assert r.stdout.strip() == "fake-token", r.stderr


def test_no_usable_python_fails_with_a_hint(bin_dir):
    _stub(bin_dir / "python3", "exit 1")
    _stub(bin_dir / "python", "exit 1")        # e.g. Python 2, or 3.7
    r = run("cpd_token.sh", bin_dir)
    assert r.returncode == 1
    assert "CPD_PYTHON" in r.stderr


def _curl_args(tmp_path, bin_dir):
    r = run("wx_chat.sh", bin_dir, "hello")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "hi"
    return (tmp_path / "curl.args").read_text(encoding="utf-8").splitlines()


def test_chat_verifies_against_the_configured_ca_bundle(config_file, tmp_path, bin_dir):
    bundle = tmp_path / "private ca.pem"       # the space must not split the argument
    bundle.write_text("placeholder", encoding="utf-8")
    config_file(url="https://cluster.invalid", verify_ssl=True, ca_bundle=str(bundle))
    args = _curl_args(tmp_path, bin_dir)
    assert args[args.index("--cacert") + 1] == str(bundle)
    assert "-k" not in args


def test_chat_without_a_bundle_verifies_against_the_system_cas(config_file, tmp_path, bin_dir):
    config_file(url="https://cluster.invalid", verify_ssl=True)
    args = _curl_args(tmp_path, bin_dir)
    assert "-k" not in args and "--cacert" not in args


def test_chat_skips_verification_and_the_bundle_when_off(config_file, tmp_path, bin_dir):
    config_file(url="https://cluster.invalid", verify_ssl=False, ca_bundle="unused.pem")
    args = _curl_args(tmp_path, bin_dir)
    assert "-k" in args and "--cacert" not in args
