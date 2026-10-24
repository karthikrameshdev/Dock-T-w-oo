"""Local macOS accessibility driver. No pixels or audio go to a provider."""
from __future__ import annotations
import platform
import os
import time
import uuid
from collections import deque

class DesktopDriver:
    def __init__(self):
        self.observation='';self.pid=None;self.controls={};self.created=0;self.frontmost_pid=None

    def _native(self):
        if platform.system()!='Darwin':raise RuntimeError('This desktop driver currently requires macOS.')
        import ApplicationServices as AX
        import Quartz
        if not AX.AXIsProcessTrusted():raise PermissionError('Enable Accessibility for Dock or its Python launcher in macOS Privacy & Security.')
        AX.AXUIElementSetMessagingTimeout(AX.AXUIElementCreateSystemWide(),.35)
        self.AX,self.Q=AX,Quartz
        return AX

    def get(self,node,key):
        if node is None:return None
        error,value=self.AX.AXUIElementCopyAttributeValue(node,key,None)
        return value if error==0 else None

    def _frontmost(self):
        if self.frontmost_pid is not None:
            pid=int(self.frontmost_pid())
            if pid==os.getpid():raise RuntimeError('Brain cannot automate its own embedded browser. Open or focus the target application first.')
            app=self.AX.AXUIElementCreateApplication(pid)
            self.AX.AXUIElementSetMessagingTimeout(app,.35)
            return app,pid
        app=self.get(self.AX.AXUIElementCreateSystemWide(),'AXFocusedApplication')
        if app is None:
            # Do not run an AppKit event loop from the agent worker. The live
            # agent resolves foreground state through its GUI-thread dispatcher.
            from AppKit import NSWorkspace
            current=NSWorkspace.sharedWorkspace().frontmostApplication()
            if current is None:raise RuntimeError('No active application is available.')
            pid=int(current.processIdentifier())
            if pid==os.getpid():raise RuntimeError('Focus the target application before desktop observation.')
            app=self.AX.AXUIElementCreateApplication(pid)
            self.AX.AXUIElementSetMessagingTimeout(app,.35)
            return app,pid
        error,pid=self.AX.AXUIElementGetPid(app,None)
        if error:raise RuntimeError('The active application could not be identified.')
        if pid==os.getpid():raise RuntimeError('Focus the target application before desktop observation.')
        self.AX.AXUIElementSetMessagingTimeout(app,.35)
        return app,pid

    def observe(self):
        self._native();app,pid=self._frontmost()
        self.AX.AXUIElementSetAttributeValue(app,'AXManualAccessibility',True)
        self.AX.AXUIElementSetAttributeValue(app,'AXEnhancedUserInterface',True)
        self.observation=uuid.uuid4().hex;self.pid=pid;self.created=time.monotonic();self.controls={}
        window=self.get(app,'AXFocusedWindow');self.window=window
        pending=deque([window,self.get(app,'AXMenuBar')]);rows=[];seen=set();deadline=time.monotonic()+6
        while pending and len(rows)<350 and time.monotonic()<deadline:
            node=pending.popleft()
            if node is None or node in seen:continue
            seen.add(node)
            role=str(self.get(node,'AXRole') or '')
            if 'SecureText' in role or self.get(node,'AXSubrole')=='AXSecureTextField':continue
            label=str(self.get(node,'AXTitle') or self.get(node,'AXDescription') or '')[:200]
            value=self.get(node,'AXValue')
            if role not in ('AXGroup','AXUnknown') or label or isinstance(value,str):
                ident=str(len(rows)+1);self.controls[ident]=node
                row={'id':ident,'role':role,'label':label,'enabled':self.get(node,'AXEnabled') is not False}
                if isinstance(value,(str,int,float)):row['value']=str(value)[:5000]
                rows.append(row)
            pending.extend(self.get(node,'AXChildren') or [])
        return {'observation':self.observation,'pid':pid,'window':str(self.get(window,'AXTitle') or ''),
                'document':str(self.get(window,'AXDocument') or ''),'controls':rows,'truncated':bool(pending),'permissions':'Accessibility granted'}

    def _check(self,observation,ident=None):
        self._native()
        if observation!=self.observation or time.monotonic()-self.created>90:
            raise RuntimeError('The desktop observation is stale. Observe the desktop again.')
        _app,pid=self._frontmost()
        if self.get(_app,'AXFocusedWindow') != self.window:raise RuntimeError('The active window changed. Observe again before acting.')
        if pid!=self.pid:raise RuntimeError('The active application changed. Observe it again before acting.')
        node=self.controls.get(str(ident)) if ident is not None else None
        if ident is not None and node is None:raise ValueError('Use a control id from the latest desktop observation.')
        return node

    def click(self,observation,control):
        node=self._check(observation,control)
        if self.get(node,'AXEnabled') is False:raise RuntimeError('The selected control is disabled.')
        error=self.AX.AXUIElementPerformAction(node,'AXPress')
        if error:
            # Non-button text areas can be focused without altering selection.
            error=self.AX.AXUIElementSetAttributeValue(node,'AXFocused',True)
        if error:raise RuntimeError('The application did not accept the control action.')
        return {'clicked':str(control),'observe_again':True}

    def type_text(self,observation,text):
        self._check(observation)
        app,_pid=self._frontmost();focused=self.get(app,'AXFocusedUIElement')
        role=str(self.get(focused,'AXRole') or '')
        if 'Secure' in role or self.get(focused,'AXSubrole')=='AXSecureTextField':raise PermissionError('Brain does not enter credentials into password fields.')
        if role not in ('AXTextArea','AXTextField','AXComboBox') and 'editor' not in str(self.get(focused,'AXDescription') or '').lower():
            raise RuntimeError('Focus an editable field using a desktop observation before typing.')
        text=str(text)
        if len(text)>16000:raise ValueError('Type at most 16000 characters per call.')
        before=self.get(focused,'AXValue')
        error=self.AX.AXUIElementSetAttributeValue(focused,'AXSelectedText',text)
        if error:
            for start in range(0,len(text),16):
                self._check(observation);chunk=text[start:start+16]
                for down in (True,False):
                    event=self.Q.CGEventCreateKeyboardEvent(None,0,down)
                    self.Q.CGEventKeyboardSetUnicodeString(event,len(chunk.encode('utf-16-le'))//2,chunk)
                    self.Q.CGEventPostToPid(self.pid,event)
        time.sleep(.15);after=self.get(focused,'AXValue')
        return {'characters':len(text),'verified':isinstance(after,str) and text in after,
                'changed':before!=after,'submitted':False}

    def key(self,observation,key):
        self._check(observation)
        codes={'enter':36,'return':36,'tab':48,'escape':53,'space':49,'backspace':51,'delete':117,
               'left':123,'right':124,'down':125,'up':126,'home':115,'end':119,'pageup':116,'pagedown':121,
               'a':0,'s':1,'d':2,'f':3,'h':4,'g':5,'z':6,'x':7,'c':8,'v':9,'b':11,'q':12,'w':13,
               'e':14,'r':15,'y':16,'t':17,'o':31,'u':32,'i':34,'p':35,'l':37,'j':38,'k':40,'n':45,'m':46}
        parts=str(key).lower().replace('command','cmd').split('+');name=parts[-1];flags=0
        for modifier in parts[:-1]:
            if modifier not in ('cmd','ctrl','alt','shift'):raise ValueError('Unknown key modifier.')
            flags|={'cmd':self.Q.kCGEventFlagMaskCommand,'ctrl':self.Q.kCGEventFlagMaskControl,
                    'alt':self.Q.kCGEventFlagMaskAlternate,'shift':self.Q.kCGEventFlagMaskShift}[modifier]
        if name not in codes:raise ValueError('Use a supported key name such as cmd+s, enter, tab or escape.')
        for down in (True,False):
            event=self.Q.CGEventCreateKeyboardEvent(None,codes[name],down)
            self.Q.CGEventSetFlags(event,flags);self.Q.CGEventPostToPid(self.pid,event)
        return {'key':key,'observe_again':True}

    def scroll(self,observation,pixels,cancel):
        self._check(observation)
        pixels=max(-2000,min(2000,int(pixels)));previous=0
        from dock_twoo.brain.desktop_reader import MacReadingBackend
        rect=MacReadingBackend()._rect(self.window)
        for step in range(1,25):
            self._check(observation)
            if cancel.is_set():raise InterruptedError('Request stopped.')
            f=step/24;amount=round(pixels*f*f*(3-2*f));delta=amount-previous;previous=amount
            event=self.Q.CGEventCreateScrollWheelEvent(None,self.Q.kCGScrollEventUnitPixel,1,-delta)
            self.Q.CGEventSetLocation(event,(rect.center().x(),rect.center().y()))
            self.Q.CGEventPostToPid(self.pid,event)
            cancel.wait(1/60)
        return {'scrolled_pixels':pixels,'observe_again':True}

    def drag(self,observation,source,target,cancel):
        first=self._check(observation,source);last=self._check(observation,target)
        from dock_twoo.brain.desktop_reader import MacReadingBackend
        backend=MacReadingBackend();a,b=backend._rect(first).center(),backend._rect(last).center()
        position=(a.x(),a.y());pressed=False
        try:
            for step in range(25):
                if cancel.is_set():raise InterruptedError('Request stopped.')
                self._check(observation);f=step/24
                position=(a.x()+(b.x()-a.x())*f,a.y()+(b.y()-a.y())*f)
                kind=self.Q.kCGEventLeftMouseDown if step==0 else self.Q.kCGEventLeftMouseDragged
                event=self.Q.CGEventCreateMouseEvent(None,kind,position,self.Q.kCGMouseButtonLeft)
                self.Q.CGEventPostToPid(self.pid,event);pressed=True;cancel.wait(1/60)
        finally:
            if pressed:
                event=self.Q.CGEventCreateMouseEvent(None,self.Q.kCGEventLeftMouseUp,position,self.Q.kCGMouseButtonLeft)
                self.Q.CGEventPostToPid(self.pid,event)
        return {'dragged':True,'observe_again':True}

    def selected_text(self,pid=None):
        self._native()
        if pid==os.getpid():raise RuntimeError('Select text in an external document first.')
        app=self.AX.AXUIElementCreateApplication(pid) if pid is not None else self._frontmost()[0]
        focused=self.get(app,'AXFocusedUIElement')
        if 'Secure' in str(self.get(focused,'AXRole') or '') or self.get(focused,'AXSubrole')=='AXSecureTextField':raise PermissionError('Password text is not readable.')
        text=self.get(focused,'AXSelectedText')
        if not isinstance(text,str) or not text.strip():raise RuntimeError('No existing text selection was found in the active app.')
        return {'text':text,'selection_changed':False}
