"""Command-line entry point for `factory`."""

from __future__ import annotations

import argparse
import contextvars
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from factory_cli.config import (
    PORTAL_NAMES,
    PortalName,
    RuntimeContext,
    collect_known_secrets,
    resolve_portal_key,
)
from factory_cli.doctor import run_doctor
from factory_cli.mcp_config import AGENTS, AgentName, run_mcp_config
from factory_cli.status import run_status
from factory_cli.submit import EXIT_PRECONDITION, run_submit
from factory_cli.testrun import run_test
from factory_cli.transport import redact_text

_PARSE_CTX: contextvars.ContextVar[tuple[dict[str, str] | None, Path | None, bool]] = (
    contextvars.ContextVar("_PARSE_CTX", default=(None, None, False))
)


def _emit(line: str, *, err: bool = False, secrets: Sequence[str] = ()) -> None:
    stream = sys.stderr if err else sys.stdout
    stream.write(redact_text(line, secrets) + "\n")


class _RedactingArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that redacts secrets and URL userinfo before printing any message."""

    def _print_message(self, message: str, file: Any = None) -> None:
        if not message:
            return
        env, home, skip_key_load = _PARSE_CTX.get()
        secrets: tuple[str, ...] = (
            () if skip_key_load else collect_known_secrets(env=env, home=home)
        )
        super()._print_message(redact_text(message, secrets), file)


def build_parser() -> argparse.ArgumentParser:
    parser = _RedactingArgumentParser(
        prog="factory",
        description=(
            "Unified CLI and MCP front door for the Factory fleet "
            "(PFactory, AIFactory, TFactory, CFactory)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    submit_p = sub.add_parser(
        "submit",
        help="Submit an approved intent/spec/plan triple to PFactory and emit a task contract",
    )
    submit_p.add_argument("slug", help="Artifact slug (<slug> or plan/<slug>.md)")
    submit_p.add_argument("--base", dest="base_ref", default=None, help="Base branch reference")
    submit_p.add_argument("--project", dest="project_id", default=None, help="Project ID")
    submit_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Assemble and validate the contract without POSTing to AIFactory",
    )

    test_p = sub.add_parser(
        "test",
        help=(
            "Schedule a TFactory verification run from spec Verification bullets or a criteria file"
        ),
    )
    test_p.add_argument("--project", dest="project_id", required=True, help="Registered project ID")
    spec_group = test_p.add_mutually_exclusive_group(required=True)
    spec_group.add_argument("--spec", dest="spec_slug", help="Spec slug (reads spec/<slug>.md)")
    spec_group.add_argument(
        "--criteria", dest="criteria_file", help="Path to criteria markdown file"
    )
    test_p.add_argument("--branch", required=True, help="Branch to verify")
    test_p.add_argument("--pr", dest="pr_number", type=int, default=None, help="Optional PR number")

    status_p = sub.add_parser(
        "status",
        help=(
            "Check status of pf:<session>, af:<task>, tf:<project>/<spec>, "
            "or a bare correlation key (CFactory key sees the whole tenant)"
        ),
    )
    status_p.add_argument(
        "target",
        help="Identifier: pf:<session> | af:<task> | tf:<project>/<spec> | <correlation-key>",
    )

    sub.add_parser(
        "doctor",
        help="Check portal URLs, key sources, key kinds, health versions, and protected reads",
    )

    sub.add_parser(
        "mcp",
        help=(
            "Run the stdio MCP server "
            "(tools: factory_submit, factory_test, factory_status, factory_doctor)"
        ),
    )

    cfg_p = sub.add_parser(
        "mcp-config",
        help="Print or write the secret-free factory MCP server entry for claude, codex, or agy",
    )
    cfg_p.add_argument("agent", choices=AGENTS, help="Target coding agent")
    cfg_p.add_argument(
        "--write",
        action="store_true",
        help="Merge the factory MCP entry into the agent's configuration file",
    )
    cfg_p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing factory entry when used with --write",
    )

    return parser


def _portals_for_command(args: argparse.Namespace) -> tuple[PortalName, ...]:
    cmd = str(args.command)
    static_map: dict[str, tuple[PortalName, ...]] = {
        "mcp-config": (),
        "mcp": (),
        "submit": ("pfactory",),
        "test": ("tfactory",),
        "doctor": PORTAL_NAMES,
    }
    if cmd in static_map:
        return static_map[cmd]
    target = str(getattr(args, "target", "")).strip()
    if target.startswith("pf:"):
        return ("pfactory", "aifactory")
    if target.startswith("af:"):
        return ("aifactory",)
    return ("tfactory",) if target.startswith("tf:") else ("cfactory",)


def _dispatch_command(
    args: argparse.Namespace,
    rt: RuntimeContext,
) -> int:
    cmd = str(args.command)
    if cmd == "mcp":
        from factory_cli.mcp_server import run_mcp_stdio  # noqa: PLC0415

        return run_mcp_stdio()

    if cmd == "mcp-config":
        agent = cast(AgentName, args.agent)
        cfg_out = run_mcp_config(
            agent,
            write=bool(args.write),
            force=bool(args.force),
            ctx=rt,
        )
        _emit(cfg_out.text.rstrip("\n"), err=cfg_out.exit_code != 0, secrets=())
        return cfg_out.exit_code

    portals = _portals_for_command(args)
    secrets = collect_known_secrets(env=rt.env, home=rt.home, portals=portals)
    try:
        for portal in portals:
            resolve_portal_key(portal, env=rt.env, home=rt.home)
    except ValueError as exc:
        _emit(f"error: {exc}", err=True, secrets=secrets)
        return EXIT_PRECONDITION

    if cmd == "submit":
        outcome: Any = run_submit(
            args.slug,
            base_ref=args.base_ref,
            project_id=args.project_id,
            dry_run=bool(args.dry_run),
            ctx=rt,
        )
    elif cmd == "test":
        outcome = run_test(
            args.project_id,
            args.branch,
            spec_slug=args.spec_slug,
            criteria_file=args.criteria_file,
            pr_number=args.pr_number,
            ctx=rt,
        )
    elif cmd == "status":
        outcome = run_status(args.target, ctx=rt)
    else:
        outcome = run_doctor(ctx=rt)

    for line in outcome.lines:
        _emit(line, err=outcome.exit_code != 0, secrets=secrets)
    return int(outcome.exit_code)


def main(
    argv: Sequence[str] | None = None,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
    config_path: Path | None = None,
) -> int:
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    is_mcp_config = bool(raw_args and raw_args[0] == "mcp-config")
    token = _PARSE_CTX.set((env, home, is_mcp_config))
    try:
        parser = build_parser()
        try:
            args = parser.parse_args(raw_args)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            return EXIT_PRECONDITION if code != 0 else 0
    finally:
        _PARSE_CTX.reset(token)

    rt = RuntimeContext(cwd=cwd, env=env, home=home, config_path=config_path)
    return _dispatch_command(args, rt)


if __name__ == "__main__":
    sys.exit(main())
