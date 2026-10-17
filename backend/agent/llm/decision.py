"""Decision-model call: typed responses with a confidence level."""

from __future__ import annotations

import importlib.util
import time
from typing import Any

from backend.agent.utils.error_logger import log_error
from backend.agent.utils import provider_keys
from backend.agent.utils.contract import (
    ContractResponse,
    make_error_response,
    make_success_response,
    validate_response,
    zero_usage,
)

class DecisionMixin:
    """System One decision calls."""

    @property
    def decision_ready(self) -> bool:
        """True when ``decision`` would make a real call.

        Same conditions as ``decision``: enabled, provider and model
        selected, API key stored and ``typesafe-sdk`` installed.
        """
        try:
            provider_id = (self.decision_provider or '').strip().lower()
            if not self.decision_enabled or not (self.decision_model or '').strip():
                return False
            if provider_keys.get_decision_provider(provider_id) is None:
                return False
            if not provider_keys.get_decision_key(provider_id):
                return False
            return importlib.util.find_spec('typesafe_sdk') is not None
        except Exception as e:
            log_error(str(e), source='decision.py:decision_ready')
            return False

    async def decision(self, state: str | dict[str, Any],
                       questions: dict[str, Any],
                       provider: str | None = None,
                       model: str | None = None) -> ContractResponse:
        """Ask a System One decision model and return typed answers.

        Callable from anywhere, like ``llm_process`` or ``streaming``: the
        caller builds ``questions`` (with its options inside each question)
        and reads the typed answers from ``data``.

        Each question is a dict with ``type`` (``"noul"`` | ``"choice"`` |
        ``"score"``), ``instructions`` and ``criteria`` (for ``choice``,
        ``criteria`` maps option key → description)::

            {"route": {"type": "choice", "instructions": "...",
                       "criteria": {"billing": "...", "technical": "..."}}}

        Args:
            state: Content the model decides about (text or JSON-able dict).
            questions: Mapping of question name → question dict.
            provider: Optional decision-provider override (e.g.
                ``"openrouter"``, ``"typesafe"``). When ``None``, uses the
                user selection (``self.decision_provider``).
            model: Optional decision-model override. When ``None``, uses the
                user selection (``self.decision_model``).

        Returns:
            ``ContractResponse`` with:
            - ``data`` — ``{"available": bool, "answers": {...} | None,
              "model": str | None, "provider": str | None}``. ``answers``
              maps each question name to its nested answer JSON.
            - ``usage`` — token / time report.
            When the decision model is not enabled/configured (or the SDK
            is missing), no call is made and ``available`` is ``False``
            (graceful: the caller keeps the current flow, no error).
        """
        effective_provider = provider if provider is not None else self.decision_provider
        effective_model = model if model is not None else self.decision_model
        try:
            _dec_t0 = time.time()
            if not self.decision_enabled:
                return validate_response(make_success_response(
                    message='Decision model not enabled.',
                    data={'available': False, 'answers': None,
                          'model': None, 'provider': None},
                    usage=zero_usage(),
                ))
            provider_id = (effective_provider or '').strip().lower()
            decision_entry = provider_keys.get_decision_provider(provider_id)
            if decision_entry is None or not (effective_model or '').strip():
                return validate_response(make_success_response(
                    message='Decision model not configured.',
                    data={'available': False, 'answers': None,
                          'model': None, 'provider': None},
                    usage=zero_usage(),
                ))
            api_key = provider_keys.get_decision_key(provider_id)
            if not api_key:
                return validate_response(make_success_response(
                    message=f"Decision model not configured: missing API key for '{provider_id}'.",
                    data={'available': False, 'answers': None,
                          'model': None, 'provider': None},
                    usage=zero_usage(),
                ))
            try:
                from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score
            except ImportError:
                return validate_response(make_success_response(
                    message='Decision model not configured: typesafe-sdk not installed.',
                    data={'available': False, 'answers': None,
                          'model': None, 'provider': None},
                    usage=zero_usage(),
                ))
            _builders = {'noul': Noul, 'choice': Choice, 'score': Score}
            typed_questions = {}
            for name, spec in (questions or {}).items():
                qtype = str((spec or {}).get('type') or '').strip().lower()
                builder = _builders.get(qtype)
                if builder is None:
                    return validate_response(make_error_response(
                        message=f"Invalid decision question '{name}': unknown type '{qtype}'.",
                        usage=zero_usage(),
                    ))
                typed_questions[name] = builder(
                    instructions=str((spec or {}).get('instructions') or ''),
                    criteria=(spec or {}).get('criteria'),
                )
            client = AsyncTypeSafeClient(
                api_key=api_key,
                base_url=str(decision_entry.get('sdk_base_url') or '').rstrip('/'),
            )
            try:
                response = await client.system_one(
                    state=state,
                    questions=typed_questions,
                    model=(effective_model or '').strip(),
                )
            finally:
                try:
                    await client.close()
                except Exception:
                    pass
            sys_usage = response.usage
            prompt_tokens = int(getattr(sys_usage, 'input_tokens', 0) or 0)
            completion_tokens = int(getattr(sys_usage, 'output_tokens', 0) or 0)
            total_tokens = prompt_tokens + completion_tokens
            total_time = round(time.time() - _dec_t0, 2)
            answers = {
                name: answer.model_dump() if hasattr(answer, 'model_dump') else answer
                for name, answer in (response.answers or {}).items()
            }
            self._record_spend(provider_id, (effective_model or '').strip(), {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'total_time': total_time,
            })
            return validate_response(make_success_response(
                message='Decision ok.',
                data={'available': True, 'answers': answers,
                      'model': getattr(response, 'model', effective_model),
                      'provider': provider_id},
                usage={
                    'prompt_tokens': prompt_tokens,
                    'completion_tokens': completion_tokens,
                    'total_tokens': total_tokens,
                    'total_time': total_time,
                },
            ))
        except Exception as e:
            log_error(str(e), source="agent.py:decision")
            try:
                self._record_spend(effective_provider, effective_model or 'unknown', None)
            except Exception:
                pass
            return validate_response(make_error_response(
                message=str(e),
                usage={
                    'prompt_tokens': 0,
                    'completion_tokens': 0,
                    'total_tokens': 0,
                    'total_time': 0,
                },
            ))
