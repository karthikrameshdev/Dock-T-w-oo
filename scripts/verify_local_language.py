"""Exercise the production local-model client against running Postman simulations.

Start the three simulations as described in postman/README.md first. No audio,
model downloads, desktop actions, or cloud requests occur in this check.
"""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dock_twoo.brain.local_chat import LocalChat

results=[]
for name,port,expected,timeout in [('success',24920,True,2),('json_error',24921,False,2),('timeout',24922,False,.2),('unreachable',24923,False,.2)]:
    client=LocalChat(f'http://127.0.0.1:{port}/ollama',timeout=timeout)
    start=time.monotonic()
    if name=='success':
        assert client.ensure_ready(autostart=False),client.error
    else:
        client.model='qwen3:4b-instruct'
    try:
        answer=client.chat('Explain a rainbow briefly.')
        assert expected and answer=='This is a verified model response.'
    except RuntimeError:
        assert not expected
        assert client.status()['state']=='unavailable'
    elapsed=time.monotonic()-start
    assert elapsed<3
    results.append({'case':name,'state':client.state,'elapsed_seconds':round(elapsed,3)})
print(json.dumps({'passed':len(results),'cases':results},indent=2))
