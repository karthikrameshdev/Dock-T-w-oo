"""Non-destructive, startup-only migration of the assistant data directory."""
import json
from pathlib import Path
import shutil
import tempfile


def migrate_voice_storage(root):
    root=Path(root);old=root/'brain';new=root/'voice';marker=root/'.voice-storage-migrated'
    if marker.exists() or not old.is_dir():return new
    # Never overwrite a destination containing independent user data.
    if new.exists() and any(new.iterdir()):
        raise RuntimeError(f'Both {old} and {new} contain data. Resolve the storage conflict before starting Dock; neither folder was changed.')
    root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.voice-migration-',dir=root) as folder:
        staged=Path(folder)/'voice';shutil.copytree(old,staged)
        if new.exists():new.rmdir()  # Empty directory created by a status read.
        staged.rename(new)
    # Keep the legacy directory intact as a recovery copy. Internal artifact paths
    # pointing there remain valid; never rewrite credential/key files.
    marker.write_text(json.dumps({'from':str(old),'to':str(new),'legacy_retained':True}))
    marker.chmod(0o600)
    return new
