"""Single-instance guard over a per-user local socket (named pipe; never touches the network)."""

from __future__ import annotations

import getpass
import re

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from eye_break import APP_ID


def server_name(suffix: str = "") -> str:
    user = re.sub(r"[^A-Za-z0-9_-]", "_", getpass.getuser())
    return f"{APP_ID}-{user}{suffix}"


def send(name: str, message: bytes) -> bool:
    """Deliver a message to a running instance. Returns False when none is running."""
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(500):
        return False
    socket.write(message)
    socket.flush()
    socket.waitForBytesWritten(500)
    socket.disconnectFromServer()
    return True


class SingleInstance(QObject):
    """`is_primary()` claims the instance; later launches send "show" (or "quit") to it."""

    activation_requested = Signal()
    quit_requested = Signal()

    def __init__(self, name: str | None = None) -> None:
        super().__init__()
        self.name = name or server_name()
        self.server: QLocalServer | None = None

    def is_primary(self, message: bytes = b"show") -> bool:
        if send(self.name, message):
            return False
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self.server.listen(self.name):
            # A stale pipe from a crashed instance: remove and retry once.
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                return True  # cannot guard; still run rather than refuse to start
        self.server.newConnection.connect(self._on_connection)
        return True

    def _on_connection(self) -> None:
        assert self.server is not None
        while self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            # Handlers attach before control returns to the event loop; data already buffered is read now.
            conn.readyRead.connect(lambda c=conn: self._read(c))
            conn.disconnected.connect(conn.deleteLater)
            if conn.bytesAvailable():
                self._read(conn)

    def _read(self, conn: QLocalSocket) -> None:
        data = bytes(conn.readAll()).strip()
        if data == b"quit":
            self.quit_requested.emit()
        elif data:
            self.activation_requested.emit()

    def close(self) -> None:
        """Stop listening and drop accepted connections so no queued signal outlives this object."""
        if not self.server:
            return
        self.server.newConnection.disconnect(self._on_connection)
        for conn in self.server.findChildren(QLocalSocket):
            conn.blockSignals(True)
            conn.abort()
        self.server.close()
