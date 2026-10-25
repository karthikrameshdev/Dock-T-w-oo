"""Protect the credential encryption key using each platform's local boundary."""
from __future__ import annotations
import os
import platform
from pathlib import Path
from cryptography.fernet import Fernet

WINDOWS_HEADER=b'BRAIN-DPAPI-1\x00'


def windows_user_protection() -> bool:
    return platform.system()=='Windows'


def _dpapi(data: bytes, *, decrypt=False) -> bytes:
    """Use current-user DPAPI, never the machine-wide protection scope."""
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('length',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    raw=(ctypes.c_ubyte*len(data)).from_buffer_copy(data)
    incoming=Blob(len(data),raw);outgoing=Blob()
    library=ctypes.WinDLL('crypt32',use_last_error=True)
    operation=library.CryptUnprotectData if decrypt else library.CryptProtectData
    operation.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,
                        ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    operation.restype=wintypes.BOOL
    if not operation(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(outgoing)):
        raise OSError(ctypes.get_last_error(),'Windows could not unlock or protect the Brain credential key for this user.')
    try:
        return ctypes.string_at(outgoing.data,outgoing.length)
    finally:
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
        kernel.LocalFree(outgoing.data)


def cipher_key(path: Path) -> bytes:
    if not path.exists():
        key=Fernet.generate_key()
        stored=WINDOWS_HEADER+_dpapi(key) if windows_user_protection() else key
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as target:target.write(stored)
    stored=path.read_bytes()
    if stored.startswith(WINDOWS_HEADER):
        if not windows_user_protection():
            raise RuntimeError('This credential key belongs to a Windows user profile. Configure the cloud key on this computer.')
        return _dpapi(stored[len(WINDOWS_HEADER):],decrypt=True)
    if windows_user_protection():
        # Preserve the existing Fernet key, so encrypted credentials remain valid.
        # Wrap it atomically; never leave a newly generated raw key on Windows.
        wrapped=WINDOWS_HEADER+_dpapi(stored)
        temporary=path.with_suffix('.key.tmp')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'wb') as target:target.write(wrapped)
        temporary.replace(path)
    else:
        path.chmod(0o600)
    return stored
