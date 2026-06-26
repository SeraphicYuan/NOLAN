"""Claude CLI runner — replaces direct LLM API calls.

Routes agent invocations through the local `claude --print` CLI with stream-JSON
output, so NOLAN's orchestrator uses the user's Claude Code subscription
instead of per-token billing AND captures intermediate events for the agents
webUI live-output panel.

Two tiers:

- **`run_one_shot()`**: subprocess `claude --print --output-format stream-json
  --include-partial-messages` with stdin user message and a specialized system
  prompt. Reads events line-by-line as they arrive, tees them to an optional
  stream log, extracts the final assistant text from the `result` event.

- **`run_persistent()`** (deferred): tmux-backed long-lived session for
  `--live` Director mode and `tweak_loop` interactive iteration. Borrows the
  SPARTA pattern. Stub raises NotImplementedError until the use case is built.

See docs/plans/2026-04-26-two-layer-orchestrator.md §6.2 / §6.3.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TIMEOUT_SECONDS = 1800  # 30 min — adapt-style on a 9:50 essay took ~17 min
CLEANUP_TIMEOUT_SECONDS = 5.0
STREAM_READ_LIMIT_BYTES = 16 * 1024 * 1024  # 16 MiB per line — stream-json events can be large


@dataclass
class AgentResult:
    text: str
    elapsed_seconds: float
    return_code: int
    event_count: int = 0


class ClaudeRunnerError(RuntimeError):
    pass


def _resolve_claude_argv_prefix() -> list[str]:
    """Return argv prefix for invoking Claude CLI, honoring NOLAN_CLAUDE_BINARY.

    Two forms accepted:

    - Plain path: `NOLAN_CLAUDE_BINARY=/path/to/claude` or
      `NOLAN_CLAUDE_BINARY=C:\\path\\to\\claude.CMD`. Used directly.
    - WSL path: `NOLAN_CLAUDE_BINARY=wsl:/home/user/.local/bin/claude`.
      Wrapped via `wsl.exe -e <path>` so a Windows-side Python process can
      invoke a Linux-side Claude CLI binary. Required on this machine to use
      the up-to-date WSL claude (2.1.119) instead of an older Windows npm
      install (2.1.45) that silently ignores `--dangerously-skip-permissions`.

    Default (no env var): plain `shutil.which("claude")` from PATH.
    """
    override = os.environ.get("NOLAN_CLAUDE_BINARY")
    if override:
        if override.startswith("wsl:"):
            wsl_binary = override[len("wsl:"):]
            wsl_exe = shutil.which("wsl.exe") or shutil.which("wsl")
            if not wsl_exe:
                raise ClaudeRunnerError(
                    "NOLAN_CLAUDE_BINARY uses wsl: prefix but wsl.exe was "
                    "not found on PATH."
                )
            return [wsl_exe, "-e", wsl_binary]
        return [override]

    binary = shutil.which("claude")
    if not binary:
        raise ClaudeRunnerError(
            "Claude CLI not found on PATH. Install Claude Code or set "
            "NOLAN_CLAUDE_BINARY."
        )
    return [binary]


def is_wsl_mode() -> bool:
    """True when the runner is configured to invoke WSL claude via wsl.exe."""
    return (os.environ.get("NOLAN_CLAUDE_BINARY") or "").startswith("wsl:")


def path_for_agent(p) -> str:
    """Render a path the way the spawned Claude CLI will read it.

    On Windows + WSL-mode runner, translates `D:\\foo\\bar` to `/mnt/d/foo/bar`
    so the Linux-side Claude can fs-access it. Otherwise passes through.
    """
    s = str(p)
    if is_wsl_mode() and len(s) >= 3 and s[1] == ":" and s[2] in ("\\", "/"):
        drive = s[0].lower()
        rest = s[3:].replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return s


def _extract_text_from_event(event: dict) -> str | None:
    """Pull text content out of a stream-json event, if present.

    Looks for:
    - `result` event's top-level `result` field (canonical final text)
    - `assistant` event's message.content[].text (concatenated)
    """
    event_type = event.get("type")
    if event_type == "result" and isinstance(event.get("result"), str):
        return event["result"]
    if event_type == "assistant":
        msg = event.get("message") or {}
        content = msg.get("content") or []
        chunks: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        if chunks:
            return "".join(chunks)
    return None


async def _drain_stream(
    stream: asyncio.StreamReader,
    log_handle,
    on_event,
) -> None:
    """Read JSONL lines, tee to log, dispatch to on_event(parsed_dict)."""
    while True:
        line_bytes = await stream.readline()
        if not line_bytes:
            return
        line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            continue
        if log_handle is not None:
            log_handle.write(line + "\n")
            log_handle.flush()
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        on_event(event)


async def run_one_shot(
    system_prompt: str,
    user_prompt: str,
    cwd: Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    tools: list[str] | None = None,
    permission_mode: str | None = None,
    stream_log_path: Path | None = None,
    extra_args: list[str] | None = None,
) -> AgentResult:
    """Invoke Claude CLI in `--print` mode with stream-json output.

    Args:
        system_prompt: Replaces Claude Code's default system prompt.
        user_prompt: Sent via stdin (multi-KB safe — no argv length issues).
        cwd: Working directory for the spawned process (e.g., project folder).
        timeout_seconds: Hard cap on wall-clock duration. Default 1800 (30 min).
        tools: If provided, restricts available tools to this list (e.g.,
            `["Read", "Glob"]`). If `None`, all built-in tools are available.
            Note: `[]` (empty list) is *not* respected by Claude CLI — built-in
            tools stay on. To truly restrict, pass an explicit non-empty list
            or use `--disallowedTools` via `extra_args`.
        permission_mode: One of `default`, `acceptEdits`, `bypassPermissions`,
            `dontAsk`, `plan`. For agent runs that need to write files without
            human approval, use `bypassPermissions`. Defaults to Claude's
            built-in default (interactive prompts — which deadlock in `--print`
            mode, so callers that need writes MUST set this).
        stream_log_path: If set, every JSONL event is teed to this file as it
            arrives. Used by the agents webUI to render live progress.
        extra_args: Additional CLI flags (e.g., `["--effort", "high"]`).

    Returns:
        AgentResult with assistant text (from `result` event), elapsed seconds,
        return code, event count.

    Raises:
        ClaudeRunnerError on non-zero exit, timeout, or auth failure.
    """
    args = [
        *_resolve_claude_argv_prefix(),
        "--print",
        "--verbose",
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--system-prompt", system_prompt,
    ]

    if tools is not None and len(tools) > 0:
        args.extend(["--tools", ",".join(tools)])

    if permission_mode == "bypassPermissions":
        # `--permission-mode bypassPermissions` flag is observed to NOT actually
        # bypass — Write tools still hit a permission gate. Use the explicit
        # dangerous-skip flag, which SPARTA also relies on. Caller signaled they
        # want full autonomy by asking for bypassPermissions.
        args.append("--dangerously-skip-permissions")
    elif permission_mode:
        args.extend(["--permission-mode", permission_mode])

    if extra_args:
        args.extend(extra_args)

    log_handle = None
    if stream_log_path is not None:
        stream_log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = stream_log_path.open("w", encoding="utf-8")

    final_text: str | None = None
    accumulated_text: list[str] = []
    event_count = 0
    error_event: dict | None = None

    def on_event(event: dict) -> None:
        nonlocal final_text, event_count, error_event
        event_count += 1
        text = _extract_text_from_event(event)
        if text is not None:
            if event.get("type") == "result":
                final_text = text
            else:
                accumulated_text.append(text)
        if event.get("type") == "result" and event.get("subtype") not in (None, "success"):
            error_event = event

    started = asyncio.get_event_loop().time()
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd else None,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
        limit=STREAM_READ_LIMIT_BYTES,
    )

    try:
        try:
            proc.stdin.write(user_prompt.encode("utf-8"))
            await proc.stdin.drain()
        finally:
            proc.stdin.close()

        try:
            await asyncio.wait_for(
                _drain_stream(proc.stdout, log_handle, on_event),
                timeout=timeout_seconds,
            )
            await asyncio.wait_for(proc.wait(), timeout=CLEANUP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=CLEANUP_TIMEOUT_SECONDS)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass
            raise ClaudeRunnerError(
                f"Claude CLI exceeded timeout of {timeout_seconds}s"
            )
        except Exception as exc:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=CLEANUP_TIMEOUT_SECONDS)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass
            raise ClaudeRunnerError(
                f"Stream read failed: {type(exc).__name__}: {exc}"
            ) from exc
    finally:
        if log_handle is not None:
            log_handle.close()

    elapsed = asyncio.get_event_loop().time() - started

    if error_event is not None:
        msg = error_event.get("subtype") or "unknown_error"
        raise ClaudeRunnerError(f"Claude CLI returned error event: {msg}")

    if proc.returncode is not None and proc.returncode != 0:
        stderr_b = await proc.stderr.read()
        stderr_text = stderr_b.decode("utf-8", errors="replace").strip()
        raise ClaudeRunnerError(
            f"Claude CLI returned {proc.returncode}: {stderr_text or '(no stderr)'}"
        )

    text = final_text if final_text is not None else "".join(accumulated_text)
    text = text.strip()

    # Empty text is not an error: tool-only agents (e.g., the slide_designer
    # spec, where output is exclusively Write/Edit calls) legitimately exit
    # with no chat output. The caller validates success via produced artifacts.

    if "Please run /login" in text or text.startswith("Not logged in"):
        raise ClaudeRunnerError(
            "Claude CLI reports not-logged-in. Run `claude` interactively once "
            "to authenticate, then retry."
        )

    return AgentResult(
        text=text,
        elapsed_seconds=round(elapsed, 2),
        return_code=proc.returncode if proc.returncode is not None else -1,
        event_count=event_count,
    )


async def run_persistent(*args, **kwargs):
    """Persistent tmux-backed Claude session (deferred).

    Intended for `--live` Director mode and `tweak_loop`. Will follow the
    SPARTA pattern (tmux session + request/response file IPC). Not built yet.
    """
    raise NotImplementedError(
        "Persistent tmux runner is deferred. "
        "Use run_one_shot for one-shot agents (Director default, specialists)."
    )
