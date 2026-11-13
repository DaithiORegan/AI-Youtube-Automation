import copy
import pytest
from studio.core import config,validate,signature,scene_prompt,srt_time,subtitles
from studio.local_ai import local_session,workflow,create
from studio.audio import chunks,caption_groups

def test_pilot_has_story_arc(project):
    assert validate(project)
    assert 150<sum(len(s['narration'].split()) for s in project['scenes'])<230
    assert len({s['image_prompt'] for s in project['scenes']})==7

@pytest.mark.parametrize('change',['ids','hook','payoff','reversal','verify','camera','art'])
def test_invalid_stories_stop(project,change):
    if change=='ids':project['scenes'][0]['id']=5
    if change=='hook':project['scenes'][0]['beat']='setup'
    if change=='payoff':project['scenes'][-1]['beat']='setup'
    if change=='reversal':
        for s in project['scenes']:
            if s['beat']=='reversal':s['beat']='setup'
    if change=='verify':project['scenes'][0]['narration']='This unresolved claim is [VERIFY].'
    if change=='camera':project['scenes'][0]['camera']='shell command'
    if change=='art':project['scenes'][0]['art_source']='unknown'
    with pytest.raises(ValueError):validate(project)

@pytest.mark.parametrize('url',['https://api.openai.com','http://example.com','file:///etc/passwd','http://user:pass@localhost:8188','http://localhost:8188/path','http://localhost:8188?token=secret'])
def test_no_remote_generation_provider(url):
    with pytest.raises(ValueError):local_session(url)

def test_local_generation_ignores_proxy_environment():
    assert local_session('http://127.0.0.1:8188').trust_env is False

def test_workflow_uses_native_nodes_and_single_images(project):
    c=config(project);prompt=scene_prompt(project,project['scenes'][0]);g=workflow(c,prompt,42)
    assert g['4']['inputs']['batch_size']==1
    assert g['5']['inputs']['seed']==42
    assert g['2']['inputs']['text']==prompt
    assert project['character_bible'] in prompt
    assert all(isinstance(v['class_type'],str) for v in g.values())

def test_audio_chunks_do_not_drop_words():
    text=('This is a sentence with several words. '*15).strip()
    pieces=chunks(text,50)
    assert ' '.join(pieces)==text
    assert all(len(x)<=50 for x in pieces)

def test_captions_are_bounded_and_monotonic():
    groups=caption_groups('A courier found a promise inside the box and changed her mind about going home.',2,10)
    assert groups[0]['start']==2
    assert groups[-1]['end']==10
    assert all(a['end']<=b['start'] for a,b in zip(groups,groups[1:]))
    assert srt_time(3661.234)=='01:01:01,234'
    assert '-->' in subtitles(groups)

@pytest.mark.parametrize('field,value',[('width',1921),('fps',60),('steps',999),('speed',3),('image_width',999),('preset','broken')])
def test_invalid_render_settings(project,field,value):
    project['settings'][field]=value
    with pytest.raises(ValueError):config(project)

def test_seed_changes_cache_identity(project):
    assert signature(workflow(config(project),'shot',1))!=signature(workflow(config(project),'shot',2))

def test_writer_revision_is_validated(monkeypatch,project):
    import studio.local_ai as ai
    calls=[]
    def answer(*args,**kwargs):calls.append(args);return copy.deepcopy(project)
    monkeypatch.setattr(ai,'ollama',answer)
    result=create('A mysterious parcel changes a courier’s life.',90)
    assert len(calls)==2
    assert result['fiction'] is True
