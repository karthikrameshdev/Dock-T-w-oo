"""Transparent margins and gaps never become input or body collision geometry."""
import base64
import json

import pytest
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QRegion

from dock_twoo.brain.input_shape import decode_shape, native_mask
from tests.test_multi_brain import manager_at, inventory


def test_native_pointer_gate_skips_a_destroyed_character(qapp):
    from PySide6.QtCore import QObject
    from PySide6.QtWidgets import QWidget
    from shiboken6 import delete
    from dock_twoo.brain.native_input import NativeInputRouter
    manager = QObject()
    actor = QWidget()
    manager.companions = {'removed': actor}
    router = NativeInputRouter(manager)
    router.timer.stop()
    delete(actor)
    router.enabled = True
    router.sync(QPoint(10, 10), force=True)
    assert router._states == {}
    router.close()


def payload(size, rects):
    stride=((size.width()+31)//32)*4
    bits=bytearray(stride*size.height())
    for rect in rects:
        for y in range(rect.top(),rect.bottom()+1):
            for x in range(rect.left(),rect.right()+1):
                bits[y*stride+x//8] |= 128>>(x%8)
    return json.dumps({'width':size.width(),'height':size.height(),'bits':base64.b64encode(bits).decode()})


def test_bitmap_preserves_outer_border_and_interior_gaps(qapp):
    size=QSize(64,64);head=QRect(18,4,28,20);left=QRect(20,26,8,30);right=QRect(36,26,8,30)
    region=decode_shape(payload(size,[head,left,right]),size)
    assert region.xored(QRegion(head)|QRegion(left)|QRegion(right)).isEmpty()
    assert not region.contains(QPoint(3,20))  # Canvas margin.
    assert not region.contains(QPoint(32,50))  # Gap between the legs.
    assert region.contains(QPoint(25,50)) and region.contains(QPoint(32,12))


def test_loading_and_empty_pose_do_not_restore_a_rectangular_native_mask(qapp):
    assert not native_mask(QRegion()).isEmpty()
    assert not native_mask(QRegion()).intersects(QRect(0,0,264,268))


@pytest.mark.parametrize('data',[
    {'width':-1,'height':64,'bits':''}, {'width':2048,'height':2048,'bits':''},
    {'width':64,'height':64,'bits':'invalid'}, {'width':64,'height':64,'bits':''},
    {'width':32,'height':64,'bits':''},
])
def test_malformed_and_pre_resize_bitmaps_are_rejected(qapp,data):
    with pytest.raises(ValueError):decode_shape(json.dumps(data),QSize(64,64))


def test_resize_keeps_a_scaled_outline_and_rejects_old_frames(qapp,tmp_path):
    manager=manager_at(tmp_path,inventory()[:1]);actor=manager.companion
    shape=payload(actor.size(),[QRect(80,20,80,220)])
    actor.set_input_shape(shape)
    actor.set_character_scale(.5)
    assert actor.input_region.contains(QPoint(50,30))
    assert not actor.input_region.contains(QPoint(5,30))
    previous=QRegion(actor.input_region)
    actor.set_input_shape(shape)
    assert actor.input_region==previous and actor.mask()==previous
    manager.shutdown()


def test_overlapping_canvases_allow_nearby_bodies_but_prevent_body_overlap(qapp,tmp_path):
    manager=manager_at(tmp_path,inventory()[:1]);first=manager.companion;second=manager.add_brain()
    for actor in (first,second):actor.set_input_shape(payload(actor.size(),[QRect(80,20,80,220)]))
    first.move(100,100);second.move(200,100)
    assert first.geometry().intersects(second.geometry())
    assert not manager.playground.region(first).intersects(manager.playground.region(second))
    assert manager.playground.constrain_step(first,QPoint(110,100))==QPoint(110,100)
    stopped=manager.playground.constrain_step(first,QPoint(190,100))
    assert not manager.playground.region(first,stopped).intersects(manager.playground.region(second))
    second.move(first.pos());manager.playground.step()
    assert not manager.playground.region(first).intersects(manager.playground.region(second))
    manager.shutdown()


def test_native_pointer_gate_preserves_gaps_and_drag_capture(qapp,tmp_path,monkeypatch):
    manager=manager_at(tmp_path,inventory()[:1]);actor=manager.companion
    actor.move(100,100);actor.set_input_shape(payload(actor.size(),[QRect(80,20,80,80),QRect(80,120,25,100),QRect(135,120,25,100)]))
    calls=[]
    monkeypatch.setattr('dock_twoo.brain.mascot.mac_window',lambda _: (1,lambda *args:calls.append(args[-1][1])))
    router=manager.input_router;router.enabled=True
    router.sync(QPoint(110,150), force=True);assert calls[-1] is True  # Refresh a possibly timer-cached margin.
    router.sync(QPoint(220,150));assert calls[-1] is False  # The head.
    router.sync(QPoint(220,250));assert calls[-1] is True  # Between the legs.
    before=len(calls);router.sync(QPoint(220,250));assert len(calls)==before
    actor.origin=QPoint();router.sync(QPoint(110,150));assert calls[-1] is False
    actor.origin=None;router.sync(QPoint(110,150));assert calls[-1] is True
    router.enabled=False;manager.shutdown()


def test_scaling_a_loading_character_keeps_a_region_not_an_ambiguous_empty_polygon(qapp,tmp_path):
    manager=manager_at(tmp_path,inventory()[:1]);actor=manager.companion
    assert actor.input_region.isEmpty()
    actor.set_character_scale(.5)
    assert isinstance(actor.input_region,QRegion)
    assert not actor.input_region.contains(QPoint(5,5))
    manager.shutdown()
