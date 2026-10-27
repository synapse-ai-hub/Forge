"""ShellMixin — native tool shell."""

import asyncio
import logging
import os
import subprocess

from backend.agent.utils.config_dir import workspace_ctx
from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.packages import backend_python_env, install_package, parse_pip_install

logger = logging.getLogger(__name__)


class ShellMixin:
    """Native tool ``shell``: run a terminal command."""
    @staticmethod
    def _pip_install(specs: list[str], error: str) -> dict:
        """Run a ``pip install`` request through the controlled installer.

        A rejected command or a failed install returns an error contract
        (per the unified contract: failures carry ``status`` ``"error"``
        with the detail in ``message``), so a ``run`` node of a workflow
        fails just like with any other failed tool.

        Args:
            specs: Packages to install.
            error: Reason the command was rejected, empty when it was accepted.

        Returns:
            Contract dict; on success ``data`` holds ``output``,
            ``returncode`` (0), ``truncated`` and ``workdir``.
        """
        if error:
            return make_error_response(
                message=f"Command rejected: {error}",
                usage=zero_usage(),
            )
        lines: list[str] = []
        failed = False
        for spec in specs:
            result = install_package(spec)
            lines.append(str(result.get("message", "")))
            if result.get("status") != "success":
                failed = True
        if failed:
            return make_error_response(
                message="\n".join(lines) or "pip install failed.",
                usage=zero_usage(),
            )
        return make_success_response(
            message="Command executed.",
            data={"output": "\n".join(lines), "returncode": 0, "truncated": False, "workdir": os.getcwd()},
            usage=zero_usage(),
        )

    async def shell(self, command: str, timeout: int = 30000,
                        workdir: str | None = None) -> dict:
            """Run a terminal command in the system shell.

            Non-blocking: runs the command in a worker thread (via
            ``asyncio.to_thread``) so the event loop keeps serving Telegram
            polling / SSE while the command executes. This avoids the
            ``NotImplementedError`` raised by ``asyncio.create_subprocess_shell``
            on Windows when the running event loop is a ``SelectorEventLoop``
            (which does not implement subprocess transport).

            Supports cancellation via the stream cancel event (the worker thread
            is abandoned; the process may keep running in the background) and a
            timeout. Output larger than 50 KB is truncated.

            Args:
                command: The command to execute (e.g. ``"dir"``, ``"python script.py"``).
                timeout: Maximum execution time in milliseconds (default 30000).
                workdir: Working directory for the command. If None, uses the workspace
                    of the running workflow, or the project root outside workflows.

            Returns:
                dict with ``{status, message, data, usage}``.
                On success ``data`` contains ``output``, ``returncode`` (0)
                and ``truncated``. A non-zero exit code returns an error
                contract with the command output in ``message``.
            """
            # The per-call snapshot (ContextVar) wins over the shared attribute:
            # the attribute can hold the event of an unrelated, earlier chat.
            from backend.agent.utils.loop_helpers import _tool_call_ctx

            snapshot = _tool_call_ctx.get()
            if snapshot is not None:
                cancel_event = snapshot.get("stream_cancel_event")
            else:
                cancel_event = getattr(self, "_stream_cancel_event", None)
            # Installing a library is never a free-form command: it goes through
            # ``install_package`` (backend's Python, project packages held, recorded).
            pip_request = parse_pip_install(command)
            if pip_request is not None:
                return await asyncio.to_thread(self._pip_install, *pip_request)
            try:
                cwd = workdir or workspace_ctx.get() or os.getcwd()
                timeout_s = timeout / 1000

                # Run the blocking subprocess call in a worker thread so the
                # event loop is never blocked. ``subprocess.run`` works on every
                # platform regardless of the event-loop policy (unlike
                # ``asyncio.create_subprocess_shell`` which is unsupported on
                # Windows ``SelectorEventLoop``).
                def _run() -> subprocess.CompletedProcess:
                    """Run the command in the worker thread.

                    Returns:
                        The finished process.
                    """
                    return subprocess.run(
                        command,
                        shell=True,
                        cwd=cwd,
                        env=backend_python_env(),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=timeout_s,
                    )

                run_task = asyncio.create_task(asyncio.to_thread(_run))
                cancel_task = (
                    asyncio.create_task(cancel_event.wait())
                    if cancel_event is not None
                    else None
                )

                tasks = [run_task]
                if cancel_task is not None:
                    tasks.append(cancel_task)

                done, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )

                cancelled = cancel_task is not None and cancel_task in done

                if cancelled:
                    for t in pending:
                        t.cancel()
                    # The worker thread cannot be killed from here; let it finish
                    # in the background. We just report cancellation.
                    return make_error_response(
                        message="run_cmd: command cancelled by user.",
                        usage=zero_usage(),
                    )

                # run_task finished (success or timeout)
                for t in pending:
                    t.cancel()

                try:
                    result = run_task.result()
                except subprocess.TimeoutExpired as e:
                    return make_error_response(
                        message=f"run_cmd: command timed out after {timeout}ms. "
                                "If this command is expected to take longer, retry with a larger timeout.",
                        usage=zero_usage(),
                    )

                stdout_s = result.stdout or ""
                stderr_s = result.stderr or ""

                output = stdout_s
                if stderr_s:
                    output += "\n" + stderr_s

                MAX_BYTES = 50 * 1024
                truncated = len(output.encode("utf-8")) > MAX_BYTES
                if truncated:
                    tail = output[-MAX_BYTES:]
                    output = f"...output truncated...\n\n{tail}"

                if result.returncode != 0:
                    return make_error_response(
                        message=(
                            f"Command failed with exit code {result.returncode}: "
                            f"{(output.strip() or '(no output)')[-2000:]}"
                        ),
                        usage=zero_usage(),
                    )

                return make_success_response(
                    message="Command executed.",
                    data={
                        "output": output or "(no output)",
                        "returncode": result.returncode,
                        "truncated": truncated,
                        "workdir": cwd,
                    },
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in run_cmd: %s", e)
                return make_error_response(
                    message=f"Error executing command: {e}",
                    usage=zero_usage(),
                )
