# ============================================================
#  Shared test bootstrap.
#  Every test module imports this FIRST: it points the app at a
#  throwaway data folder before database.py computes its DB path.
# ============================================================

import json
import os
import shutil
import socket
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TMP_DIR = tempfile.mkdtemp(prefix="azcafe_tests_")
os.environ["AZCAFE_DATA_DIR"] = TMP_DIR

import database as db          # noqa: E402  (import after the env var)


def reset_db():
    """Delete and recreate the database file between tests."""
    for name in os.listdir(TMP_DIR):
        if name.startswith("azcafe.db"):
            try:
                os.remove(os.path.join(TMP_DIR, name))
            except OSError:
                pass
    db.init_db()


def cleanup_tmp():
    shutil.rmtree(TMP_DIR, ignore_errors=True)


class DBTestCase(unittest.TestCase):
    def setUp(self):
        reset_db()


class FakeSock:
    """Stands in for a client socket; records every message sent."""

    def __init__(self):
        self.messages = []
        self.closed = False

    def sendall(self, data: bytes):
        for line in data.decode("utf-8").splitlines():
            if line.strip():
                self.messages.append(json.loads(line))

    def close(self):
        self.closed = True

    def recv(self, _size):                     # pragma: no cover - not used
        raise socket.timeout()

    # ── test helpers ─────────────────────────────────────────
    def types(self):
        return [m["type"] for m in self.messages]

    def last(self, msg_type):
        for message in reversed(self.messages):
            if message["type"] == msg_type:
                return message["data"]
        return None

    def clear(self):
        self.messages.clear()


def make_server(**kwargs):
    """A server object with threads stopped (no listen loop)."""
    from server.server_core import AZCafeServer
    server = AZCafeServer(**kwargs)
    return server


def connect_pc(server, pc_name: str, sock: FakeSock = None):
    """Register a fake client and return its ClientConnection."""
    from server.server_core import ClientConnection
    sock = sock or FakeSock()
    client = ClientConnection(sock, ("127.0.0.1", 12345), pc_name=pc_name)
    client.pc_name = pc_name
    server._on_register(client, {"pc_name": pc_name})
    return client
