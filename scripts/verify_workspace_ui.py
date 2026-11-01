"""Render responsive Live Trail/Dashboard against isolated synthetic API fixtures.

Uses actual Qt WebEngine, controls.js, ActivityStore and static app assets. No
microphone, cloud models, live app, native pointer or user storage is accessed.
Screenshots and JSON checks go to /tmp/dock-workspace-ui by default.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from dock_twoo.brain.activity import ActivityStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/tmp/dock-workspace-ui'))
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    folder = tempfile.TemporaryDirectory(prefix='dock-workspace-ui-')
    fixed = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc); clock = [fixed - timedelta(days=6)]
    store = ActivityStore(Path(folder.name), clock=lambda: clock[0])
    profiles = [dict(id='research', name='Research', provider='openai', model='research-model', _character_id='default', _character_name='Brain'),
                dict(id='everyday', name='Everyday', provider='anthropic', model='assistant-model', _character_id='parrot', _character_name='Rio')]
    for day in range(7):
        clock[0] = fixed - timedelta(days=6-day)
        for index, profile in enumerate(profiles):
            run = store.start(['Summarize today’s completed work items', 'Read the product notes and list the next steps'][index], 'voice')
            call = store.begin_call(run, profile, {'messages': [{'role': 'user', 'content': 'Summarize the synthetic project notes.'}]})
            inp, out = 12000 + day*9300 + index*2400, 2800 + day*1100
            store.end_call(call, {'usage': {'prompt_tokens': inp, 'completion_tokens': out, 'total_tokens': inp+out, 'prompt_tokens_details': {'cached_tokens': inp//5}}, 'content': 'The synthetic work log has been summarized.'}, 'openai', latency_ms=1850+day*80)
            store.finish(run, 'complete', 'Completed the design review, updated the launch notes, and recorded tomorrow’s priorities.')
    clock[0] = fixed + timedelta(minutes=2)
    run = store.start('Research quantum computing and prepare a concise briefing with source notes.', 'voice')
    call = store.begin_call(run, profiles[0], {'messages': [{'role': 'user', 'content': 'Research quantum computing. Cover qubits, entanglement, and current practical limitations.'}], 'task': 'Create a clear research briefing'}, step=1)
    store.end_call(call, {'model': 'research-model', 'usage': {'prompt_tokens': 18400, 'completion_tokens': 4200, 'total_tokens': 22600}, 'content': 'I will research the foundations, compare the key approaches, and compile the findings into a briefing.'}, 'openai', latency_ms=2450)
    store.event(run, 'tool_result', {'agent': 'Orbit', 'result': 'Background research started. Reviewing source material and extracting the central findings.'}, 1)
    store.begin_call(run, profiles[0], {'messages': [{'role': 'user', 'content': 'Combine the research findings into the final briefing.'}]}, step=2)
    request_log = []
    static = Path(__file__).resolve().parents[1] / 'dock_twoo/server/static'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            parsed = urlsplit(self.path); query = parse_qs(parsed.query); path = parsed.path
            request_log.append(self.path)
            pick = lambda name, default=None: query.get(name, [default])[0]
            if path == '/api/brain/status': data = {'settings': {}}
            elif path == '/api/brain/model': data = {'characters': [{'id': 'default', 'name': 'Brain'}, {'id': 'orbit', 'name': 'Orbit'}, {'id': 'parrot', 'name': 'Rio'}], 'profiles': profiles}
            elif path == '/api/brain/ecosystem': data = {'jobs': [{'id': 'a', 'character_id': 'default', 'state': 'running', 'prompt': 'Prepare the quantum computing briefing', 'profile_id': 'research'}, {'id': 'b', 'character_id': 'orbit', 'state': 'complete', 'prompt': 'Research qubits and entanglement', 'profile_id': 'research', 'parent_id': 'a', 'result': 'Research is complete. The source notes are ready for synthesis.'}]}
            elif path == '/api/activity': data = store.list(offset=pick('offset', 0))
            elif path.startswith('/api/activity/'): data = store.detail(path.split('/')[3])
            elif path == '/api/usage':
                data = store.metrics(start=pick('from'), end=pick('to'), period=pick('period', 'month'), profile_id=pick('profile'), character_id=pick('character'))
                data['fixture'] = True
            else:
                target = (static / path.lstrip('/')).resolve()
                if not target.is_relative_to(static) or not target.is_file(): self.send_error(404); return
                raw = target.read_bytes(); self.send_response(200); self.send_header('Content-Type', mimetypes.guess_type(target)[0] or 'application/octet-stream'); self.end_headers(); self.wfile.write(raw); return
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(json.dumps(data).encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    view = QWebEngineView(); view.show()
    checks, shots = {}, []

    def js(code):
        result = []
        view.page().runJavaScript('JSON.stringify((()=>{' + code + '})())', result.append)
        until = time.monotonic()+5
        while not result and time.monotonic()<until: app.processEvents(); time.sleep(.01)
        if not result: raise AssertionError('WebEngine JavaScript did not respond')
        return json.loads(result[0] or 'null')

    def wait(code, timeout=10):
        until = time.monotonic()+timeout
        while time.monotonic()<until:
            result = js(code)
            if result:return result
            app.processEvents(); time.sleep(.05)
        raise AssertionError('UI condition timed out: '+code)

    def navigate(path):
        loaded = []
        view.loadFinished.connect(loaded.append)
        try:
            view.setUrl(QUrl(f'http://127.0.0.1:{server.server_port}/'+path))
            until = time.monotonic()+10
            while not loaded and time.monotonic()<until: app.processEvents(); time.sleep(.02)
            assert loaded and loaded[-1], ('Page did not load',path)
        finally:
            view.loadFinished.disconnect(loaded.append)

    def snapshot(name):
        for _ in range(8): app.processEvents(); time.sleep(.04)
        target = args.output / (name+'.png'); assert view.grab().save(str(target)); shots.append(str(target))

    try:
        for page in ('dashboard', 'live-trail'):
            for theme in ('dark', 'light'):
                for width in (420, 1100):
                    view.resize(width, 1000)
                    navigate(f'{page}.html?theme={theme}')
                    ready = 'document.querySelectorAll(".usage-chart svg").length===6' if page=='dashboard' else 'document.querySelectorAll(".activity-run").length>0'
                    wait('return location.search.includes("'+theme+'") && '+ready+';')
                    state = js('return {overflow:document.documentElement.scrollWidth>innerWidth,background:getComputedStyle(document.body).backgroundColor,heading:getComputedStyle(document.querySelector("h1")).fontSize,controls:[...document.querySelectorAll(".custom-dropdown-trigger,.usage-field>input,.usage-filter-panel>button")].map(x=>x.getBoundingClientRect().height),expanded:document.querySelectorAll(".activity-run[open]").length};')
                    assert not state['overflow'], (page, theme, width, state)
                    assert state['heading']=='22px', state
                    assert all(height==40 for height in state['controls']), state
                    assert state['background']==('rgb(19, 26, 36)' if theme=='dark' else 'rgb(244, 246, 250)'), state
                    if page=='live-trail': assert state['expanded']==0
                    checks[f'{page}-{theme}-{width}'] = state
                    snapshot(f'{page}-{theme}-{width}')
                    if page=='live-trail' and width==1100:
                        js('document.querySelector(".activity-run").open=true;')
                        wait('return !!document.querySelector(".activity-call");')
                        js('const call=document.querySelector(".activity-call");call.open=true;call.scrollIntoView({block:"start"});')
                        snapshot(f'live-trail-detail-{theme}-{width}')
                        js('Array.from(document.querySelectorAll("button")).find(b=>b.textContent==="Refresh").click();')
                        wait('return !!document.querySelector(".activity-run[open] .activity-call[open]");')
                        checks[f'expansion-{theme}'] = True
        for page in ('dashboard','live-trail'):
            for theme in ('dark','light'):
                view.resize(390,620);navigate(f'{page}.html?theme={theme}&embedded=1')
                wait('return '+('document.querySelectorAll(".usage-chart svg").length===6;' if page=='dashboard' else 'document.querySelectorAll(".activity-run").length>0;'))
                assert js('return document.documentElement.scrollWidth<=innerWidth && ![...document.querySelectorAll("h1")].some(x=>x.getClientRects().length);')
                snapshot(f'{page}-embedded-{theme}-390')
                checks[f'{page}-embedded-{theme}-390'] = True
        # Searchable dropdown and scoped dashboard data, not just screenshot counts.
        view.resize(420,1000);navigate('dashboard.html?theme=light')
        wait('return document.querySelectorAll(".usage-chart svg").length===6 && !!document.querySelector(".usage-hero strong");')
        before = js('return document.querySelector(".usage-hero strong").textContent;')
        js('document.querySelector(".custom-dropdown-trigger").click();const input=document.querySelector(".custom-dropdown-menu:not([hidden]) input");input.value="Research";input.dispatchEvent(new Event("input",{bubbles:true}));')
        assert js('return document.querySelectorAll(".custom-dropdown-menu:not([hidden]) [role=option]").length;')==1
        snapshot('dashboard-profile-search-light-420')
        js('document.querySelector(".custom-dropdown-menu:not([hidden]) [role=option]").click();')
        wait('return document.querySelector(".usage-hero strong").textContent!=='+json.dumps(before)+';')
        assert any('profile=research' in path for path in request_log)
        js('const p=document.querySelectorAll("select")[2];p.value="custom";p.dispatchEvent(new Event("change",{bubbles:true}));const dates=document.querySelectorAll("input[type=date]");dates[0].value="2026-11-14";dates[1].value="2026-11-20";document.querySelector(".usage-filter-panel").dispatchEvent(new Event("submit",{cancelable:true}));')
        wait('return document.querySelector("[role=status]").textContent.includes("2026-11-14");')
        assert any('from=2026-11-14' in path and 'to=2026-11-20' in path for path in request_log)
        checks['searchable_profile_filter'] = checks['profile_metrics_change'] = checks['custom_dates'] = True
        # Hold actual API responses to force edits/navigation during a pending
        # request. Older responses must never replace the currently chosen view.
        js('window.__nativeFetch=window.fetch;window.__held=[];window.fetch=async(...args)=>{const response=await window.__nativeFetch(...args);if(String(args[0]).startsWith("/api/usage?"))return new Promise(resolve=>window.__held.push({url:String(args[0]),release:()=>resolve(response)}));return response;};const dates=document.querySelectorAll("input[type=date]");dates[0].value="2026-11-13";document.querySelector(".usage-filter-panel").dispatchEvent(new Event("submit",{cancelable:true}));')
        wait('return window.__held.length===1;')
        js('document.querySelector("input[type=date]").value="2026-11-16";document.querySelector(".usage-filter-panel").dispatchEvent(new Event("submit",{cancelable:true}));window.__held[0].release();')
        wait('return window.__held.length===2;')
        assert not js('return document.querySelector("[role=status]").textContent.includes("2026-11-13");'), 'Stale custom date response was displayed'
        js('window.__held[1].release();window.fetch=window.__nativeFetch;')
        wait('return document.querySelector("[role=status]").textContent.includes("2026-11-16");')
        checks['stale_custom_date_response_ignored'] = True

        # Fill a second page, then click Next while a paused-list refresh is held.
        # This must finish on page 2 even without the automatic polling timer.
        for index in range(20):
            clock[0] += timedelta(seconds=1)
            store.start(f'Pagination fixture request {index}', 'typed')
        navigate('live-trail.html?theme=light')
        wait('return document.querySelectorAll(".activity-run").length===30;')
        first_ids = js('return [...document.querySelectorAll(".activity-run")].map(row=>row.dataset.run);')
        js('Array.from(document.querySelectorAll("button")).find(b=>b.textContent==="Pause updates").click();window.__nativeFetch=window.fetch;window.__held=[];window.fetch=async(...args)=>{const response=await window.__nativeFetch(...args);if(String(args[0]).startsWith("/api/activity?offset="))return new Promise(resolve=>window.__held.push({url:String(args[0]),release:()=>resolve(response)}));return response;};Array.from(document.querySelectorAll("button")).find(b=>b.textContent==="Refresh").click();')
        wait('return window.__held.length===1;')
        js('Array.from(document.querySelectorAll("button")).find(b=>b.textContent==="Next").click();window.__held[0].release();')
        wait('return window.__held.length===2 && window.__held[1].url.endsWith("offset=30");')
        assert not js('return document.querySelectorAll(".activity-run").length;'), 'Old activity page was rendered after navigation'
        js('window.__held[1].release();window.fetch=window.__nativeFetch;')
        wait('return document.querySelector(".activity-footer [role=status]").textContent.includes("Page 2") && document.querySelectorAll(".activity-run").length===5;')
        assert not set(first_ids).intersection(js('return [...document.querySelectorAll(".activity-run")].map(row=>row.dataset.run);'))
        checks['paused_activity_navigation_ignores_stale_page'] = True
        result = {'success': True, 'checks': checks, 'screenshots': shots, 'cloud_calls': 0, 'user_data_written': False}
        (args.output/'report.json').write_text(json.dumps(result, indent=2));print(json.dumps(result, indent=2))
    finally:
        view.close();server.shutdown();server.server_close();thread.join(2);folder.cleanup()


if __name__=='__main__':main()
