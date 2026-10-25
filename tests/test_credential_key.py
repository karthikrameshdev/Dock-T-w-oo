"""Platform protection and lossless migration of existing credential keys."""
from cryptography.fernet import Fernet
import pytest
from dock_twoo.brain import credential_key as module


def test_windows_key_is_wrapped_and_existing_credentials_survive_migration(tmp_path,monkeypatch):
    key=Fernet.generate_key();encrypted=Fernet(key).encrypt(b'provider-secret')
    path=tmp_path/'cloud-credentials.key';path.write_bytes(key)
    monkeypatch.setattr(module,'windows_user_protection',lambda:True)
    def protect(data,*,decrypt=False):return data[::-1] if decrypt else data[::-1]
    monkeypatch.setattr(module,'_dpapi',protect)
    assert module.cipher_key(path)==key
    assert path.read_bytes()==module.WINDOWS_HEADER+key[::-1]
    assert Fernet(module.cipher_key(path)).decrypt(encrypted)==b'provider-secret'


def test_windows_protection_failure_cannot_create_an_unprotected_key(tmp_path,monkeypatch):
    path=tmp_path/'cloud-credentials.key'
    monkeypatch.setattr(module,'windows_user_protection',lambda:True)
    monkeypatch.setattr(module,'_dpapi',lambda *_:(_ for _ in ()).throw(OSError('unavailable')))
    with pytest.raises(OSError):module.cipher_key(path)
    assert not path.exists()


def test_native_windows_protection_roundtrip_and_tamper_rejection():
    if not module.windows_user_protection():pytest.skip('Native DPAPI needs a Windows user profile')
    data=Fernet.generate_key();wrapped=module._dpapi(data)
    assert wrapped!=data and module._dpapi(wrapped,decrypt=True)==data
    with pytest.raises(OSError):module._dpapi(wrapped[:20],decrypt=True)
