"""Native attached dashboard with the same local charts as the settings console."""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QApplication, QLabel
from dock_twoo.ui.apps.base_app import BaseAttachedApp


class DashboardAppWidget(BaseAttachedApp):
    def __init__(self, config, parent=None):
        super().__init__('dashboard', 'Dashboard', config, parent)
        self.view = None
        if QApplication.platformName() == 'offscreen':
            self.content_layout.addWidget(QLabel('Cloud usage dashboard · local charts', self))
            return
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEngineSettings
        self.view = QWebEngineView(self)
        self.view.page().setBackgroundColor(Qt.transparent)
        self.view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.content_layout.addWidget(self.view)
        self._url()

    def _url(self):
        if self.view:
            url=f'http://127.0.0.1:{self.config.server_port}/dashboard.html?theme={self.config.get_effective_theme()}'
            if self.view.url().toString()!=url:self.view.setUrl(QUrl(url))

    def update_config(self, config):
        super().update_config(config)
        self._url()

    def showEvent(self, event):
        if self.view:
            from PySide6.QtWebEngineCore import QWebEnginePage
            self.view.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
            self._url()
        super().showEvent(event)
