"""Explicit idle-sleep inhibition while enabled; released on exit."""
import atexit
import platform
import os
import subprocess
import threading

class KeepAwake:
    def __init__(self):
        self.config=None;self.process=None;self.enabled=False;self._lock=threading.RLock();self._windows_stop=threading.Event();self._windows_thread=None;atexit.register(self.close)
    def bind(self,config):
        self.config=config
        self.set_enabled(bool(config.config.keep_live))
    def set_enabled(self,enabled):
        with self._lock:
            if bool(enabled)==self.status()['enabled']:return self.status()
            if enabled:
                system=platform.system()
                if system=='Darwin':
                    self.process=subprocess.Popen(['/usr/bin/caffeinate','-d','-i','-w',str(os.getpid())],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                elif system=='Windows':
                    import ctypes
                    self._windows_stop.clear();ready=threading.Event();success=[]
                    def hold():
                        success.append(bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)));ready.set()
                        self._windows_stop.wait()
                        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
                    self._windows_thread=threading.Thread(target=hold,daemon=True,name='dock-keep-awake')
                    self._windows_thread.start()
                    if not ready.wait(2) or not success[0]:
                        self._windows_stop.set()
                        self._windows_thread.join(timeout=2)
                        raise RuntimeError('Windows could not prevent idle sleep.')
                elif system=='Linux':
                    self.process=subprocess.Popen(['systemd-inhibit','--what=idle:sleep','--who=Dock T(w)oo','--why=Keep Live enabled','--mode=block','sleep','infinity'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    try:
                        code=self.process.wait(timeout=.1)
                        raise RuntimeError(f'The desktop sleep inhibitor exited ({code}). Check systemd/login permissions.')
                    except subprocess.TimeoutExpired:pass
                else:raise RuntimeError('Unsupported Keep Live platform.')
                self.enabled=True
            else:self.close()
            if self.config:self.config.update({'keep_live':self.enabled})
            return self.status()
    def close(self):
        with self._lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:self.process.kill()
            self._windows_stop.set()
            if self._windows_thread and self._windows_thread is not threading.current_thread():self._windows_thread.join(timeout=2)
            self._windows_thread=None
            self.process=None;self.enabled=False
    def status(self):
        with self._lock:
            if self.process and self.process.poll() is not None:self.process=None;self.enabled=False
            return {'enabled':self.enabled,'description':'Display and system idle sleep prevented while enabled. Manual lock remains available.'}
_instance=KeepAwake()
def get_keep_awake():return _instance
