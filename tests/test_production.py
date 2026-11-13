import copy
import threading
import requests
import pytest
from PIL import Image
from studio.core import save,load
from studio.production import approve,copy_pilot,pipeline,package
from studio.render import inspect_art
from studio.server import make_server

def test_pilot_does_not_overwrite(tmp_path):
    path=copy_pilot(tmp_path)
    assert path.exists()
    with pytest.raises(ValueError,match='already exists'):copy_pilot(tmp_path)

def test_missing_art_never_becomes_blank(tmp_path,project):
    with pytest.raises(ValueError,match='missing'):inspect_art(tmp_path,project)

def test_low_resolution_is_rejected(tmp_path,project):
    (tmp_path/'art').mkdir();Image.new('RGB',(100,100)).save(tmp_path/'art/001.png')
    with pytest.raises(ValueError,match='below'):inspect_art(tmp_path,project)

def test_project_lock_blocks_concurrent_runs(tmp_path,project):
    save(tmp_path/'project.json',project);(tmp_path/'.production.lock').write_text('123')
    with pytest.raises(ValueError,match='locked'):pipeline(tmp_path/'project.json',('package',))

def test_failure_records_status_and_releases_lock(tmp_path,project):
    save(tmp_path/'project.json',project)
    with pytest.raises(ValueError):pipeline(tmp_path/'project.json',('render',),progress=lambda _:None)
    assert not (tmp_path/'.production.lock').exists()
    assert load(tmp_path/'status.json')['state']=='failed'

def test_approval_requires_watch_and_checks(tmp_path,project):
    with pytest.raises(ValueError,match='five'):approve(tmp_path,project,{})
    project['technical_demo']=True
    with pytest.raises(ValueError,match='technical demo'):approve(tmp_path,project,{})

def test_pack_escapes_story_text(tmp_path,project):
    project['title']='<script>alert(1)</script>'
    package(tmp_path,project)
    text=(tmp_path/'review.html').read_text()
    assert '<script>alert' not in text
    assert '&lt;script&gt;' in text
    assert load(tmp_path/'upload-metadata.json')['privacy']=='private'

@pytest.fixture
def server(tmp_path):
    server=make_server(0,tmp_path/'projects');thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    session=requests.Session();session.trust_env=False
    yield f'http://127.0.0.1:{server.server_port}',session,server,tmp_path
    server.shutdown();server.server_close();server.pool.shutdown(wait=True)

def test_local_api_access_controls(server):
    base,session,_,_=server
    assert session.get(base+'/').status_code==200
    assert session.get(base+'/',headers={'Host':'evil.test'}).status_code==400
    assert session.post(base+'/api/create',json={}).status_code==403
    assert session.post(base+'/api/create',json={},headers={'X-Storyforge':'1','Origin':'https://evil.test'}).status_code==403
    assert session.post(base+'/api/resume',json={'project':'../outside'},headers={'X-Storyforge':'1'}).status_code==422
    assert session.get(base+'/projects/%2e%2e%2fsecret.txt').status_code==404

def test_video_range_and_unknown_project(server):
    base,session,_,tmp=server
    folder=tmp/'projects'/'fixture';folder.mkdir();(folder/'final.mp4').write_bytes(b'0123456789')
    r=session.get(base+'/projects/fixture/final.mp4',headers={'Range':'bytes=2-5'})
    assert r.status_code==206 and r.content==b'2345'
    assert r.headers['Content-Range']=='bytes 2-5/10'
    assert session.get(base+'/projects/fixture/final.mp4',headers={'Range':'bytes=99-'}).status_code==416
