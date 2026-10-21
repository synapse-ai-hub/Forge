"""Controlled installation of the libraries the tools need (no network)."""

import pytest

from backend.agent.utils import packages


@pytest.mark.parametrize("command,specs", [
    ("pip install requests", ["requests"]),
    ("python -m pip install httpx==0.28.1 -q", ["httpx==0.28.1"]),
    ("py -m pip install -U trafilatura", ["trafilatura"]),
    ("pip3 install a b[extra]>=1", ["a", "b[extra]>=1"]),
])
def test_pip_install_is_parsed(command, specs):
    assert packages.parse_pip_install(command) == (specs, "")


@pytest.mark.parametrize("command", [
    "pip install -r requirements.txt",
    "pip install x && rm -rf /",
    "pip install x | tee out.txt",
    "pip install git+https://example.com/x.git",
    "pip install ./local_dir",
    "pip install --target /tmp x",
    "pip install --index-url http://evil x",
    "pip install",
])
def test_unsafe_pip_install_is_rejected(command):
    specs, error = packages.parse_pip_install(command)
    assert specs == [] and error


@pytest.mark.parametrize("command", ["ls -la", "echo pip is great", "python script.py", "git clone x"])
def test_other_commands_are_not_pip(command):
    assert packages.parse_pip_install(command) is None


def test_install_rejects_invalid_spec_without_running_pip(monkeypatch):
    monkeypatch.setattr(packages, "_run_pip", lambda *a, **k: pytest.fail("pip must not run"))
    assert packages.install_package("git+https://example.com/x.git")["status"] == "error"


def test_install_records_in_tools_and_project_requirements(tmp_path, monkeypatch):
    class Done:
        returncode, stdout, stderr = 0, "ok", ""

    project = tmp_path / "requirements.txt"
    project.write_text("httpx>=0.28\n", encoding="utf-8")
    tools = tmp_path / "tools_requirements.txt"
    monkeypatch.setattr(packages, "project_requirements_file", lambda: project)
    monkeypatch.setattr(packages, "tools_requirements_file", lambda: tools)
    monkeypatch.setattr(packages, "_run_pip", lambda specs, extra=None: Done())
    monkeypatch.setattr(packages, "_installed_version", lambda name: "1.2.3")

    result = packages.install_package("trafilatura")

    assert result["status"] == "success"
    assert tools.read_text(encoding="utf-8").splitlines() == ["trafilatura==1.2.3"]
    assert project.read_text(encoding="utf-8").splitlines()[-1] == "trafilatura==1.2.3"
    # Installing it again does not duplicate the line.
    packages.install_package("trafilatura")
    assert tools.read_text(encoding="utf-8").splitlines() == ["trafilatura==1.2.3"]
    assert project.read_text(encoding="utf-8").count("trafilatura") == 1


def test_failed_install_records_nothing(tmp_path, monkeypatch):
    class Failed:
        returncode, stdout, stderr = 1, "", "conflict"

    tools = tmp_path / "tools_requirements.txt"
    monkeypatch.setattr(packages, "project_requirements_file", lambda: None)
    monkeypatch.setattr(packages, "tools_requirements_file", lambda: tools)
    monkeypatch.setattr(packages, "_run_pip", lambda specs, extra=None: Failed())

    assert packages.install_package("x")["status"] == "error"
    assert not tools.exists()


def test_restore_installs_only_the_missing(tmp_path, monkeypatch):
    tools = tmp_path / "tools_requirements.txt"
    tools.write_text("present==1.0\nmissing==2.0\n", encoding="utf-8")
    seen = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(packages, "tools_requirements_file", lambda: tools)
    monkeypatch.setattr(packages, "_installed_version", lambda name: "1.0" if name == "present" else None)
    monkeypatch.setattr(packages, "_run_pip", lambda specs, extra=None: seen.append(specs) or Done())

    assert packages.restore_missing() == ["missing==2.0"]
    assert seen == [["missing==2.0"]]
