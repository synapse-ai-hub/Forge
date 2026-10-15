"""Manual CLI probe for a System One decision model using real app code.

YAML-driven probe: scenarios live in ``tests/decisor/scenarios/`` (one
doc per scenario, keyed by test number, plus a ``config`` doc with the
sleeps). The CLI runs every scenario in order with no arguments. Each
scenario passes its complete prompt in ``prompt`` and it goes to
``Agent.decision`` (``backend/agent/agent.py``) as ``state`` verbatim.
Only the hardcoded per-mode task wrappers are added, and only for the
``compare`` LLM runs. Stores a verbatim report as Markdown plus a
``.json`` table under ``tests/decisor/report/<scenario>/``, and appends
one line per model to ``tests/decisor/report/general.jsonl`` (append
only, never rewritten). The synapseForge parent-agent prompt recreator
lives apart in ``tests/decisor/parent_state.py``.

Rate-limit policy for the decision model: a rate-limited scenario is
skipped (sleep, then next scenario); 3 consecutive rate limits stop the
whole run.

Usage:
    python -m tests.decisor.decision_cli
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Any

import yaml

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from backend.agent.agent import Agent
from backend.agent.utils.provider_keys import PROVIDER_REGISTRY
from backend.agent.utils.spend_handler import calculate_cost
from google import genai
from openai import AsyncOpenAI

DECISION_PROVIDER = "openrouter"
DECISION_MODEL = "inception/mercury-decide:free"
COMPARE_PROVIDERS = ["google", "groq", "openrouter", "groq"]
COMPARE_MODELS = [
    "gemini-3.5-flash-lite",
    "openai/gpt-oss-20b",
    "inclusionai/ling-3.1-flash",
    "qwen/qwen3.8-27b",
]
COMPARE_ENV_KEYS = ["GOOGLE_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY",
                    "GROQ_API_KEY"]
REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "report")
SCENARIOS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "scenarios", "decisor.yaml")
GENERAL_JSONL = os.path.join(REPORT_DIR, "general.jsonl")

MAX_CONSECUTIVE_RATE_LIMITS = 3

_RATE_LIMIT_CODE_RE = re.compile(r"\b(429|413|402)\b")
_RATE_LIMIT_TEXT_MARKERS = (
    "rate_limit",
    "rate-limit",
    "rate limit",
    "too many requests",
    "resource_exhausted",
    "quota exceeded",
)


class DecisionRateLimited(Exception):
    """The decision model answered with a rate-limit error."""

    def __init__(self, name: str, message: str = "") -> None:
        """Store the scenario name and the raw error message.

        Args:
            name: Scenario (test) name that was skipped.
            message: Raw error message from the decision response.
        """
        super().__init__(name)
        self.scenario_name = name
        self.error_message = message


def is_rate_limit_response(response: Any) -> bool:
    """Detect a rate-limit failure in an ``Agent.decision`` response.

    ``Agent.decision`` never raises: failures come back as
    ``{"status": "error", "message": ...}``. A rate limit is reported
    when the status is ``"error"`` and the message carries a rate-limit
    code (429/413/402) or marker.

    Args:
        response: Raw ``Agent.decision`` response.

    Returns:
        True when the response is a rate-limit error.
    """
    if not isinstance(response, dict):
        return False
    if response.get("status") != "error":
        return False
    message = str(response.get("message") or "").lower()
    if _RATE_LIMIT_CODE_RE.search(message):
        return True
    return any(marker in message for marker in _RATE_LIMIT_TEXT_MARKERS)


def parse_criteria(spec: str) -> dict[str, str]:
    """Parse a ``"key=description;key2=description2"`` criteria spec.

    Args:
        spec: Raw criteria string from the CLI.

    Returns:
        Mapping of option key to description.

    Raises:
        ValueError: If any pair has no ``=`` or an empty key.
    """
    criteria: dict[str, str] = {}
    for pair in (spec or "").split(";"):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(f"Invalid criteria pair (missing '='): {pair!r}")
        key, _, description = pair.partition("=")
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid criteria pair (empty key): {pair!r}")
        criteria[key] = description.strip()
    if not criteria:
        raise ValueError("Empty criteria: pass at least one 'key=description' pair.")
    return criteria


def build_questions(scenario: dict[str, Any]) -> dict[str, Any]:
    """Build the ``questions`` dict for ``Agent.decision`` from a scenario.

    Only the question of ``scenario["mode"]`` is built (one modality per
    run). Names follow the jev SDK (``noul``, ``choice``, ``score``).

    Args:
        scenario: Scenario mapping from the YAML (``mode``, ``noul`` /
            ``choice`` / ``score``, ``instructions``).

    Returns:
        Mapping with a single question (the mode one).

    Raises:
        ValueError: If a choice/score spec cannot be parsed, or the
            mode question was not provided.
    """
    name = scenario.get("scenario", "?")
    mode = scenario.get("mode")
    questions: dict[str, Any] = {}
    if mode == "noul":
        if scenario.get("noul") is None:
            raise ValueError("{}: mode noul requiere 'noul'".format(name))
        questions["noul"] = {"type": "noul",
                             "instructions": scenario["noul"]}
    elif mode == "choice":
        if scenario.get("choice") is None:
            raise ValueError("{}: mode choice requiere 'choice'".format(name))
        questions["choice"] = {
            "type": "choice",
            "instructions": scenario.get("instructions") or "",
            "criteria": parse_criteria(scenario["choice"]),
        }
    elif mode == "score":
        if scenario.get("score") is None:
            raise ValueError("{}: mode score requiere 'score'".format(name))
        # SDK ScoreQuestion.criteria is an ordered list of level
        # descriptions (position = score, starting at zero), not a dict:
        # plain comma-separated values, any count.
        levels = [v.strip() for v in (scenario["score"] or "").split(",")]
        levels = [v for v in levels if v]
        if not levels:
            raise ValueError("{}: empty score levels".format(name))
        questions["score"] = {
            "type": "score",
            "instructions": scenario.get("instructions") or "",
            "criteria": levels,
        }
    else:
        raise ValueError("modo inválido en {}: {}".format(name, mode))
    return questions


def load_scenarios() -> tuple[dict[str, Any],
                              list[tuple[str, dict[str, Any]]]]:
    """Load the YAML config and scenarios in document order.

    Returns:
        Tuple of (config mapping with the sleeps, list of
        (scenario name, scenario mapping)).

    Raises:
        ValueError: If the file has no scenarios or a scenario is
            missing name, mode or prompt.
    """
    with open(SCENARIOS_PATH, encoding="utf-8") as f:
        docs = [d for d in yaml.safe_load_all(f) if d]
    config: dict[str, Any] = {}
    scenarios: list[tuple[str, dict[str, Any]]] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        if "config" in doc and "scenario" not in doc:
            config = doc.get("config") or {}
        elif "scenario" in doc:
            name = doc.get("scenario")
            if not doc.get("mode") or doc.get("prompt") is None:
                raise ValueError(
                    "{}: el escenario requiere 'mode' y 'prompt'".format(
                        name))
            scenarios.append((str(name), doc))
    if not scenarios:
        raise ValueError("sin escenarios en {}".format(SCENARIOS_PATH))
    return config, scenarios


def append_jsonl(name: str, mode: str,
                 table_data: list[dict[str, Any]]) -> None:
    """Append one JSON line per model to ``report/general.jsonl``.

    Args:
        name: Scenario (test) name, stored as the ``prueba`` key.
        mode: Question modality (``noul``, ``choice`` or ``score``),
            stored as the ``tipo`` key.
        table_data: Same row mappings stored in the individual ``.json``
            (no fields removed).
    """
    with open(GENERAL_JSONL, "a", encoding="utf-8") as f:
        for row in table_data:
            f.write(json.dumps({"prueba": name, "tipo": mode, **row},
                               ensure_ascii=False) + "\n")


def _table_cell(value: Any) -> str:
    """Flatten a value into a single Markdown table cell.

    Args:
        value: Any value.

    Returns:
        Single-line string with pipes escaped.
    """
    return str(value).replace("|", "\\|").replace("\n", " ")


def _extract_metrics(response: Any, elapsed: float,
                     provider: str, model: str,
                     is_decision: bool = False) -> dict[str, Any]:
    """Extract table metrics (tokens, time, decision, cost) from a call.

    Args:
        response: Raw contract response (dict with ``data`` + ``usage``).
        elapsed: Seconds the call took.
        provider: Provider id used in the call.
        model: Model id used in the call.
        is_decision: Whether this is the decision-model call (only it
            reports ``confianza``; compare LLM runs get ``None``).

    Returns:
        Dict with ``tokens_entrada``, ``tokens_salida``, ``tiempo``,
        ``decision``, ``confianza`` and ``gasto_usd``.
    """
    resp = response if isinstance(response, dict) else {}
    usage = resp.get("usage") or {}
    data = resp.get("data") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    choice = data.get("choice") if isinstance(data, dict) else None
    answers = data.get("answers") if isinstance(data, dict) else None
    if isinstance(answers, dict) and isinstance(
            answers.get("choice"), dict) and "choice" in answers["choice"]:
        decision_value = answers["choice"]["choice"]
    elif isinstance(answers, dict) and isinstance(
            answers.get("score"), dict) and "score" in answers["score"]:
        decision_value = answers["score"]["score"]
    elif isinstance(answers, dict) and isinstance(
            answers.get("noul"), dict) and "noul" in answers["noul"]:
        # NoulAnswer has no confidence, only the yes probability.
        decision_value = answers["noul"]["noul"]
    elif isinstance(choice, dict) and "choice" in choice:
        decision_value = choice["choice"]
    elif isinstance(data, dict):
        decision_value = data if data else resp.get("message")
        decision_value = json.dumps(decision_value, ensure_ascii=False)
    else:
        decision_value = data if data else resp.get("message")
    try:
        _, _, cost_total = calculate_cost(
            provider, model, prompt_tokens, completion_tokens)
    except Exception:
        cost_total = 0.0
    try:
        # Table/JSON only (raw sections stay verbatim): numeric
        # decisions with 2 decimals.
        decision_value = round(float(decision_value), 2)
    except (TypeError, ValueError):
        pass
    confidence = None
    if is_decision and isinstance(answers, dict):
        for answer in answers.values():
            if isinstance(answer, dict) and "confidence" in answer:
                confidence = answer["confidence"]
                break
    return {
        "tokens_entrada": prompt_tokens,
        "tokens_salida": completion_tokens,
        "tiempo": round(elapsed, 2),
        "decision": decision_value,
        "confianza": confidence,
        "gasto_usd": cost_total,
    }


def _comparison_row(provider: str, model: str, response: Any,
                    elapsed: float,
                    is_decision: bool = False) -> str:
    """Build one Markdown table row with tokens, time, decision and cost.

    Args:
        provider: Provider id used in the call.
        model: Model id used in the call.
        response: Raw contract response (dict with ``data`` + ``usage``).
        elapsed: Seconds the call took.
        is_decision: Whether this is the decision-model row (only it
            shows ``confianza``; compare LLM rows show ``null``).

    Returns:
        Markdown table row string.
    """
    metrics = _extract_metrics(response, elapsed, provider, model,
                               is_decision)
    confidence = metrics["confianza"]
    return "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
        _table_cell(provider),
        _table_cell(model),
        metrics["tokens_entrada"],
        metrics["tokens_salida"],
        metrics["tiempo"],
        _table_cell(metrics["decision"]),
        "null" if confidence is None else confidence,
        metrics["gasto_usd"],
    )


def save_report(filename: str | None, state: str,
                questions: dict[str, Any],
                response: Any, elapsed: float,
                compare_runs: list[dict[str, Any]] | None = None,
                subfolder: str | None = None,
                ) -> tuple[str, list[dict[str, Any]]]:
    """Save the verbatim Markdown report under tests/decisor/report/.

    Args:
        filename: ``.md`` file name (basename only; always stored in the
            test report dir). A timestamped default is used when ``None``.
        state: Exact text sent as ``state`` to ``Agent.decision`` (shown
            raw, as plain text, without any transformation).
        response: Raw ``Agent.decision`` response (stored verbatim).
        elapsed: Seconds the ``Agent.decision`` call took.
        compare_runs: Optional list of compare runs (each with
            ``provider``, ``model``, ``task_section``, ``response`` and
            ``elapsed``). All runs share the same base prompt as the
            decision model; only the added task section is shown, then
            one raw section per model and the final comparison table.
        subfolder: Optional report subfolder (scenario name). The ``.md``
            and ``.json`` are saved inside it.

    Returns:
        Absolute path of the written report. A ``.json`` file with the
        same name (comparison table data) is saved next to it.
    """
    target_dir = REPORT_DIR
    if subfolder:
        target_dir = os.path.join(REPORT_DIR, subfolder)
    os.makedirs(target_dir, exist_ok=True)
    if not filename:
        filename = "decision_{}.md".format(
            datetime.now().strftime("%Y%m%d_%H%M%S"))
    stem = os.path.basename(filename)
    if stem.lower().endswith(".md"):
        stem = stem[:-len(".md")]
    filename = stem + ".md"
    try:
        raw_json = json.dumps(response, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        raw_json = str(response)
    report = (
        "# Decision Probe\n"
        "\n"
        "- provider: {}\n"
        "- model: {}\n"
        "- timestamp: {}\n"
        "\n"
        "## Prompt exacto del modelo de decisión\n"
        "\n"
        "````\n"
        "{}\n"
        "````\n"
    ).format(
        DECISION_PROVIDER,
        DECISION_MODEL,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        state,
    )
    if compare_runs:
        report += (
            "\n"
            "### Agregado para LLM tradicional\n"
            "\n"
            "````\n"
            "{}\n"
            "````\n"
        ).format(compare_runs[0]["task_section"])
    report += (
        "\n"
        "## Parámetros de modelo de decisión\n"
        "\n"
        "```json\n"
        "{}\n"
        "```\n"
        "\n"
        "## Respuesta modelo de decisión\n"
        "\n"
        "```json\n"
        "{}\n"
        "```\n"
    ).format(
        json.dumps(questions, ensure_ascii=False, indent=2),
        raw_json,
    )
    rows = [
        _comparison_row(
            DECISION_PROVIDER, DECISION_MODEL, response, elapsed,
            True),
    ]
    table_data = [{
        "proveedor": DECISION_PROVIDER,
        "modelo": DECISION_MODEL,
        **_extract_metrics(
            response, elapsed, DECISION_PROVIDER, DECISION_MODEL,
            True),
    }]
    if compare_runs:
        for run_entry in compare_runs:
            try:
                run_raw = json.dumps(
                    run_entry["response"], ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                run_raw = str(run_entry["response"])
            report += (
                "\n"
                "## Respuesta {}\n"
                "\n"
                "```json\n"
                "{}\n"
                "```\n"
            ).format(run_entry["model"], run_raw)
            rows.append(
                _comparison_row(
                    run_entry["provider"], run_entry["model"],
                    run_entry["response"], run_entry["elapsed"]))
            table_data.append({
                "proveedor": run_entry["provider"],
                "modelo": run_entry["model"],
                **_extract_metrics(
                    run_entry["response"], run_entry["elapsed"],
                    run_entry["provider"], run_entry["model"]),
            })
    report += (
        "\n"
        "## Tabla comparativa\n"
        "\n"
        "| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "{}\n"
    ).format("\n".join(rows))
    path = os.path.join(target_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    json_name = stem + ".json"
    json_path = os.path.join(target_dir, json_name)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(table_data, f, ensure_ascii=False, indent=2)
    return path, table_data


async def run_scenario(name: str, scenario: dict[str, Any],
                       sleep_llamadas: float) -> tuple[str, list[dict[str,
                                                                     Any]]]:
    """Run one YAML scenario and return its report path and table data.

    Args:
        name: Scenario (test) name.
        scenario: Scenario mapping from the YAML.
        sleep_llamadas: Seconds to sleep between model calls.

    Returns:
        Tuple of (written report path, table-data row mappings).

    Raises:
        DecisionRateLimited: If the decision model answers with a
            rate-limit error (the scenario must be skipped).
    """
    mode = scenario.get("mode")
    questions = build_questions(scenario)
    agent = Agent()
    # Clean probe: the scenario prompt goes to state verbatim. Only the
    # hardcoded per-mode task wrappers are added, and only for the
    # compare LLM runs.
    state: str = scenario["prompt"]
    # Same as POST /api/config/models/decision/enabled with enabled=true
    # (backend/routes/config.py): enables the decision path for this call.
    agent.decision_enabled = True
    start = time.perf_counter()
    response = await agent.decision(
        state, questions,
        provider=DECISION_PROVIDER, model=DECISION_MODEL,
    )
    elapsed = time.perf_counter() - start
    if is_rate_limit_response(response):
        raise DecisionRateLimited(
            name, str(response.get("message") or ""))
    compare_runs: list[dict[str, Any]] = []
    compare = bool(scenario.get("compare", False))
    if compare:
        await asyncio.sleep(sleep_llamadas)
        # Task section depends on the mode: the chat model does not
        # understand the decision-model JSON shape, so it gets the same
        # array as plain text plus a hardcoded wrapper that always
        # orders: return only that, no extra text, no arguing.
        if mode == "choice":
            options = "\n".join(
                "- {}: {}".format(key, description)
                for key, description in
                questions["choice"]["criteria"].items()
            )
            task_section = (
                "## Tarea\n"
                "En base a lo indicado en el prompt y a la solicitud del "
                "usuario, elige una de las siguientes opciones y devuelve "
                "solo la opción elegida, sin texto extra, sin argumentar.\n"
                "Opciones:\n"
                "{}".format(options)
            )
        elif mode == "score":
            # Same scale as the decision model: dict built automatically
            # from the level count (0 to N-1). The LLM must return only
            # a float on that scale (may fall between levels).
            score_map = {
                str(i): description
                for i, description in
                enumerate(questions["score"]["criteria"])
            }
            task_section = (
                "## Tarea\n"
                "Asigná un puntaje en base a los criterios del usuario y "
                "devolvé solo el puntaje como número (puede tener "
                "decimales, puede caer entre niveles), sin texto extra, "
                "sin argumentar.\n"
                "Escala:\n"
                "```json\n"
                "{}\n"
                "```".format(json.dumps(score_map, ensure_ascii=False))
            )
        else:
            task_section = (
                "## Tarea\n"
                "Solo respondé esta pregunta en función a lo indicado por "
                "el usuario y devolvé solo la respuesta, sin texto extra, "
                "sin argumentar.\n"
                "Pregunta: {}".format(questions["noul"]["instructions"])
            )
        llm_prompt = "{}\n{}".format(state, task_section)
        for i in range(len(COMPARE_PROVIDERS)):
            provider = COMPARE_PROVIDERS[i]
            model = COMPARE_MODELS[i]
            api_key = os.environ.get(COMPARE_ENV_KEYS[i])
            if not api_key:
                raise ValueError(
                    "{} no está en el entorno".format(COMPARE_ENV_KEYS[i]))
            if provider == "google":
                # Same client construction as Agent.__init__ (agent.py):
                # the Google SDK client with the key, so llm_process
                # uses it.
                agent.google_client = genai.Client(api_key=api_key)
            else:
                # Same construction as rebuild_provider_client
                # (agent.py): AsyncOpenAI with the provider base_url,
                # only the key comes from the environment.
                base_url = str(
                    PROVIDER_REGISTRY[provider].get("base_url") or ""
                ).rstrip("/")
                agent._openai_clients[provider] = AsyncOpenAI(
                    base_url=base_url, api_key=api_key)
            run_start = time.perf_counter()
            run_response = await agent.llm_process(
                model=model,
                prompt=llm_prompt,
                system_content="",
                provider=provider,
            )
            run_elapsed = time.perf_counter() - run_start
            compare_runs.append({
                "provider": provider,
                "model": model,
                "task_section": task_section,
                "response": run_response,
                "elapsed": run_elapsed,
            })
            if i < len(COMPARE_PROVIDERS) - 1:
                await asyncio.sleep(sleep_llamadas)
    return save_report(scenario.get("file"), state, questions,
                       response, elapsed, compare_runs, subfolder=name)


async def run_all() -> list[str]:
    """Run every YAML scenario in order, appending to general.jsonl.

    A scenario whose decision call hits a rate limit is skipped (sleep,
    then next scenario). After ``MAX_CONSECUTIVE_RATE_LIMITS``
    consecutive rate limits the whole run stops. ``general.jsonl`` is
    only appended to, never rewritten.

    Returns:
        List of written report paths.
    """
    config, scenarios = load_scenarios()
    sleep_llamadas = float(config.get("sleep_entre_llamadas", 30))
    sleep_escenarios = float(config.get("sleep_entre_escenarios", 30))
    paths: list[str] = []
    consecutive_rate_limits = 0
    for index, (name, scenario) in enumerate(scenarios):
        try:
            path, table_data = await run_scenario(name, scenario,
                                                  sleep_llamadas)
        except DecisionRateLimited as exc:
            consecutive_rate_limits += 1
            print("Rate limit en modelo de decisión ({}): se omite {}.".format(
                exc.error_message, name))
            if consecutive_rate_limits >= MAX_CONSECUTIVE_RATE_LIMITS:
                print("3 rate limits seguidos: se corta el test.")
                break
            await asyncio.sleep(sleep_escenarios)
            continue
        consecutive_rate_limits = 0
        append_jsonl(name, scenario.get("mode"), table_data)
        print(f"Reporte guardado en: {path}")
        paths.append(path)
        if index < len(scenarios) - 1:
            await asyncio.sleep(sleep_escenarios)
    return paths


def main() -> int:
    """CLI entry point (no arguments: everything comes from the YAML).

    Returns:
        Process exit code.
    """
    os.chdir(REPO_ROOT)
    try:
        asyncio.run(run_all())
    except ValueError as exc:
        print(f"Error: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
