"""Regression for CSS alpha colors accidentally painting black in dark mode."""
import pytest
from PySide6.QtGui import QColor,QPainter,QImage,QRegion
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QPoint
from dock_twoo.config import DockConfig,DockAppItem
from dock_twoo.ui.dock_icon import DockIconButton
from dock_twoo.ui.theme import paint_color


@pytest.mark.parametrize('value,expected',[
    ('rgba(255, 255, 255, 0.16)',(255,255,255,41)),
    ('rgba(0, 0, 0, 0.12)',(0,0,0,31)),
    ('rgb(24, 50, 70)',(24,50,70,255)),
    ('#112233',(17,34,51,255)),
])
def test_theme_paint_colors_preserve_css_alpha(value,expected):
    assert paint_color(value).getRgb()==expected


@pytest.mark.parametrize('theme',['dark','light'])
@pytest.mark.parametrize('state',['active','hover'])
def test_button_highlight_is_visible_against_dock_background(qapp,qtbot,theme,state):
    config=DockConfig(theme_mode=theme,dock_width=72,dock_padding_x=6,icon_size=24)
    button=DockIconButton(DockAppItem(id='keep_awake',name='Keep Awake',icon='coffee',tooltip=''),config)
    qtbot.addWidget(button)
    background=paint_color(config.get_effective_dock_bg())
    def render():
        image=QImage(button.size(),QImage.Format.Format_ARGB32);image.fill(background)
        painter=QPainter(image);button.render(painter,QPoint(),QRegion(),QWidget.RenderFlag.DrawChildren);painter.end();return image
    normal=render()
    button._is_active=state=='active';button._is_hover=state=='hover'
    selected=render()
    # Interior of the circle, away from the glyph and anti-aliased edge.
    x,y=button.width()//2,9
    before,after=normal.pixelColor(x,y),selected.pixelColor(x,y)
    delta=sum(abs(a-b) for a,b in zip(before.getRgb()[:3],after.getRgb()[:3]))
    assert delta>=35
    if state=='active':
        # Active state strengthens the glyph without disappearing into its fill.
        colors=[selected.pixelColor(x,y) for x in range(20,40) for y in range(20,40)]
        if theme=='dark':assert max(c.lightness() for c in colors)>220
        else:assert min(c.lightness() for c in colors)<70


def test_keep_awake_highlight_survives_opening_another_feature(qtbot,tmp_path,monkeypatch):
    from dock_twoo.config import ConfigManager
    from dock_twoo.ui.dock_window import DockWindow
    dock=DockWindow(ConfigManager(config_path=tmp_path/'config.json'));qtbot.addWidget(dock)
    from dock_twoo.keep_awake import get_keep_awake
    monkeypatch.setattr(get_keep_awake(),'status',lambda:{'enabled':True})
    dock._set_active_icon('notes')
    assert dock._icon_buttons['keep_awake']._is_active
    assert dock._icon_buttons['notes']._is_active
    dock._set_active_icon(None)
    assert dock._icon_buttons['keep_awake']._is_active
