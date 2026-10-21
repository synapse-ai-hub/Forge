"""User prompt of an agent node in a TOML file (``prompt_file``)."""

import pytest

from backend.agent.utils import workflow_loader
from backend.agent.utils.workflow_validator import validate_workflow


@pytest.fixture()
def prompts_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow_loader, "get_workflow_prompts_dir", lambda: tmp_path)
    return tmp_path


def _workflow(**node):
    base = {"id": "a", "type": "agent", "step": 1, "agent_name": "x", "final": True}
    return {"name": "w", "nodes": [{**base, **node}]}


def test_toml_is_rendered_as_the_user_message(prompts_dir):
    (prompts_dir / "revisar.toml").write_text(
        'objetivo = "Revisar commits."\n'
        'archivos = ["repo/README.md", "repo/backend"]\n\n'
        "[instrucciones]\n"
        'devolver = "Tabla por autor."\n',
        encoding="utf-8",
    )
    result = workflow_loader.load_prompt_file("revisar")
    assert result["status"] == "success"
    assert "## objetivo\n\nRevisar commits." in result["data"]
    assert "- repo/README.md" in result["data"]
    assert "## instrucciones\n\n### devolver\n\nTabla por autor." in result["data"]


@pytest.mark.parametrize("name", ["../x", "a/b", "a.b", ""])
def test_invalid_names_are_rejected(prompts_dir, name):
    assert workflow_loader.load_prompt_file(name)["status"] == "error"


def test_missing_and_broken_files_report_why(prompts_dir):
    assert "No existe" in workflow_loader.load_prompt_file("nada")["message"]
    (prompts_dir / "roto.toml").write_text("esto = no es toml", encoding="utf-8")
    assert "TOML válido" in workflow_loader.load_prompt_file("roto")["message"]


def test_validator_keeps_prompt_file_only_for_agent_nodes():
    ok = validate_workflow(_workflow(prompt_file="revisar"))
    assert ok["status"] == "success"
    assert ok["data"]["nodes"][0]["prompt_file"] == "revisar"
    other = validate_workflow({"name": "w", "nodes": [
        {"id": "t", "type": "tool", "step": 1, "tool": "read", "prompt_file": "x", "final": True}]})
    assert other["data"]["nodes"][0]["prompt_file"] == ""
    assert validate_workflow(_workflow(prompt_file="../hack"))["status"] == "error"
