import sys,types
import numpy as np
import pytest
import soundfile as sf
from studio.core import save,load
from studio.audio import narrate,assemble

def test_voice_cache_invalidates_on_text_and_audio_changes(tmp_path,project,monkeypatch):
    import studio.audio as a
    models=tmp_path/'models';models.mkdir();(models/'kokoro-v1.0.onnx').write_bytes(b'model');(models/'voices-v1.0.bin').write_bytes(b'voices')
    monkeypatch.setattr(a,'ROOT',tmp_path)
    calls=[]
    class Voice:
        def __init__(self,*args):pass
        def get_voices(self):return ['af_heart']
        def create(self,text,**kwargs):
            calls.append(text);t=np.arange(4800)/24000
            return (.2*np.sin(2*np.pi*200*t)).astype(np.float32),24000
    monkeypatch.setitem(sys.modules,'kokoro_onnx',types.SimpleNamespace(Kokoro=Voice))
    folder=tmp_path/'film';folder.mkdir()
    narrate(folder,project,lambda _:None);n=len(calls)
    narrate(folder,project,lambda _:None);assert len(calls)==n
    project['scenes'][0]['narration']='A new promise arrived in an old box.'
    narrate(folder,project,lambda _:None);assert len(calls)>n
    n=len(calls);sf.write(folder/'audio/002.wav',np.ones(1000)*.1,24000)
    narrate(folder,project,lambda _:None);assert len(calls)>n
    timeline=assemble(folder,project)
    assert len(timeline)==len(project['scenes'])
    assert timeline[0]['start']==0
    assert (folder/'captions.srt').exists()

def test_missing_scene_audio_stops(tmp_path,project):
    with pytest.raises(ValueError,match='Missing scene narration'):assemble(tmp_path,project)
