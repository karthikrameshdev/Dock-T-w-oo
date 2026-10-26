"""Real local ONNX scanner -> HTTP boundary -> Postman fixture, no private user data."""
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dock_twoo.brain.cloud import CloudClient
from dock_twoo.brain.activity import ActivityStore
with tempfile.TemporaryDirectory(prefix='dock-privacy-') as folder:
    tracker=ActivityStore(Path(folder)/'activity')
    cases=[]
    for protocol in ('openai','anthropic'):
        client=CloudClient({'provider':'custom','model':'fixture','protocol':protocol,'base_url':'http://127.0.0.1:24930/cloud'},'fixture-key',allow_test_endpoint=True,timeout=10)
        client.privacy.secrets.add('opaque-test-key');client.tracker=tracker
        text='privacy-check Jane Smith alice@example.org 4111 1111 1111 1111 password: danger-secret access_key: opaque-test-key'
        payload=client.payload([{'role':'user','content':text}],[])
        wire=json.dumps(payload)
        for secret in ('Jane Smith','alice@example.org','4111 1111','danger-secret','opaque-test-key'):assert secret not in wire,secret
        result=client.turn([{'role':'user','content':text}],[])
        assert 'Privacy checked' in result.calls[0]['arguments']['text']
        assert 'Jane Smith' in result.calls[0]['arguments']['text']
        cases.append({'protocol':protocol,'redacted_on_wire':True,'local_references_restored':True})
    print(json.dumps({'success':True,'cases':cases,'scanner':'local quantized BERT ONNX','live_provider_calls':0}))
