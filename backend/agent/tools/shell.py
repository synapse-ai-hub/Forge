"""ShellMixin — native tool shell."""

import asyncio
import logging
import os
import subprocess

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class ShellMixin:
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
                workdir: Working directory for the command. If None, uses project root.

            Returns:
                dict with ``{status, message, data, usage}``.
                ``data`` contains ``output``, ``returncode``, and ``truncated``.
            """
            cancel_event = getattr(self, "_stream_cancel_event", None)
            try:
                cwd = workdir or os.getcwd()
                timeout_s = timeout / 1000

                # Run the blocking subprocess call in a worker thread so the
                # event loop is never blocked. ``subprocess.run`` works on every
                # platform regardless of the event-loop policy (unlike
                # ``asyncio.create_subprocess_shell`` which is unsupported on
                # Windows ``SelectorEventLoop``).
                def _run() -> subprocess.CompletedProcess:
                    return subprocess.run(
                        command,
                        shell=True,
                        cwd=cwd,
                        capture_output=True,
                        text=True,
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
                    log_error(
                        f"run_cmd: command timed out after {timeout}ms",
                        source="tools.py:shell(timeout)",
                    )
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
                log_error(str(e), source="tools.py:shell")
                return make_error_response(
                    message=f"Error executing command: {e}",
                    usage=zero_usage(),
                )
