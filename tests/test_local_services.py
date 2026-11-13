import io,json,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
import pytest
from PIL import Image
from studio.core import config,load
from studio.local_ai import images,create

@pytest.fixture
def ai_service(project):
    state={'image_jobs':0,'writing_calls':0,'error':False}
    png=io.BytesIO();Image.new('RGB',(1344,768),'#465d41').save(png,format='PNG')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,data,mime='application/json'):
            if not isinstance(data,bytes):data=json.dumps(data).encode()
            self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/generate':
                assert body['keep_alive']==0 and body['format']=='json'
                state['writing_calls']+=1
                return self.reply({'response':json.dumps(project)})
            if self.path=='/prompt':
                assert body['prompt']['4']['inputs']['batch_size']==1
                state['image_jobs']+=1
                return self.reply({'prompt_id':'job-'+str(state['image_jobs'])})
            return self.reply({})
        def do_GET(self):
            if self.path.startswith('/history/'):
                key=self.path.rsplit('/',1)[1]
                if state['error']:return self.reply({key:{'status':{'status_str':'error','completed':True}}})
                return self.reply({key:{'status':{'completed':True},'outputs':{'7':{'images':[{'filename':'test.png','subfolder':'storyforge','type':'output'}]}}}})
            return self.reply(png.getvalue(),'image/png')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}',state
    server.shutdown();server.server_close()

def test_real_http_writer_contract(ai_service):
    base,state=ai_service
    p=create('A courier receives a forgotten promise.',75,{'ollama_url':base,'comfy_url':base},lambda _:None)
    assert state['writing_calls']==2
    assert p['fiction'] is True

def test_real_http_image_contract_cache_and_manual_art(ai_service,tmp_path,project):
    base,state=ai_service;project['settings']['comfy_url']=base
    images(tmp_path,project,lambda _:None)
    assert state['image_jobs']==7
    assert Image.open(tmp_path/'art/001.png').size==(1344,768)
    images(tmp_path,project,lambda _:None);assert state['image_jobs']==7
    project['scenes'][0]['image_prompt']+=' dramatic close-up'
    images(tmp_path,project,lambda _:None);assert state['image_jobs']==8
    project['scenes'][0]['art_source']='manual';project['settings']['seed']+=1
    images(tmp_path,project,lambda _:None);assert state['image_jobs']==14

def test_comfy_failure_never_creates_fake_image(ai_service,tmp_path,project):
    base,state=ai_service;state['error']=True;project['settings']['comfy_url']=base
    with pytest.raises(RuntimeError,match='generation failed'):images(tmp_path,project,lambda _:None)
    assert not (tmp_path/'art/001.png').exists()
