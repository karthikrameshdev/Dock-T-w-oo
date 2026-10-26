"""On-demand local activity drawer; no renderer or polling until opened."""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QApplication, QLabel

from dock_twoo.ui.apps.base_app import BaseAttachedApp


class LiveTrailAppWidget(BaseAttachedApp):
    def __init__(self, config, parent=None):
        super().__init__('activity', 'Live Trail', config, parent)
        self.view = None
        if QApplication.platformName() == 'offscreen':
            self.content_layout.addWidget(QLabel('Live model calls and agent tasks', self))

    def _url(self):
        if self.view:
            url = QUrl(f'http://127.0.0.1:{self.config.server_port}/live-trail.html?theme={self.config.get_effective_theme()}')
            if self.view.url() != url:
                self.view.setUrl(url)

    def update_config(self, config):
        super().update_config(config)
        if self.isVisible():
            self._url()

    def showEvent(self, event):
        if QApplication.platformName() != 'offscreen':
            from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
            from PySide6.QtWebEngineWidgets import QWebEngineView
            if self.view is None:
                self.view = QWebEngineView(self)
                self.view.page().setBackgroundColor(Qt.transparent)
                self.view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
                self.content_layout.addWidget(self.view)
            self.view.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
            self.view.show()
            self._url()
        super().showEvent(event)

    def hideEvent(self, event):
        if self.view:
            from PySide6.QtWebEngineCore import QWebEnginePage
            self.view.hide()
            self.view.page().setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
        super().hideEvent(event)
