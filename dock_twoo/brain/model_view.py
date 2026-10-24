"""Transparent GPU-rendered companion using the editable Blender skeleton."""
from __future__ import annotations

import json
import time
from PySide6.QtCore import QObject, QTimer, QUrl, Qt, Signal, Slot, QFile, QIODevice
from PySide6.QtGui import QColor
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineScript


class ModelBridge(QObject):
    loaded = Signal(str, str)
    error = Signal(str)

    @Slot(str, str)
    def ready(self, version, asset_hash):
        self.loaded.emit(version, asset_hash)

    @Slot(str)
    def failed(self, message):
        self.error.emit(message)


class CharacterView(QWebEngineView):
    def __init__(self, companion):
        super().__init__(companion)
        self.companion = companion
        self.ready = False
        self.error = ''
        self.version = ''
        self.asset_hash = ''
        self.attempts = 0
        self.setGeometry(companion.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.channel = QWebChannel(self.page())
        self.bridge = ModelBridge(self)
        self.channel.registerObject('brain', self.bridge)
        self.page().setWebChannel(self.channel)
        source = QFile(":/qtwebchannel/qwebchannel.js")
        if not source.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError("Qt WebChannel runtime is unavailable")
        script = QWebEngineScript()
        script.setName("Brain native bridge")
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setSourceCode(bytes(source.readAll()).decode("utf-8"))
        self.page().scripts().insert(script)
        self.bridge.loaded.connect(self._ready)
        self.bridge.error.connect(self._error)
        self.loadFinished.connect(self._loaded)
        QTimer.singleShot(12000, self._check_ready)
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._sync)
        self.hide()
        QTimer.singleShot(800, self._load)

    def _load(self):
        from dock_twoo.config import ConfigManager
        self.attempts += 1
        port = ConfigManager().config.server_port
        self.load(QUrl(f'http://127.0.0.1:{port}/brain3d/index.html?embedded'))

    def _loaded(self, ok):
        if not ok and self.attempts < 5:
            QTimer.singleShot(1500, self._load)

    def _check_ready(self):
        if not self.ready:
            self._error(self.error or "The 3D renderer did not become ready; using the artwork fallback.")

    def _ready(self, version, asset_hash):
        self.version = version
        self.asset_hash = asset_hash
        self.companion.setToolTip(f"Brain {version} · Glossy Blue")
        self.ready = True
        self.error = ''
        self.show()
        self.timer.start()
        self.companion.update()

    def _error(self, message):
        self.ready = False
        self.error = message
        self.hide()
        self.timer.stop()
        self.companion.update()

    def _sync(self):
        c = self.companion
        if not c.isVisible():
            return
        progress = min(1, max(0, (time.monotonic() - c.motion_started) / max(.01, c.motion_duration)))
        state = dict(reducedMotion=c.reduced_motion, action=c.action or 'idle', yaw=c._yaw, progress=progress,
                     distance=c.gait_distance, blink=c.blink_amount,
                     mouth=c.mouth_level if c.activity == 'speaking' else 0,
                     gazeX=max(-1, min(1, c._gaze_offset.x() / .018)),
                     gazeY=max(-1, min(1, c._gaze_offset.y() / .014)), activity=c.activity)
        self.page().runJavaScript('window.setBrainState && window.setBrainState(' + json.dumps(state) + ')')
