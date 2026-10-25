"""Transparent GPU-rendered companion using the editable Blender skeleton."""
from __future__ import annotations

import json
import time
from PySide6.QtCore import QObject, QTimer, QUrl, Qt, Signal, Slot, QFile, QIODevice, QPoint, QRect, QEvent
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineScript, QWebEnginePage
from shiboken6 import isValid


def render_budget(visible_count, nearby=False):
    """Bound the cost of a crowd without slowing the selected character."""
    if nearby or visible_count <= 3:
        return dict(maxFps=30, shapeFps=20, pixelRatio=2)
    return dict(maxFps=24 if visible_count <= 12 else 20,
                shapeFps=6 if visible_count <= 12 else 4, pixelRatio=1)


def listening_aura_allowed(companion):
    """Names identify the listener; status is shown only on its head light."""
    return False


class ModelBridge(QObject):
    loaded = Signal(str, str)
    error = Signal(str)
    shape = Signal(str)

    @Slot(str)
    def silhouette(self, payload):
        self.shape.emit(payload)

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
        from dock_twoo.brain.connectivity import Connectivity
        self.connectivity = Connectivity(self)
        self.ready = False
        self.error = ''
        self.version = ''
        self.asset_hash = ''
        self.attempts = 0
        self._loading = False
        self._sync_pending = False
        self._sync_started = 0.0
        self._epoch = 0
        self._recoveries = 0
        self._reload_pending = False
        self._healthy_since = 0.0
        self.detached = hasattr(companion, 'set_input_shape')
        if self.detached:
            # The complete visual layer (including glow and props) passes all
            # input through. Its owner is an invisible silhouette-shaped window.
            self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                                Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus |
                                Qt.WindowType.WindowTransparentForInput)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            companion.installEventFilter(self)
        self.sync_geometry()
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
        if self.detached:
            self.bridge.shape.connect(companion.set_input_shape)
        self.loadFinished.connect(self._loaded)
        self.renderProcessTerminated.connect(self._renderer_terminated)
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._sync)
        self.hide()
        QTimer.singleShot(800, self, self._load)

    def sync_geometry(self):
        c = self.companion
        self.setGeometry(QRect(c.mapToGlobal(QPoint()), c.size()) if self.detached else c.rect())

    def show_visual(self):
        self.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
        self.sync_geometry()
        self.show()
        if self.ready:
            self.timer.start()
            self._sync()
        elif not self._loading and (not self.error or self._reload_pending):
            QTimer.singleShot(0, self, self._load)
        if self.detached:
            from dock_twoo.brain.mascot import pin_native, mac_window
            pin_native(self)
            # Cocoa's native WebEngine surface can keep accepting input despite
            # the Qt flag. Match the existing click-through reading guide there.
            import platform
            if platform.system() == 'Darwin':
                import ctypes
                window, message = mac_window(self)
                if window and message:
                    message(None, window, 'setIgnoresMouseEvents:', (ctypes.c_bool, True))

    def eventFilter(self, watched, event):
        if watched is self.companion:
            if event.type() in (QEvent.Type.Move, QEvent.Type.Resize):
                self.sync_geometry()
            elif event.type() == QEvent.Type.Hide:
                self.timer.stop()
                self._epoch += 1
                self._sync_pending = False
                self.hide()
                # Hidden WebEngine pages otherwise keep running their RAF,
                # skeleton and GPU readback loops indefinitely.
                self.page().setVisible(False)
                if self.ready:
                    self.page().setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
            elif event.type() == QEvent.Type.Show:
                self.show_visual()
        return super().eventFilter(watched, event)

    def _load(self):
        if self._loading or self.ready or not self.companion.isVisible():
            return
        from dock_twoo.config import ConfigManager
        self._loading = True
        self._reload_pending = False
        self._epoch += 1
        self._sync_pending = False
        self.attempts += 1
        port = ConfigManager().config.server_port
        self.load(QUrl(f'http://127.0.0.1:{port}/brain3d/index.html?embedded&character={self.companion.character_id}'))
        attempt = self.attempts
        QTimer.singleShot(12000, self, lambda: self._check_ready(attempt))

    def _loaded(self, ok):
        if not ok and self.attempts < 5:
            self._loading = False
            QTimer.singleShot(1500, self, self._load)

    def _check_ready(self, attempt=None):
        if attempt is not None and attempt != self.attempts:
            return
        if not self.ready and self._loading:
            self._error(self.error or "The 3D renderer did not become ready; restart Dock to retry.")

    def _ready(self, version, asset_hash):
        self.version = version
        self.asset_hash = asset_hash
        self.companion.setToolTip(f"{self.companion.character_name} {version}")
        self.ready = True
        self._loading = False
        self._reload_pending = False
        self._healthy_since = time.monotonic()
        self.error = ''
        if self.companion.isVisible():
            self.show_visual()
        else:
            # It may have been hidden while its assets were still loading.
            self.page().setVisible(False)
            self.page().setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
        if hasattr(self.companion, 'set_renderer_status'):
            self.companion.set_renderer_status('')
        self.companion.update()

    def _error(self, message):
        self.ready = False
        self._loading = False
        self.error = message
        if not self.detached:
            self.hide()
        elif self.companion.isVisible():
            self.show_visual()
        self.timer.stop()
        if hasattr(self.companion, 'set_renderer_status'):
            self.companion.set_renderer_status(f'{self.companion.character_name} 3D could not load.\nRestart Dock to retry.', error=True)
            self.companion.setToolTip(message)
        self.companion.update()

    def _renderer_terminated(self, _status, _code):
        self._recover_renderer('The character renderer stopped.')

    def _recover_renderer(self, reason):
        # Fail open: a stalled renderer must never leave a stale invisible hit
        # rectangle above the desktop. Rebuild only this character, not the app.
        self._epoch += 1
        self._sync_pending = False
        self._error(reason)
        if self._recoveries < 2:
            self._recoveries += 1
            # Retain the retry if the character is hidden before it runs.
            self._reload_pending = True
            QTimer.singleShot(1000 * self._recoveries, self, self._load)

    def _sync(self):
        c = self.companion
        if not c.isVisible():
            return
        if self._healthy_since and time.monotonic()-self._healthy_since > 60:
            # Bound a crash storm, not the number of recoveries over days of use.
            self._recoveries = 0
        if self._sync_pending:
            if time.monotonic()-self._sync_started > 5:
                self._recover_renderer('The character renderer stopped responding.')
            return
        count=sum(actor.isVisible() for actor in getattr(c.manager,'companions',{}).values())
        nearby=c.geometry().adjusted(-20,-20,20,20).contains(QCursor.pos())
        budget=render_budget(count, nearby or c.activity!='idle')
        self.timer.setInterval(round(1000/budget['maxFps']))
        progress = min(1, max(0, (time.monotonic() - c.motion_started) / max(.01, c.motion_duration)))
        state = dict(**budget, visible=True, online=self.connectivity.online, listeningAuraAllowed=listening_aura_allowed(c), reducedMotion=c.reduced_motion, action=c.action or 'idle', yaw=c._yaw, progress=progress,
                     distance=c.gait_distance, blink=c.blink_amount,
                     mouth=c.mouth_level if c.activity == 'speaking' else 0,
                     gazeX=max(-1, min(1, c._gaze_offset.x() / .018)),
                     gazeY=max(-1, min(1, c._gaze_offset.y() / .014)), activity=c.activity)
        # One outstanding update per view. A delayed renderer used to accumulate
        # thirty more IPC requests every second, including obsolete poses.
        self._sync_pending = True
        self._sync_started = time.monotonic()
        epoch = self._epoch
        def acknowledged(_value):
            if isValid(self) and self._epoch == epoch:
                self._sync_pending = False
        self.page().runJavaScript('window.setBrainState && window.setBrainState(' + json.dumps(state) + ')', acknowledged)
