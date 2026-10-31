"""Command-line interface for VoiceWriter."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from voicewriter import config
from voicewriter import llm as vw_llm
from voicewriter import profile as vw_profile
from voicewriter import style_eval as vw_eval
from voicewriter import verticals as vw_verticals
from voicewriter.generate import generate_draft


def _add_llm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", default="", help="openai or ollama")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--temperature", type=float, default=0.7)


def _client_from_args(args: argparse.Namespace) -> vw_llm.LlmClient:
    cfg = config.load_llm_config()
    if getattr(args, "provider", ""):
        cfg.provider = args.provider.lower()
    if getattr(args, "base_url", ""):
        cfg.base_url = args.base_url
    if getattr(args, "api_key", ""):
        cfg.api_key = args.api_key
    if getattr(args, "model", ""):
        cfg.model = args.model
    cfg.temperature = args.temperature
    return vw_llm.from_config(cfg)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voicewriter",
        description="Voice-preserving writing agent for fundraising, legal and newsletter copy.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    profile_parser = sub.add_parser("profile", help="Build a voice profile from writing samples.")
    profile_parser.add_argument("name")
    profile_parser.add_argument(
        "--samples", nargs="+", required=True, help="Files, directories, or raw text."
    )
    profile_parser.add_argument(
        "--vertical", default="general", choices=vw_verticals.vertical_names()
    )

    show_parser = sub.add_parser("show", help="Show a saved profile.")
    show_parser.add_argument("name")

    sub.add_parser("profiles", help="List saved profiles.")

    generate_parser = sub.add_parser("generate", help="Generate a draft in a saved voice.")
    generate_parser.add_argument("profile")
    generate_parser.add_argument("--brief", required=True)
    generate_parser.add_argument(
        "--vertical", default="general", choices=vw_verticals.vertical_names()
    )
    generate_parser.add_argument("--format", dest="format_name", default="")
    _add_llm_args(generate_parser)

    eval_parser = sub.add_parser("eval", help="Compare two drafts against a voice profile.")
    eval_parser.add_argument("profile")
    eval_parser.add_argument("--a", dest="text_a", required=True, help="File path or raw text.")
    eval_parser.add_argument("--b", dest="text_b", required=True, help="File path or raw text.")
    eval_parser.add_argument("--judge", choices=["rules", "llm"], default="rules")
    _add_llm_args(eval_parser)

    prefs_parser = sub.add_parser("prefs", help="Manage pairwise style preferences.")
    prefs_sub = prefs_parser.add_subparsers(dest="prefs_command", required=True)
    add_parser = prefs_sub.add_parser("add", help="Record a pairwise preference.")
    add_parser.add_argument("--profile", required=True)
    add_parser.add_argument("--winner", required=True)
    add_parser.add_argument("--loser", required=True)
    rank_parser = prefs_sub.add_parser("rank", help="Show Elo rankings.")
    rank_parser.add_argument("--profile", default="")

    sub.add_parser("install-forge", help="Install the Forge skill and tool into the Forge config directory.")
    return parser


def _cmd_profile(args: argparse.Namespace) -> int:
    texts = vw_profile.resolve_samples(args.samples)
    if not texts:
        print("No usable samples found.", file=sys.stderr)
        return 1
    profile = vw_profile.build_profile(args.name, texts, args.vertical)
    vw_profile.save_profile(profile)
    print(f"Profile '{profile.name}' saved ({profile.sample_words} words, {profile.sample_count} samples).")
    print()
    print(profile.voice_instructions)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    profile = vw_profile.load_profile(args.name)
    if profile is None:
        print(f"Profile '{args.name}' not found.", file=sys.stderr)
        return 1
    print(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False))
    return 0


def _cmd_profiles(args: argparse.Namespace) -> int:
    names = vw_profile.list_profiles()
    if not names:
        print("No profiles saved.")
    for name in names:
        print(name)
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    profile = vw_profile.load_profile(args.profile)
    if profile is None:
        print(f"Profile '{args.profile}' not found.", file=sys.stderr)
        return 1
    client = _client_from_args(args)
    if not client.configured:
        print(
            "No LLM backend configured. Set VOICEWRITER_LLM_PROVIDER, "
            "VOICEWRITER_LLM_BASE_URL and VOICEWRITER_LLM_MODEL, or pass --provider/--model.",
            file=sys.stderr,
        )
        return 1
    draft = generate_draft(profile, args.brief, args.vertical, client, args.format_name)
    print(draft)
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    profile = vw_profile.load_profile(args.profile)
    if profile is None:
        print(f"Profile '{args.profile}' not found.", file=sys.stderr)
        return 1
    text_a = vw_profile.resolve_text(args.text_a)
    text_b = vw_profile.resolve_text(args.text_b)
    if args.judge == "llm":
        client = _client_from_args(args)
        if not client.configured:
            print(
                "LLM judge requires a configured backend. Use --judge rules or configure the LLM.",
                file=sys.stderr,
            )
            return 1
        result = vw_eval.llm_judge(text_a, text_b, profile, client)
    else:
        result = vw_eval.pairwise(text_a, text_b, profile)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _cmd_prefs(args: argparse.Namespace) -> int:
    if args.prefs_command == "add":
        entry = vw_eval.record_preference(args.winner, args.loser, args.profile)
        print(json.dumps(entry, ensure_ascii=False))
        return 0
    if args.prefs_command == "rank":
        for row in vw_eval.rankings(args.profile or None):
            print(f"{row['elo']:>7}  {row['name']}  ({row['matches']} matches)")
        return 0
    return 1


def _cmd_install_forge(args: argparse.Namespace) -> int:
    forge_dir = Path(__file__).resolve().parent / "forge"
    forge_home = Path.home() / ".config" / "synapseForge"

    skills_src = forge_dir / "skills" / "voice-preserving-writer"
    skills_dst = forge_home / "skills" / "voice-preserving-writer"
    tool_src = forge_dir / "tools" / "voicewrite.py"
    tools_dst = forge_home / "tools"

    installed: list[str] = []
    if skills_src.is_dir():
        skills_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skills_src, skills_dst, dirs_exist_ok=True)
        installed.append(str(skills_dst))
    if tool_src.is_file():
        tools_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tool_src, tools_dst / "voicewrite.py")
        installed.append(str(tools_dst / "voicewrite.py"))

    if not installed:
        print("No Forge skill/tool files found.", file=sys.stderr)
        return 1
    print("Installed into Forge config:")
    for path in installed:
        print(f"- {path}")
    print("Restart or refresh the Forge agent to pick up the new tool/skill.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "profile": _cmd_profile,
        "show": _cmd_show,
        "profiles": _cmd_profiles,
        "generate": _cmd_generate,
        "eval": _cmd_eval,
        "prefs": _cmd_prefs,
        "install-forge": _cmd_install_forge,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
