"""TCP/IP protocol definitions for blzbak client-daemon communication.

Messages are length-prefixed JSON over TCP:
  [4-byte big-endian uint32: payload length][UTF-8 JSON payload]
"""

import json
import struct

PROTOCOL_VERSION = 1
DEFAULT_PORT = 7890

_HEADER_FORMAT = "!I"   # network byte order, unsigned 32-bit int
HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)


class Command:
    PING             = "PING"
    TEST             = "TEST"
    PREPARE_BACKUP   = "PREPARE_BACKUP"
    BACKUP_COMPLETE  = "BACKUP_COMPLETE"
    LIST_SETS        = "LIST_SETS"
    LIST_SNAPSHOTS   = "LIST_SNAPSHOTS"
    LIST_FILES       = "LIST_FILES"


def encode_message(data: dict) -> bytes:
    """Encode a dict as a length-prefixed JSON message."""
    payload = json.dumps(data).encode("utf-8")
    header = struct.pack(_HEADER_FORMAT, len(payload))
    return header + payload


def decode_message(data: bytes) -> dict:
    """Decode a raw JSON payload (no header) into a dict."""
    return json.loads(data.decode("utf-8"))


def pack_header(length: int) -> bytes:
    return struct.pack(_HEADER_FORMAT, length)


def unpack_header(data: bytes) -> int:
    return struct.unpack(_HEADER_FORMAT, data)[0]
