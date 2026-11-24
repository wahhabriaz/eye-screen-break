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


class SingleInstance(QObject):
    """`is_primary()` claims the instance; secondary launches ask the primary to show itself."""

    activation_requested = Signal()

    def __init__(self, name: str | None = None) -> None:
        super().__init__()
        self.name = name or server_name()
        self.server: QLocalServer | None = None

    def is_primary(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if socket.waitForConnected(500):
            socket.write(b"show")
            socket.flush()
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            return False
        self.server = QLocalServer(self)
        if not self.server.listen(self.name):
            # A stale pipe from a crashed instance: remove and retry once.
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                return True  # cannot guard; still run rather than refuse to start
        self.server.newConnection.connect(self._on_connection)
        return True

    def _on_connection(self) -> None:
        # Any connection from a second launch means "show the window"; no payload parsing needed
        # (the data may arrive before a readyRead handler could be attached).
        assert self.server is not None
        while self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            conn.disconnected.connect(conn.deleteLater)
            conn.disconnectFromServer()
            self.activation_requested.emit()

    def close(self) -> None:
        if self.server:
            self.server.close()
