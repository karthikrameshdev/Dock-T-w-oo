"""Local ONNX image captioning. Only its text result enters the cloud agent."""
from __future__ import annotations
from pathlib import Path
import threading
MODEL='Xenova/vit-gpt2-image-captioning'
REVISION='215b4edcb7ec1fad5905a18a03f7b2007f6fabd0'
_lock=threading.Lock();_engine=None

def describe_image(path,cancel):
    global _engine
    import numpy as np
    from PIL import Image,ImageOps
    with _lock:
        if cancel.is_set():raise InterruptedError('Request stopped.')
        if _engine is None:
            import onnxruntime as ort
            from huggingface_hub import snapshot_download
            from tokenizers import Tokenizer
            import truststore
            truststore.inject_into_ssl()
            root=Path(snapshot_download(MODEL,revision=REVISION,cache_dir=Path.home()/'.cache/huggingface/hub',
                allow_patterns=['*.json','vocab.json','merges.txt','onnx/encoder_model_quantized.onnx','onnx/decoder_model_quantized.onnx']))
            options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
            encoder=ort.InferenceSession(str(root/'onnx/encoder_model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
            decoder=ort.InferenceSession(str(root/'onnx/decoder_model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
            _engine=encoder,decoder,Tokenizer.from_file(str(root/'tokenizer.json'))
        encoder,decoder,tokenizer=_engine
        if Path(path).stat().st_size>20*1024*1024:raise ValueError('Use an image smaller than 20 MB.')
        with Image.open(path) as original:
            if original.width*original.height>40_000_000:raise ValueError('This image is too large to decode safely.')
            image=ImageOps.exif_transpose(original).convert('RGB').resize((224,224),Image.Resampling.BILINEAR)
            pixels=np.asarray(image,dtype=np.float32)/255.
        hidden=encoder.run(None,{encoder.get_inputs()[0].name:((pixels-.5)/.5).transpose(2,0,1)[None]})[0]
        tokens=[50256]
        for _ in range(40):
            if cancel.is_set():raise InterruptedError('Request stopped.')
            inputs={'input_ids':np.array([tokens],dtype=np.int64),'encoder_hidden_states':hidden}
            values={node.name:inputs[node.name] for node in decoder.get_inputs()}
            logits=decoder.run(None,values)[0];next_token=int(np.argmax(logits[0,-1]))
            if next_token==50256:break
            tokens.append(next_token)
        caption=tokenizer.decode(tokens,skip_special_tokens=True).strip()
        return {'caption':caption,'text':image_text(path),'source':'local ViT-GPT2 ONNX','limitation':'A short visual caption, not a factual identification or exhaustive image analysis.','pixels_uploaded':False}

def image_text(path):
    """Apple Vision OCR on a local file, with no selection or provider upload."""
    import platform
    if platform.system()!='Darwin':return ''
    import Vision
    from Foundation import NSURL,NSDictionary
    request=Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(0);request.setUsesLanguageCorrection_(True)
    handler=Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(path)),NSDictionary.dictionary())
    ok,error=handler.performRequests_error_([request],None)
    if not ok:raise RuntimeError('Local text recognition failed.')
    return '\n'.join(observation.topCandidates_(1)[0].string() for observation in request.results() or [] if observation.topCandidates_(1))


def capture_window(window_id,path):
    """Use current ScreenCaptureKit, retaining image bytes on the device."""
    import Quartz
    if not Quartz.CGPreflightScreenCaptureAccess():raise PermissionError('Enable Screen Recording for Dock to describe or OCR this window locally.')
    import ScreenCaptureKit as SC
    from AppKit import NSBitmapImageRep,NSBitmapImageFileTypePNG
    ready=threading.Event();result={}
    def content_ready(content,error):
        result['content']=content;result['error']=error;ready.set()
    SC.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(True,True,content_ready)
    if not ready.wait(5) or result.get('error'):raise RuntimeError('The active window could not be identified for local capture.')
    window=next((entry for entry in result['content'].windows() if entry.windowID()==window_id),None)
    if window is None:raise RuntimeError('The selected window is no longer available.')
    config=SC.SCStreamConfiguration.alloc().init()
    config.setWidth_(max(1,round(window.frame().size.width*2)))
    config.setHeight_(max(1,round(window.frame().size.height*2)))
    content_filter=SC.SCContentFilter.alloc().initWithDesktopIndependentWindow_(window)
    ready.clear()
    def image_ready(image,error):result['image']=image;result['error']=error;ready.set()
    SC.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(content_filter,config,image_ready)
    if not ready.wait(5) or result.get('error') or result.get('image') is None:raise RuntimeError('Screen capture failed. Check Screen Recording permission.')
    bitmap=NSBitmapImageRep.alloc().initWithCGImage_(result['image'])
    data=bitmap.representationUsingType_properties_(NSBitmapImageFileTypePNG,{})
    Path(path).write_bytes(bytes(data))


def describe_active_window(cancel):
    from dock_twoo.brain.desktop_reader import MacReadingBackend
    import tempfile
    target=MacReadingBackend().target()
    with tempfile.TemporaryDirectory(prefix='brain-local-window-') as folder:
        path=Path(folder)/'window.png';capture_window(target.window_id,path)
        result=describe_image(path,cancel);result['text']=image_text(path);result['window']=target.title
        return result
