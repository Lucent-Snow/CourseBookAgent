"""Run the suite in disposable storage with real network connections forbidden."""
import os
import ipaddress
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch


def local_only(original):
    def connect(sock, address):
        if sock.family == getattr(socket, "AF_UNIX", None):
            return original(sock, address)
        try:
            allowed = ipaddress.ip_address(address[0]).is_loopback
        except ValueError:
            allowed = False
        if not allowed:
            raise AssertionError("Offline test attempted external network access")
        return original(sock, address)
    return connect


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    with tempfile.TemporaryDirectory(prefix="coursebook-offline-") as tmp:
        os.environ.update({
            "DATA_DIR": tmp, "OUTPUT_DIR": str(Path(tmp) / "output"),
            "LLM_API_KEY": "", "LLM_BASE_URL": "", "LLM_MODEL": "",
            "ZHIYUN_JWT": "", "ZHIYUN_SESSION_FILE": str(Path(tmp) / "session.json"),
        })
        # Windows asyncio creates a loopback socketpair for its event loop.
        with patch.object(socket.socket, "connect", local_only(socket.socket.connect)), \
             patch.object(socket.socket, "connect_ex", local_only(socket.socket.connect_ex)):
            suite = unittest.defaultTestLoader.discover(str(root / "tests"))
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
