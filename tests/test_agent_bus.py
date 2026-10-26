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
        def assign(_):return rio.call('Assign',{'character_id':'parrot','prompt':'Research entanglement'})
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(assign,range(8)))
        assert sum(result['accepted'] for result in results)==1
        task=next(result['task_id'] for result in results if result['accepted'])
        with pytest.raises(grpc.RpcError):fox.call('Report',{'task_id':task,'state':'complete'})
        stream=brain.watch();first=next(stream)
        assert first['character_id']=='parrot' and first['kind']=='task_started'
        rio.call('Publish',{'task_id':task,'kind':'review_required','payload':{'error':'Missing source'}})
        assert next(stream)['kind']=='review_required'
        rio.call('Cancel',{'task_id':task})
        assert not rio.call('Assign',{'character_id':'parrot','prompt':'Not until cancellation acknowledged'})['accepted']
        rio.call('Report',{'task_id':task,'state':'cancelled'})
        assert rio.call('Assign',{'character_id':'parrot','prompt':'New task'})['accepted']
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


def test_peer_delegation_cycle_busy_reuse_and_cancellation_ownership(tmp_path):
    bus=AgentBus(tmp_path).start()
    orbit=bus.client('orbit');brain=bus.client('default');owl=bus.client('owl')
    try:
        root=orbit.call('Assign',{'character_id':'orbit','prompt':'Research'})['task_id']
        child=orbit.call('Assign',{'character_id':'default','prompt':'Subtask','parent_id':root})['task_id']
        nested=brain.call('Assign',{'character_id':'owl','prompt':'Nested research','parent_id':child})['task_id']
        with pytest.raises(grpc.RpcError) as cycle:
            owl.call('Assign',{'character_id':'orbit','prompt':'Cycle','parent_id':nested})
        assert cycle.value.code()==grpc.StatusCode.INVALID_ARGUMENT
        with pytest.raises(grpc.RpcError):
            owl.call('Assign',{'character_id':'fox','prompt':'Foreign parent','parent_id':root})
        with pytest.raises(grpc.RpcError):brain.call('Cancel',{'task_id':root})
        assert not orbit.call('Assign',{'character_id':'owl','prompt':'Busy','parent_id':root})['accepted']
        owl.call('Report',{'task_id':nested,'state':'complete','result':'Evidence'})
        brain.call('Report',{'task_id':child,'state':'complete','result':'Section'})
        reused=orbit.call('Assign',{'character_id':'default','prompt':'Fifth task','parent_id':root})
        assert reused['accepted'] and reused['task_id']!=child
        orbit.call('Cancel',{'task_id':root})
        states={j['id']:j['state'] for j in orbit.call('Snapshot')['jobs']}
        assert states[root]==states[reused['task_id']]=='cancelling'
        assert states[nested]==states[child]=='complete'
    finally:
        for client in (orbit,brain,owl):client.close()
        bus.close()
