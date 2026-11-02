"""Shared visual language for native workspace drawers.

Keep these surfaces aligned with the console and usage workspace CSS. All
decoration is static; opening a drawer does not add animation or polling work.
"""
from dataclasses import dataclass
from PySide6.QtWidgets import QStackedWidget

from dock_twoo.ui.theme import ThemeTokens
from dock_twoo.icons import get_icons_dir


class CurrentPageStack(QStackedWidget):
    """Let the active page size itself without inheriting hidden-page minima."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(lambda _index: self.updateGeometry())

    def sizeHint(self):
        page = self.currentWidget()
        return page.sizeHint() if page is not None else super().sizeHint()

    def minimumSizeHint(self):
        page = self.currentWidget()
        return page.minimumSizeHint() if page is not None else super().minimumSizeHint()

    def hasHeightForWidth(self):
        # A scroll area treats heightForWidth as a compulsory content height.
        # The page layouts already wrap their labels and distribute the available
        # height; don't force their preferred height over a smaller viewport.
        return False


@dataclass
class WorkspaceTokens(ThemeTokens):
    surface_alt: str
    accent_fill: str
    accent_text: str
    hover: str
    success: str
    danger: str


def get_workspace_tokens(config):
    dark = config.get_effective_theme() == 'dark'
    dock_bg = config.get_effective_dock_bg() if dark else '#f4f6fa'
    return WorkspaceTokens(
        font_family=config.font_family, font_size_root=config.font_size_root,
        font_size_tooltip=config.font_size_tooltip, font_size_title=22,
        bg_color=dock_bg,
        card_bg='#18181c' if dark else '#ffffff',
        border_color='rgba(255, 255, 255, 0.10)' if dark else '#dce3ed',
        text_primary='#ededf2' if dark else '#1c293c',
        text_secondary='#90909c' if dark else '#62748b',
        accent_color='#79b5ff' if dark else '#2269cf',
        surface_alt='#141416' if dark else '#edf1f7',
        accent_fill='rgba(255, 255, 255, 0.08)' if dark else '#e7f0ff',
        accent_text='#ffffff' if dark else '#ffffff',
        hover='rgba(255, 255, 255, 0.06)' if dark else '#edf3fc',
        success='#75d6b0' if dark else '#187858',
        danger='#f7a3a8' if dark else '#b73549',
    )



def workspace_styles(config):
    p = get_workspace_tokens(config)
    arrows = get_icons_dir().as_posix()
    return f'''
        QWidget {{ color: {p.text_primary}; font-size: {p.font_size_root}px; }}
        QWidget#workspaceApp, QWidget#workspaceContent, QStackedWidget,
        QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
        QLabel {{ background: transparent; border: none; color: {p.text_primary}; }}
        QLabel[role="muted"] {{ color: {p.text_secondary}; font-size: 12px; }}
        QLabel[role="section"] {{ color: {p.text_secondary}; font-size: 11px; font-weight: 600; }}
        QLabel[role="title"] {{ font-size: 22px; font-weight: 600; }}
        QLabel[role="itemTitle"] {{ font-size: 14px; font-weight: 600; }}
        QLabel[role="panelTitle"] {{ font-size: 18px; font-weight: 600; }}
        QLabel[role="metric"] {{ font-size: 25px; font-weight: 600; }}
        QLabel[role="success"] {{ color: {p.success}; }}
        QLabel[role="danger"] {{ color: {p.danger}; }}
        QFrame[role="card"] {{ background: {p.card_bg}; border: 1px solid {p.border_color}; border-radius: 12px; }}
        QFrame[role="card"][selected="true"] {{ background: {p.accent_fill}; border-color: {p.accent_color}; }}
        QFrame[role="subtle"] {{ background: {p.surface_alt}; border: 1px solid {p.border_color}; border-radius: 10px; }}
        QFrame[role="divider"] {{ background: {p.border_color}; border: none; max-height: 1px; }}
        QPushButton, QToolButton {{
            background: {p.card_bg}; color: {p.text_primary}; border: 1px solid {p.border_color};
            border-radius: 9px; padding: 9px 12px; min-height: 20px; font-weight: 500;
        }}
        QPushButton:hover, QToolButton:hover {{ background: {p.hover}; border-color: {p.text_secondary}; }}
        QPushButton:pressed, QToolButton:pressed {{ background: {p.accent_fill}; }}
        QPushButton:focus, QToolButton:focus {{ border-color: {p.accent_color}; }}
        QPushButton:disabled, QToolButton:disabled {{ color: {p.text_secondary}; background: {p.surface_alt}; border-color: {p.border_color}; }}
        QPushButton[role="primary"] {{ background: {p.accent_color}; color: {p.accent_text}; border-color: {p.accent_color}; font-weight: 600; }}
        QPushButton[role="primary"]:hover {{ background: {p.accent_fill}; color: {p.accent_color}; }}
        QPushButton[role="danger"] {{ color: {p.danger}; }}
        QPushButton[role="quiet"], QToolButton[role="quiet"] {{ background: transparent; border-color: transparent; color: {p.text_secondary}; }}
        QPushButton[role="quiet"]:hover, QToolButton[role="quiet"]:hover {{ background: {p.hover}; color: {p.text_primary}; }}
        QPushButton:checked, QToolButton:checked {{ background: {p.accent_fill}; color: {p.accent_color}; border-color: {p.accent_color}; }}
        QPushButton[role="icon"], QToolButton[role="icon"] {{ padding: 0; min-height: 0; border-radius: 9px; }}
        QLineEdit, QTextEdit, QPlainTextEdit, QTextBrowser, QComboBox, QDateEdit, QTimeEdit, QDateTimeEdit, QSpinBox {{
            color: {p.text_primary}; background: {p.card_bg}; border: 1px solid {p.border_color};
            border-radius: 9px; padding: 9px 11px; min-height: 20px;
            selection-background-color: {p.accent_fill}; selection-color: {p.text_primary};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
        QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus {{ border-color: {p.accent_color}; }}
        QLineEdit:disabled, QComboBox:disabled {{ color: {p.text_secondary}; background: {p.surface_alt}; }}
        QComboBox {{ padding-right: 28px; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox::down-arrow, QDateEdit::down-arrow, QDateTimeEdit::down-arrow, QTimeEdit::down-arrow, QSpinBox::down-arrow {{ image: url("{arrows}/chevron-down.svg"); width: 12px; height: 8px; }}
        QDateEdit::up-arrow, QDateTimeEdit::up-arrow, QTimeEdit::up-arrow, QSpinBox::up-arrow {{ image: url("{arrows}/chevron-up.svg"); width: 12px; height: 8px; }}
        QDateEdit, QDateTimeEdit, QTimeEdit, QSpinBox {{ padding-right: 27px; }}
        QDateEdit::drop-down, QDateTimeEdit::drop-down {{ border: none; width: 24px; }}
        QDateEdit::up-button, QDateTimeEdit::up-button, QTimeEdit::up-button, QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 24px; height: 19px; border: none; background: transparent; }}
        QDateEdit::down-button, QDateTimeEdit::down-button, QTimeEdit::down-button, QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; height: 19px; border: none; background: transparent; }}
        QComboBox QAbstractItemView {{ background: {p.card_bg}; color: {p.text_primary}; border: 1px solid {p.border_color}; selection-background-color: {p.accent_fill}; padding: 6px; outline: none; }}
        QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 3px 8px; }}
        QCalendarWidget QWidget {{ background: {p.card_bg}; color: {p.text_primary}; }}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {p.surface_alt}; }}
        QCalendarWidget QAbstractItemView {{ background: {p.card_bg}; alternate-background-color: {p.surface_alt}; color: {p.text_primary}; selection-background-color: {p.accent_fill}; selection-color: {p.text_primary}; border: none; outline: none; }}
        QCalendarWidget QAbstractItemView:disabled {{ color: {p.text_secondary}; }}
        QCalendarWidget QToolButton {{ color: {p.text_primary}; background: transparent; border: none; padding: 4px 6px; min-height: 22px; }}
        QCalendarWidget QToolButton:hover {{ background: {p.accent_fill}; }}
        QCalendarWidget QToolButton#qt_calendar_prevmonth {{ qproperty-icon: url("{arrows}/chevron-left.svg"); }}
        QCalendarWidget QToolButton#qt_calendar_nextmonth {{ qproperty-icon: url("{arrows}/chevron-right.svg"); }}
        QCalendarWidget QSpinBox {{ background: {p.card_bg}; color: {p.text_primary}; padding: 3px 22px 3px 5px; }}
        QCheckBox {{ color: {p.text_primary}; spacing: 8px; background: transparent; }}
        QCheckBox::indicator {{ width: 16px; height: 16px; }}
        QListWidget, QTreeWidget {{ background: transparent; border: none; outline: none; padding: 0; }}
        QListWidget::item, QTreeWidget::item {{ border-radius: 8px; }}
        QListWidget::item:selected, QTreeWidget::item:selected {{ background: {p.accent_fill}; color: {p.text_primary}; }}
        QScrollBar:vertical {{ background: transparent; width: 7px; margin: 2px 0; border: none; }}
        QScrollBar:horizontal {{ background: transparent; height: 7px; margin: 0 2px; border: none; }}
        QScrollBar::handle {{ background: {p.border_color}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
        QScrollBar::handle:hover {{ background: {p.text_secondary}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; border: none; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
        QToolTip {{ background: {p.card_bg}; color: {p.text_primary}; border: 1px solid {p.border_color}; padding: 7px; }}
        QMenu {{ background: {p.card_bg}; color: {p.text_primary}; border: 1px solid {p.border_color}; padding: 6px; }}
        QMenu::item {{ padding: 8px 22px 8px 12px; border-radius: 6px; }}
        QMenu::item:selected {{ background: {p.accent_fill}; color: {p.accent_color}; }}
    '''
