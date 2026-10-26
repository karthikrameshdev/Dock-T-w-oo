import json
from types import SimpleNamespace
import pytest
from dock_twoo.brain.security.privacy import PrivacyFilter,PrivacyUnavailable

class Entities:
    def spans(self,text):
        name='Jane Smith';start=text.find(name)
        return ((start,start+len(name)),) if start>=0 else ()


def test_sensitive_content_is_redacted_without_destroying_local_path_roundtrip():
    p=PrivacyFilter(['bare-private-key'],entities=Entities())
    text='Jane Smith /Users/alice/report.md email alice@example.org card 4111 1111 1111 1111 password: tiger-secret key bare-private-key phone +1 202 555 0123'
    clean=p.text(text)
    for secret in ('Jane Smith','alice','4111','tiger-secret','bare-private-key','202 555'):assert secret not in clean
    assert p.restore(clean)==text
    assert p.text(text)==clean


def test_all_model_protocols_scan_user_tool_memory_and_review_content():
    from dock_twoo.brain.cloud import CloudClient
    for provider,protocol in [('openai','openai'),('anthropic','anthropic'),('gemini','openai'),('ollama','openai')]:
        config={'provider':provider,'protocol':protocol,'model':'fixture','base_url':'http://127.0.0.1:24930/v1' if provider=='ollama' else 'https://provider.example/v1'}
        client=CloudClient(config,'test-api-key');client.privacy=PrivacyFilter(['test-api-key'],entities=Entities())
        payload=client.payload([{'role':'system','content':'Remember Jane Smith with alice@example.org'},{'role':'user','content':'password: danger-secret'},{'role':'tool','tool_call_id':'t1','content':'card 4111 1111 1111 1111 test-api-key'}],[])
        encoded=json.dumps(payload)
        for secret in ('Jane Smith','alice@example','danger-secret','4111','test-api-key'):assert secret not in encoded
        assert '[PRIVATE_' in encoded


def test_scanner_error_fails_closed_before_transport(monkeypatch):
    from dock_twoo.brain.cloud import CloudClient
    class Failed:
        def spans(self,text):raise PrivacyUnavailable('scanner failed')
    client=CloudClient({'provider':'openai','model':'fixture'},'test-key');client.privacy=PrivacyFilter(entities=Failed())
    sent=[];monkeypatch.setattr('urllib.request.urlopen',lambda *a,**k:sent.append(a))
    with pytest.raises(PrivacyUnavailable):client.turn([{'role':'user','content':'Private document'}],[])
    assert sent==[]


def test_unsafe_cli_adapters_fail_before_launch_or_task_file(monkeypatch):
    from dock_twoo.brain.ecosystem.cli import CLIClient
    from dock_twoo.brain.cloud import CloudError
    launches=[];monkeypatch.setattr('subprocess.Popen',lambda *a,**k:launches.append(a))
    for provider in ('custom_cli','codex_cli','gemini_cli','kilo_cli'):
        client=CLIClient({'provider':provider,'model':'fixture','executable':'unsafe'})
        try:
            with pytest.raises(CloudError,match='disabled'):client.turn([{'role':'user','content':'private'}],[])
            assert not (client.workspace/'task.json').exists()
        finally:client.close()
    assert not launches


def test_structured_short_secrets_are_redacted_by_field_name():
    privacy=PrivacyFilter(entities=Entities())
    result=privacy.clean({'result':{'password':'cat','pin':1234,'card_number':'4111111111111111'},'ok':True})
    assert result['ok'] is True
    assert all(str(value).startswith('[PRIVATE_') for value in result['result'].values())
    assert privacy.restore(result)['result']['password']=='cat'
