"""Cross-platform Qt display selection and one resident dock per selected screen."""
from __future__ import annotations

import hashlib
from collections import Counter

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication


def display_inventory(screens=None, primary=None):
    """Stable hardware identities survive monitor rearrangement and renumbering."""
    screens = list(QGuiApplication.screens() if screens is None else screens)
    primary = QGuiApplication.primaryScreen() if primary is None else primary
    identities = []
    for screen in screens:
        hardware = [str(getattr(screen, field)() or '') for field in ('manufacturer', 'model', 'serialNumber')]
        if hardware[-1].casefold() in ('', '0', 'unknown'):
            hardware.append(screen.name())
        identities.append('|'.join(hardware))
    totals, seen = Counter(identities), Counter()
    connectors = Counter((identity, screen.name()) for identity, screen in zip(identities, screens))
    result = []
    for number, (screen, identity) in enumerate(zip(screens, identities), 1):
        seen[(identity, screen.name())] += 1
        # Some virtual/identical monitors expose no serial or unique connector.
        # An occurrence suffix is the best identity Qt can supply in that case.
        suffix = ('-' + hashlib.sha256(screen.name().encode()).hexdigest()[:8]
                  if totals[identity] > 1 else '')
        if connectors[(identity, screen.name())] > 1:
            suffix += '-' + str(seen[(identity, screen.name())])
        key = 'display-' + hashlib.sha256(identity.encode()).hexdigest()[:20] + suffix
        rect = screen.geometry()
        result.append({'id': key, 'number': number, 'name': screen.name() or f'Display {number}',
                       'primary': screen == primary, 'geometry': [rect.x(), rect.y(), rect.width(), rect.height()],
                       'scale': screen.devicePixelRatio(), 'screen': screen})
    return result


def selected_displays(config, inventory):
    """Keep saved disconnected ids; temporarily fall back to primary if needed."""
    if not inventory:
        return [], False
    mode, ids = config.display_mode, config.display_ids
    if mode == 'all':
        return list(inventory), False
    if not ids:  # Migrate the old single screen_index preference without rewriting it.
        return [inventory[min(max(0, config.screen_index), len(inventory) - 1)]], False
    matches = [entry for entry in inventory if entry['id'] in ids]
    if matches:
        return (matches[:1] if mode == 'single' else matches), False
    return [next((entry for entry in inventory if entry['primary']), inventory[0])], True


class DisplayController(QObject):
    """Own docks only. BrainManager remains the sole audio/agent service owner."""
    def __init__(self, config_manager, brain, *, dock_factory=None, inventory=None):
        super().__init__()
        from dock_twoo.ui.dock_window import DockWindow
        self.config_manager, self.brain = config_manager, brain
        self.dock_factory = dock_factory or DockWindow
        self.inventory_source = inventory or display_inventory
        self.docks = {}
        self.visible = True
        self._closed = False
        self._screens = set()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(100)
        self.refresh_timer.timeout.connect(self.refresh)
        app = QGuiApplication.instance()
        app.screenAdded.connect(self.schedule_refresh)
        app.screenRemoved.connect(self.schedule_refresh)
        app.primaryScreenChanged.connect(self.schedule_refresh)
        config_manager.config_updated.connect(self.refresh)
        self.refresh()

    def schedule_refresh(self, *_):
        if not self._closed:
            self.refresh_timer.start()

    def refresh(self, *_):
        if self._closed:
            return
        config = self.config_manager.config
        inventory = self.inventory_source()
        for entry in inventory:
            screen = entry['screen']
            if screen not in self._screens:
                screen.geometryChanged.connect(self.schedule_refresh)
                screen.availableGeometryChanged.connect(self.schedule_refresh)
                screen.logicalDotsPerInchChanged.connect(self.schedule_refresh)
        self._screens = {entry['screen'] for entry in inventory}
        chosen, fallback = selected_displays(config, inventory)
        ids = {entry['id'] for entry in chosen}
        # Save a JSON-only snapshot for HTTP workers. No QScreen call off GUI thread.
        self.config_manager.display_snapshot = {
            'mode': config.display_mode, 'display_ids': list(config.display_ids), 'fallback': fallback,
            'displays': [{**{k: v for k, v in entry.items() if k != 'screen'}, 'selected': entry['id'] in ids}
                         for entry in inventory]}
        self.brain.configure_displays(chosen, inventory)
        for key in list(self.docks):
            if key not in ids:
                dock = self.docks.pop(key)
                dock.close()
                dock.deleteLater()
        for entry in chosen:
            key = entry['id']
            if key not in self.docks:
                self.docks[key] = self.dock_factory(self.config_manager, screen_id=key,
                                                   screen_index=entry['number'] - 1)
            else:
                self.docks[key].set_display_index(entry['number'] - 1)
            if self.visible:
                self.docks[key].show()

    def isVisible(self):
        return self.visible and bool(self.docks)

    def hide(self):
        self.visible = False
        for dock in self.docks.values():
            dock.hide()
            dock.attached_window.hide_window()

    def show(self):
        self.visible = True
        for dock in self.docks.values():
            dock.show()

    def raise_(self):
        for dock in self.docks.values():
            dock.raise_()

    def _slide_in(self):
        for dock in self.docks.values():
            dock._slide_in()

    def close(self):
        self._closed = True
        self.refresh_timer.stop()
        for dock in self.docks.values():
            dock.close()
