"""Gemini helpers: thought signatures and conversion of tools and messages to the Gemini format."""

from __future__ import annotations

import json
import base64
from typing import Any

from google.genai import types

from backend.agent.utils.error_logger import log_error

def _signature_to_str(signature: Any) -> str | None:
    """Encode a Gemini thought signature (bytes) to a JSON-safe string.

    Args:
        signature: Raw signature from ``part.thought_signature`` (bytes or str).

    Returns:
        Base64 string, the original value if already a string, or ``None``.
    """
    if isinstance(signature, (bytes, bytearray)):
        try:
            return base64.b64encode(bytes(signature)).decode("ascii")
        except Exception as e:
            log_error(str(e), source="agent.py:_signature_to_str")
            return None
    return signature if isinstance(signature, str) else None

def _signature_from_str(value: Any) -> Any:
    """Decode a thought signature previously encoded with
    :func:`_signature_to_str`.

    Args:
        value: Base64 string, raw bytes or ``None``.

    Returns:
        Bytes ready to be sent to the Gemini API, or ``None``.
    """
    if isinstance(value, str):
        try:
            return base64.b64decode(value)
        except Exception as e:
            log_error(str(e), source="agent.py:_signature_from_str")
            return None
    return value if isinstance(value, (bytes, bytearray)) else None


class GeminiMixin:
    """Builds Gemini tool declarations and message contents."""

    def _sanitize_gemini_schema(self, schema: Any) -> Any:
        """Recursively strip JSON-Schema keys not supported by Gemini.

        Gemini's ``Schema`` only accepts a subset of JSON Schema
        (``type``, ``description``, ``properties``, ``required``, ``items``,
        ``enum``, ``format``). Keys like ``additionalProperties`` or
        ``$schema`` cause 400 errors, so they are removed here.

        Args:
            schema: A JSON Schema dict (or any value).

        Returns:
            The sanitized schema.
        """
        if not isinstance(schema, dict):
            return schema
        allowed = ("type", "description", "properties", "required",
                   "items", "enum", "format")
        out: dict[str, Any] = {}
        for k, v in schema.items():
            if k not in allowed:
                continue
            if k == "properties" and isinstance(v, dict):
                out[k] = {pk: self._sanitize_gemini_schema(pv) for pk, pv in v.items()}
            elif k == "items":
                out[k] = self._sanitize_gemini_schema(v)
            else:
                out[k] = v
        return out

    def _to_gemini_tools(self, tools: list[dict[str, Any]] | None) -> list[Any]:
        """Convert OpenAI-format tool schemas to Gemini ``Tool`` declarations.

        Args:
            tools: Tool definitions in OpenAI format
                (``{"type": "function", "function": {...}}``).

        Returns:
            List with a single ``types.Tool`` holding all function
            declarations, or an empty list when no tools are given.
        """
        if not tools:
            return []
        declarations: list[types.FunctionDeclaration] = []
        for t in tools:
            fn = t.get("function", t)
            params = fn.get("parameters")
            declarations.append(types.FunctionDeclaration(
                name=fn.get("name"),
                description=fn.get("description") or "",
                parameters=self._sanitize_gemini_schema(params) if params else None,
            ))
        return [types.Tool(function_declarations=declarations)]

    def _to_gemini_contents(
        self, msgs: list[dict[str, Any]]
    ) -> tuple[list[types.Content], str | None]:
        """Convert OpenAI-style messages to Gemini ``Content`` objects.

        Mapping rules:

        - ``system`` → accumulated into the returned system instruction.
        - ``user`` → ``role="user"`` with a text part.
        - ``assistant`` with ``tool_calls`` → ``role="model"`` with one
          ``function_call`` part per call (plus its text, if any).
        - ``tool`` → ``role="user"`` with a ``function_response`` part whose
          payload is the parsed JSON of the tool result (or a string wrapper).
        - ``assistant`` plain → ``role="model"`` with a text part.

        Consecutive messages with the same role are merged into a single
        ``Content`` so the history always alternates roles as Gemini requires.

        Args:
            msgs: Messages array in OpenAI format.

        Returns:
            Tuple ``(contents, system_instruction)`` where ``contents`` is
            the list of ``types.Content`` and ``system_instruction`` is the
            concatenated system prompt (or ``None``).
        """
        contents: list[types.Content] = []
        system_instruction: str | None = None
        # Map tool_call_id -> function name so role:"tool" messages without
        # an explicit tool_name can still be linked to their functionCall.
        id_to_name: dict[str, str] = {}

        def _append(role: str, part: types.Part) -> None:
            """Add a part to the last content when it has the same role, or start a new one.

            Args:
                role: Gemini role of the part.
                part: The part to add.
            """
            if contents and contents[-1].role == role:
                contents[-1].parts.append(part)
            else:
                contents.append(types.Content(role=role, parts=[part]))

        for m in msgs:
            role = m.get("role")
            if role == "system":
                text = str(m.get("content") or "")
                system_instruction = (
                    f"{system_instruction}\n\n{text}" if system_instruction else text
                )
                continue

            if role == "tool":
                fn_name = m.get("tool_name") or id_to_name.get(m.get("tool_call_id", ""), "")
                raw = m.get("content")
                # Strip <tool_output> wrapper if present so JSON payloads
                # wrapped in loop.py keep parsing exactly as before.
                # Unwrapped content (creators, old history) is unchanged.
                if isinstance(raw, str) and "<tool_output" in raw and "</tool_output>" in raw:
                    try:
                        start = raw.index(">") + 1
                        end = raw.rindex("</tool_output>")
                        raw = raw[start:end].strip()
                    except (ValueError, AttributeError):
                        pass
                try:
                    payload = json.loads(raw) if isinstance(raw, str) else raw
                except (json.JSONDecodeError, TypeError):
                    payload = {"result": str(raw)}
                if not isinstance(payload, dict):
                    payload = {"result": payload}
                _append("user", types.Part(function_response=types.FunctionResponse(
                    name=fn_name,
                    response=payload,
                )))
                continue

            tcs = m.get("tool_calls")
            if tcs:
                text = m.get("content")
                if text:
                    _append("model", types.Part(text=str(text)))
                for tc in tcs:
                    # Accept both normalized {"id","name","args"} and SDK
                    # wrapped {"id","type","function":{"name","arguments"}}.
                    fn = tc.get("function") if isinstance(tc.get("function"), dict) else tc
                    tc_id = tc.get("id") or ""
                    name = fn.get("name") or ""
                    if tc_id:
                        id_to_name[tc_id] = name
                    args = fn.get("args", fn.get("arguments")) or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    if not isinstance(args, dict):
                        args = {}
                    fc_part = types.Part(function_call=types.FunctionCall(
                        name=name,
                        args=args,
                    ))
                    # Gemini 3.x requires the thought_signature captured from
                    # the original response to be sent back with each
                    # functionCall part when replaying history.
                    sig = _signature_from_str(tc.get("thought_signature"))
                    if sig:
                        fc_part.thought_signature = sig
                    _append("model", fc_part)
                continue

            g_role = "user" if role == "user" else "model"
            _append(g_role, types.Part(text=str(m.get("content") or "")))

        return contents, system_instruction
