"""Render actual Notes/Vault at narrow and wide widths using only disposable data.

QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/verify_notes_vault_design.py
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication,QEvent,QPoint,QRect
from PySide6.QtWidgets import QApplication,QFrame,QVBoxLayout,QPushButton
from dock_twoo.config import DockConfig
from dock_twoo.ui.apps.notes_app import NotesAppWidget
from dock_twoo.ui.apps.vault_app import VaultAppWidget
from dock_twoo.ui.workspace import get_workspace_tokens
from dock_twoo.vault.auth import VaultAuthManager
from dock_twoo.vault.storage import VaultStorageManager
from dock_twoo.vault.models import VaultItem,VaultStore

app=QApplication([])
app.setQuitOnLastWindowClosed(False)
output=Path('/tmp/dock-notes-vault-design');output.mkdir(exist_ok=True)
results=[]
with tempfile.TemporaryDirectory(prefix='dock-drawer-design-') as folder:
 root=Path(folder)
 VaultAuthManager._ensure_helper_compiled=lambda self:None
 VaultAuthManager.is_biometrics_available=lambda self:False
 # Avoid even looking at the default vault or legacy migration candidates.
 VaultStorageManager._check_and_migrate_legacy=lambda self:None
 for theme in ('dark','light'):
  cfg=DockConfig();cfg.storage_path=str(root/theme);cfg.theme_mode=theme
  notes_dir=cfg.get_notes_dir();notes_dir.mkdir(parents=True,exist_ok=True)
  now=time.time()
  for index,(title,body) in enumerate([
   ('Product launch notes','# Launch checklist\n\nA focused release for a calmer desktop.\n\n- Confirm the onboarding flow\n- Review accessibility\n- Publish the release notes\n\n## Next step\nShare the final build with the team.'),
   ('Ideas worth exploring','A quick capture for the next planning session.\n\nMake room for small improvements that save time every day.'),
   ('Weekly reflection','What went well, what I learned, and what I want to improve next week.')]):
   (notes_dir/f'fixture{index}.json').write_text(json.dumps({'title':title,'body':body,'created_at':now-86400*(index+1),'updated_at':now-3600*index}))
  storage=VaultStorageManager(root/theme/'vault',iterations=1000)
  store=VaultStore()
  for title,username in [('GitHub workspace','demo@example.test'),('Work email','hello@example.test'),('Design tools','design@example.test')]:
   store.add(VaultItem(title=title,username=username,password='Fixture-only-not-a-real-secret'))
  storage.save_vault(store)
  auth=VaultAuthManager(root/theme/'vault');auth.set_pin('2468')
  notes=NotesAppWidget(cfg);vault=VaultAppWidget(cfg,storage=storage,auth_mgr=auth)
  for width,height in ((380,430),(380,620),(600,820)):
   for name,widget,prepare in [
    ('notes',notes,lambda:notes._go_back_to_list()),
    ('note-editor',notes,lambda:notes._open_note('fixture0')),
    ('note-preview',notes,lambda:(notes._open_note('fixture0'),notes._show_preview(True))),
    ('vault-locked',vault,lambda:vault.lock_vault()),
    ('vault-list',vault,lambda:vault._unlock_vault()),
    ('vault-details',vault,lambda:(vault._unlock_vault(),vault._cards[0].toggle_expand())),
    ('vault-form',vault,lambda:(vault._unlock_vault(),vault._open_edit_form(vault.store.items[0]))),
   ]:
    frame=QFrame();frame.setObjectName('captureFrame')
    frame.setStyleSheet('#captureFrame{background:'+get_workspace_tokens(cfg).bg_color+';}')
    layout=QVBoxLayout(frame);layout.setContentsMargins(0,0,0,0);layout.addWidget(widget)
    frame.resize(width,height);prepare();frame.show();app.processEvents()
    widget.toast.hide()
    for _ in range(5):
     app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);time.sleep(.01)
    suffix='-short' if height==430 else ''
    path=output/f'{name}-{theme}-{width}{suffix}.png';frame.grab().save(str(path))
    row={'view':name,'theme':theme,'requested':[width,height],'actual':[frame.width(),frame.height()],'path':str(path)}
    if name=='vault-form':
     save=next(button for button in vault._active_form.findChildren(QPushButton) if button.text()=='Save credential')
     viewport=vault.content_scroll.viewport()
     row['save_in_viewport']=viewport.rect().contains(QRect(save.mapTo(viewport,QPoint()),save.size()))
    results.append(row)
    widget.setParent(None);frame.close();frame.deleteLater();app.processEvents()
  notes.close();vault.close();notes.deleteLater();vault.deleteLater();app.processEvents()
(output/'report.json').write_text(json.dumps(results,indent=2))
assert all(row['actual']==row['requested'] for row in results),[row for row in results if row['actual']!=row['requested']]
assert all(row.get('save_in_viewport',True) for row in results),[row for row in results if not row.get('save_in_viewport',True)]
print(json.dumps({'screenshots':len(results),'sizes':'380×430, 380×620 and 600×820','themes':['dark','light'],'directory':str(output)}))
