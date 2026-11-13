import shutil
import numpy as np
import pytest
import soundfile as sf
from PIL import Image
from studio.core import save,load
from studio.production import pipeline,approve

@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='FFmpeg not installed')
def test_actual_export_cache_music_and_stale_approval(tmp_path,project):
    project['scenes']=project['scenes'][:3]
    project['scenes'][1]['beat']='reversal';project['scenes'][2]['beat']='payoff'
    project['settings'].update({'width':640,'height':360,'preset':'fast','burn_captions':True})
    (tmp_path/'art').mkdir();(tmp_path/'audio').mkdir()
    sr=24000;t=np.arange(sr)/sr
    for s,colour in zip(project['scenes'],['#213449','#624b31','#336255']):
        Image.new('RGB',(1024,576),colour).save(tmp_path/'art'/f"{s['id']:03}.png")
        sf.write(tmp_path/'audio'/f"{s['id']:03}.wav",.2*np.sin(2*np.pi*(200+s['id']*30)*t),sr)
    music=tmp_path/'music.wav';sf.write(music,.08*np.sin(2*np.pi*120*t),sr)
    project['settings'].update({'music':str(music),'music_rights':'Synthetic test waveform created in this test'})
    path=tmp_path/'project.json';save(path,project)
    pipeline(path,('render','package'),progress=lambda _:None)
    assert load(tmp_path/'quality.json')['technical_pass'] is True
    assert load(tmp_path/'quality.json')['width']==640
    checks={k:True for k in ['watched_full_video','character_continuity','voice_and_captions','rights_reviewed','youtube_settings_reviewed']}
    assert approve(tmp_path,project,checks)['input_signature']
    clip=tmp_path/'cache/master/001.mp4';before=clip.stat().st_mtime_ns
    pipeline(path,('render',),progress=lambda _:None)
    assert clip.stat().st_mtime_ns==before
    Image.new('RGB',(1024,576),'red').save(tmp_path/'art/001.png')
    with pytest.raises(ValueError,match='assets changed'):approve(tmp_path,project,checks)
