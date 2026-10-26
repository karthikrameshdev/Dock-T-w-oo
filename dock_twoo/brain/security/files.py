"""File mutations are capabilities, never arbitrary generated shell commands."""
import hashlib
import json
import os
from pathlib import Path
import stat
import threading


class FileGuard:
    def __init__(self, ledger=None, approve=None):
        self.ledger=Path(ledger) if ledger else None
        self.approve=approve
        self.lock=threading.RLock()
        try:self.owned=json.loads(self.ledger.read_text()) if self.ledger else {}
        except (OSError,ValueError):self.owned={}

    @staticmethod
    def path(value):
        path=Path(os.path.abspath(Path(value).expanduser()))
        if os.sys.platform=='darwin':
            for alias in ('/var','/tmp'):
                if path.is_relative_to(alias):path=Path(alias).resolve()/path.relative_to(alias);break
        forbidden={'.ssh','.gnupg','.aws','.config','.bashrc','.zshrc','.profile','LaunchAgents','LaunchDaemons','Startup'}
        managed=any(part in {'.dock2','.dock_twoo'} for part in path.parts)
        report=any(path.is_relative_to(Path.home()/root/voice/'documents') for root in ('.dock2','.dock_twoo') for voice in ('voice','brain'))
        if any(part in forbidden for part in path.parts) or (managed and not report):
            raise PermissionError('Agent writes to credentials, startup configuration and application state are disabled: '+str(path))
        for part in (path,*path.parents):
            if part.is_symlink():raise PermissionError('Symlink paths are not permitted for file changes: '+str(path))
        if path.exists() and path.is_file() and path.stat().st_nlink!=1:
            raise PermissionError('Hard-linked files cannot be changed by an agent.')
        return path

    @staticmethod
    def fingerprint(path):
        info=path.stat()
        if not stat.S_ISREG(info.st_mode):raise PermissionError('Only regular files can be changed. Recursive directory deletion is disabled.')
        if info.st_size>32*1024*1024:raise PermissionError('File changes are limited to 32 MB.')
        return [info.st_dev,info.st_ino,info.st_mtime_ns,info.st_size,hashlib.sha256(path.read_bytes()).hexdigest()]

    def remember(self,path):
        with self.lock:
            self.owned[str(path)]=self.fingerprint(path)
            self._save()

    def _save(self):
        if self.ledger:
            self.ledger.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.ledger.with_suffix('.tmp');tmp.write_text(json.dumps(self.owned));tmp.chmod(0o600);tmp.replace(self.ledger)

    def create(self,value,text):
        with self.lock:
            path=self.path(value)
            path.parent.mkdir(parents=True,exist_ok=True)
            self.path(path)
            with path.open('x',encoding='utf-8') as stream:stream.write(text)
            self.remember(path)
            return {'created':str(path),'verified':path.read_text(encoding='utf-8')==text}

    def change(self,value,operation,cancel,text=None):
        if operation not in ('update','delete'):raise ValueError('Unknown file operation.')
        path=self.path(value);before=self.fingerprint(path)
        owned=self.owned.get(str(path))==before
        if not owned:
            if self.approve is None:raise PermissionError('Explicit approval is required to '+operation+' '+str(path))
            summary=(f'Replace the file contents with {len(text or "")} characters.' if operation=='update' else 'Permanently delete this file.')
            if not self.approve(operation,str(path),summary,cancel):raise PermissionError('File change denied or expired. Do not retry it or use another tool.')
        with self.lock:
            if cancel.is_set():raise InterruptedError('File change stopped.')
            self.path(path)
            if self.fingerprint(path)!=before:raise PermissionError('The file changed while approval was pending. Request a new approval.')
            if operation=='delete':
                path.unlink();self.owned.pop(str(path),None)
                self._save()
                return {'deleted':str(path),'verified':not path.exists()}
            # Do not grant ownership of a user document after an approved edit.
            descriptor=os.open(path,os.O_WRONLY|getattr(os,'O_NOFOLLOW',0))
            with os.fdopen(descriptor,'wb') as stream:
                info=os.fstat(stream.fileno())
                if [info.st_dev,info.st_ino]!=before[:2]:raise PermissionError('File identity changed before writing.')
                stream.write((text or '').encode('utf-8'));stream.truncate()
            if owned:self.remember(path)
            return {'updated':str(path),'verified':path.read_text(encoding='utf-8')==text}

    def command(self,argv,cwd,cancel,read_tool):
        """Portable command semantics. No shell, subprocess, eval or redirections."""
        if not isinstance(argv,list) or not 1<=len(argv)<=50 or any(not isinstance(a,str) or '\0' in a for a in argv):raise ValueError('Supply a command argv list.')
        name,*args=argv
        def path(value):
            p=Path(value).expanduser()
            return self.path(p if p.is_absolute() else Path(cwd)/p)
        if name=='pwd' and not args:return {'stdout':str(Path(cwd).resolve())}
        if name in ('ls','dir') and len(args)<=1:return read_tool('list_files',{'path':str(path(args[0] if args else '.'))},cancel)
        if name in ('cat','type') and len(args)==1:return read_tool('read_file',{'path':str(path(args[0]))},cancel)
        if name=='mkdir' and args:
            parents=args[0]=='-p';targets=args[1:] if parents else args
            if not targets:raise ValueError('mkdir needs a directory.')
            paths=[path(p) for p in targets]
            for p in paths:
                if cancel.is_set():raise InterruptedError('Command stopped.')
                p.mkdir(parents=parents,exist_ok=parents)
            return {'directories':[str(p) for p in paths],'verified':True}
        if name=='touch' and len(args)==1:
            target=path(args[0])
            if target.exists():return {'unchanged':str(target),'verified':True}
            return self.create(target,'')
        if name in ('rm','del') and len(args)==1 and not args[0].startswith('-'):return self.change(path(args[0]),'delete',cancel)
        if name=='cp' and len(args)==2:
            source=read_tool('read_file',{'path':str(path(args[0]))},cancel)
            if source.get('next_offset') is not None:raise ValueError('Use read_file pagination and write_file for larger documents.')
            return self.create(path(args[1]),source['text'])
        raise PermissionError('This command has no guarded implementation. Use list_files, search_files, read_file, write_file, update_file or delete_file. Shells, interpreters, pipelines, recursive deletion and arbitrary executables are disabled.')
