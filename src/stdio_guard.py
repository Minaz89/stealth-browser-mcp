"""Guard the MCP stdio transport against stray stdout writes.

Under stdio transport, file descriptor 1 is the JSON-RPC channel. Any
Python-level print() from this repo or a third-party dependency (nodriver
included) lands on that channel, corrupts the protocol framing, and makes
the client drop the connection to protect itself.

Install the guard right before starting the stdio transport. After that,
print() goes to stderr while the transport keeps working, because the
transport wraps the saved stdout buffer, not the replaced sys.stdout.
"""

import sys
from typing import Optional


class TransportSafeStdout:
    """sys.stdout replacement that keeps the stdio transport intact.

    Write calls are routed to stderr. The ``buffer`` attribute still
    exposes the original stdout buffer, so the MCP stdio server, which
    wraps ``sys.stdout.buffer`` at startup, keeps writing framed
    JSON-RPC messages to the real transport.
    """

    def __init__(self, real_stdout):
        """Keep the original stdout and expose its buffer to the transport."""
        self._real_stdout = real_stdout
        try:
            self._transport_buffer = real_stdout.buffer
        except Exception:
            self._transport_buffer = None

    @property
    def buffer(self):
        """Return the original stdout buffer used by the MCP transport."""
        return self._transport_buffer

    def write(self, data) -> int:
        """Route text writes to stderr so stdout stays protocol-clean."""
        try:
            return sys.stderr.write(data)
        except Exception:
            try:
                return len(data)
            except Exception:
                return 0

    def writelines(self, lines) -> None:
        """Route multi-line writes to stderr."""
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        """Flush stderr."""
        try:
            sys.stderr.flush()
        except Exception:
            pass

    @property
    def encoding(self) -> str:
        """Report the original stdout encoding."""
        return getattr(self._real_stdout, "encoding", "utf-8")

    @property
    def errors(self) -> str:
        """Report the original stdout error handling."""
        return getattr(self._real_stdout, "errors", "strict")

    def isatty(self) -> bool:
        """Never claim a terminal; the transport pipe is not interactive."""
        return False

    def fileno(self) -> int:
        """Return the original stdout file descriptor."""
        return self._real_stdout.fileno()

    def __getattr__(self, name):
        """Delegate anything else to the original stdout object."""
        return getattr(object.__getattribute__(self, "_real_stdout"), name)


_guard_installed = False


def install_stdio_guard() -> bool:
    """Replace sys.stdout with the transport-safe proxy.

    Returns:
        bool: True when the guard was installed, False when stdout has
        no usable buffer or the guard is already active.
    """
    global _guard_installed
    if _guard_installed:
        return False
    real_stdout = sys.stdout
    if real_stdout is None or isinstance(real_stdout, TransportSafeStdout):
        return False
    if getattr(real_stdout, "buffer", None) is None:
        return False
    sys.stdout = TransportSafeStdout(real_stdout)
    _guard_installed = True
    return True


def is_guard_active() -> bool:
    """Check whether the stdio guard is currently installed."""
    return _guard_installed and isinstance(sys.stdout, TransportSafeStdout)


def reset_stdio_guard_for_tests(original_stdout: Optional[object] = None) -> None:
    """Restore stdout after a test. Test helper only, not runtime code."""
    global _guard_installed
    if original_stdout is not None:
        sys.stdout = original_stdout
    _guard_installed = False
