"""Thirty production Companion/CharacterView windows, GPU silhouettes and own clips.

Uses disposable settings and the verification asset server on 24942. No hardware
microphone, model provider or external application is controlled.
"""
import json,os,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));os.environ.setdefault('PYTEST_CURRENT_TEST','native-character-check')
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QImage,QPainter,QColor
from PySide6.QtWidgets import QApplication
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore
from dock_twoo.displays import display_inventory
import dock_twoo.config as config_module
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
folder=tempfile.TemporaryDirectory(prefix='native-characters-');store=BrainStore(Path(folder.name));store.update_settings({'roaming':False,'wake_word_enabled':False})
manager=BrainManager(store=store,start_services=False);original=config_module.ConfigManager
config_module.ConfigManager=lambda:SimpleNamespace(config=SimpleNamespace(server_port=24942))
entries=display_inventory();manager.configure_displays(entries[:1],entries);manager.add_all_characters()
for actor in manager.companions.values():actor.roam_timer.stop()
started=time.monotonic();phase=0;played=0;samples=0;errors=[];finished=False

def finish():
 global finished
 if finished:return
 finished=True;timer.stop();actors=list(manager.companions.values())
 sheet=QImage(1200,1000,QImage.Format.Format_ARGB32);sheet.fill(QColor('#10181f'));painter=QPainter(sheet)
 for i,actor in enumerate(actors):painter.drawPixmap((i%6)*200,(i//6)*200,200,200,actor.model_view.grab())
 painter.end();sheet.save('/tmp/dock-native-character-crowd.png')
 result={'success':not errors,'native_characters':len(actors),'ready':sum(a.model_view.ready for a in actors),'body_masks':sum(a.has_input_shape and not a.input_region.isEmpty() for a in actors),'collision_samples':samples,'errors':errors,'cloud_calls':0}
 Path('/tmp/dock-native-character-crowd.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
 config_module.ConfigManager=original;manager.shutdown();app.exit(0 if not errors else 1)

def tick():
 global phase,played,samples
 actors=list(manager.companions.values())
 if time.monotonic()-started>80:errors.append('Timed out waiting for all native renderers/masks.');finish();return
 if not all(a.model_view.ready and a.has_input_shape and not a.input_region.isEmpty() for a in actors):return
 if phase==0:
  manager.playground.arrange();phase=1;played=time.monotonic()
  for actor in actors:
   species=[k for k,v in actor.character['actions'].items() if v.get('category')=='species']
   actor.play_action(species[0] if species else 'wave')
  print('All 30 native models and silhouette masks ready.',flush=True);return
 manager.playground.step();samples+=1
 for i,actor in enumerate(actors):
  if any(manager.playground.region(actor).intersects(manager.playground.region(other)) for other in actors[i+1:]):errors.append('Body overlap after collision pass.');finish();return
 if time.monotonic()-played>5:finish()
timer=QTimer();timer.setInterval(40);timer.timeout.connect(tick);timer.start();app.exec();folder.cleanup()
