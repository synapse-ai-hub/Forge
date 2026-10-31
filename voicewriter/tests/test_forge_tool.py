"""Verify the Forge external tool contract."""

import importlib.util
import inspect
from pathlib import Path


def test_forge_tool_signature() -> None:
    tool_path = Path(__file__).resolve().parents[1] / "forge" / "tools" / "voicewrite.py"
    spec = importlib.util.spec_from_file_location("voicewrite_tool", tool_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    handler = getattr(module, "voicewrite")
    assert callable(handler)
    assert inspect.iscoroutinefunction(handler)

    signature = inspect.signature(handler)
    assert "action" in signature.parameters
    assert signature.parameters["action"].default is inspect.Parameter.empty
    assert "samples" in signature.parameters
    assert "brief" in signature.parameters

    doc_first_line = (module.__doc__ or "").strip().split("\n")[0]
    assert doc_first_line
