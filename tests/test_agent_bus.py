import threading
from concurrent.futures import ThreadPoolExecutor
import grpc
import pytest
from dock_twoo.brain.ecosystem.bus import AgentBus,AgentClient


def test_real_grpc_identity_leases_stream_and_restart(tmp_path):
    bus=AgentBus(tmp_path).start();brain=bus.client();rio=bus.client('parrot');fox=bus.client('fox')
    try:
        with pytest.raises(grpc.RpcError) as error:
            rio.call('Assign',{'character_id':'fox','prompt':'Unauthorized delegation'})
        assert error.value.code()==grpc.StatusCode.PERMISSION_DENIED
        def assign(_):return brain.call('Assign',{'character_id':'parrot','prompt':'Research entanglement'})
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(assign,range(8)))
        assert sum(result['accepted'] for result in results)==1
        task=next(result['task_id'] for result in results if result['accepted'])
        with pytest.raises(grpc.RpcError):fox.call('Report',{'task_id':task,'state':'complete'})
        stream=brain.watch();first=next(stream)
        assert first['character_id']=='parrot' and first['kind']=='task_started'
        rio.call('Publish',{'task_id':task,'kind':'review_required','payload':{'error':'Missing source'}})
        assert next(stream)['kind']=='review_required'
        brain.call('Cancel',{'task_id':task})
        assert not brain.call('Assign',{'character_id':'parrot','prompt':'Not until cancellation acknowledged'})['accepted']
        rio.call('Report',{'task_id':task,'state':'cancelled'})
        assert brain.call('Assign',{'character_id':'parrot','prompt':'New task'})['accepted']
        stream.cancel()
    finally:
        brain.close();rio.close();fox.close();bus.close()
    bus=AgentBus(tmp_path).start();brain=bus.client()
    try:
        snapshot=brain.call('Snapshot');assert len(snapshot['agents'])==30
        assert snapshot['jobs'][0]['state']=='interrupted'
        bad=AgentClient(bus.port,'invalid-credential')
        try:
            with pytest.raises(grpc.RpcError) as error:bad.call('Snapshot')
            assert error.value.code()==grpc.StatusCode.UNAUTHENTICATED
        finally:bad.close()
    finally:brain.close();bus.close()
