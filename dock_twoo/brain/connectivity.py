"""Native OS network reachability; does not probe websites or send user data."""
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkInformation


class Connectivity(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.online = None
        self.backend = None
        if QNetworkInformation.loadDefaultBackend():
            self.backend = QNetworkInformation.instance()
        if self.backend:
            self.backend.reachabilityChanged.connect(self._update)
            self._update(self.backend.reachability())

    def _update(self, reachability):
        if reachability == QNetworkInformation.Reachability.Online:
            online = True
        elif reachability in (QNetworkInformation.Reachability.Disconnected,
                               QNetworkInformation.Reachability.Local,
                               QNetworkInformation.Reachability.Site):
            online = False
        else:
            online = None
        if online != self.online:
            self.online = online
            self.changed.emit()
