"""TCP/IP client for communicating with the blzbak server daemon.

Connection lifecycle:
    with DaemonClient(host, port) as client:
        client.prepare_backup("myset")
        ...

Or manually:
    client = DaemonClient(host, port)
    client.connect()
    try:
        ...
    finally:
        client.disconnect()
"""

import logging
import socket
from typing import Any, Optional

from .protocol import (
    Command, HEADER_SIZE, encode_message, decode_message, unpack_header
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT  = 30.0
PREPARE_TIMEOUT  = 300.0   # diff + C→O sync can be slow for large datasets


class DaemonError(Exception):
    """Raised when the daemon returns a status='error' response."""


class DaemonClient:
    """Synchronous TCP client for the blzbak daemon protocol."""

    def __init__(self, host: str, port: int, timeout: float = DEFAULT_TIMEOUT):
        self.host    = host
        self.port    = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
        except (ConnectionRefusedError, TimeoutError, OSError) as exc:
            sock.close()
            raise ConnectionError(
                f"Cannot connect to blzbak daemon at {self.host}:{self.port}: {exc}"
            ) from exc
        self._sock = sock
        logger.debug("Connected to daemon at %s:%d", self.host, self.port)

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
            logger.debug("Disconnected from daemon")

    def __enter__(self) -> "DaemonClient":
        self.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Low-level framed I/O
    # ------------------------------------------------------------------

    def _send(self, data: dict) -> None:
        if not self._sock:
            raise RuntimeError("Not connected to daemon")
        self._sock.sendall(encode_message(data))

    def _recv_exactly(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed by daemon")
            buf.extend(chunk)
        return bytes(buf)

    def _recv(self) -> dict:
        if not self._sock:
            raise RuntimeError("Not connected to daemon")
        header  = self._recv_exactly(HEADER_SIZE)
        msg_len = unpack_header(header)
        body    = self._recv_exactly(msg_len)
        return decode_message(body)

    def _request(self, data: dict, timeout: Optional[float] = None) -> dict:
        """Send a request and return the response dict.

        Raises DaemonError if the server returns status='error'.
        Temporarily overrides socket timeout when *timeout* is given.
        """
        if timeout is not None and self._sock:
            self._sock.settimeout(timeout)
        try:
            self._send(data)
            response = self._recv()
        finally:
            if timeout is not None and self._sock:
                self._sock.settimeout(self.timeout)

        if response.get("status") == "error":
            raise DaemonError(response.get("message", "Unknown daemon error"))
        return response

    # ------------------------------------------------------------------
    # Protocol commands
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        try:
            resp = self._request({"cmd": Command.PING})
            return resp.get("status") == "ok"
        except Exception as exc:
            logger.debug("Ping failed: %s", exc)
            return False

    def test(self) -> dict:
        """Request test/diagnostic information from the daemon.

        Returns daemon configuration, storage info, and health status.
        """
        return self._request({"cmd": Command.TEST})

    def prepare_backup(self, set_name: str) -> dict:
        """Signal the daemon to prepare for a new backup.

        The daemon will:
          1. Create a diff archive capturing changes between C and O.
          2. Sync O to match C (making them identical).
          3. Return {"status": "ok"} when the server is ready for rsync.

        Uses an extended timeout because the diff + sync can be slow.
        """
        logger.info("Requesting backup preparation for '%s'", set_name)
        return self._request(
            {"cmd": Command.PREPARE_BACKUP, "set_name": set_name},
            timeout=PREPARE_TIMEOUT,
        )

    def backup_complete(self, set_name: str) -> dict:
        """Notify the daemon that the rsync transfer has finished."""
        return self._request({"cmd": Command.BACKUP_COMPLETE, "set_name": set_name})

    def list_sets(self) -> list[dict]:
        resp = self._request({"cmd": Command.LIST_SETS})
        return resp.get("sets", [])

    def list_snapshots(self, set_name: str) -> list[dict]:
        resp = self._request({"cmd": Command.LIST_SNAPSHOTS, "set_name": set_name})
        return resp.get("snapshots", [])

    def list_files(
        self, set_name: str, snapshot: str = "C", path: str = "/"
    ) -> list[dict]:
        resp = self._request({
            "cmd": Command.LIST_FILES,
            "set_name": set_name,
            "snapshot": snapshot,
            "path": path,
        })
        return resp.get("files", [])
