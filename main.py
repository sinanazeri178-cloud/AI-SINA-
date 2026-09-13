# SINA AI LOCAL PRO
# Real local LLM frontend for Android/Pydroid.
# Uses llama.cpp's local OpenAI-compatible server when available.
# No cloud API key is required.
import os, json, threading, subprocess, time, urllib.request, urllib.error, re, shutil
from datetime import datetime

os.environ.setdefault('KIVY_NO_ARGS','1')
os.environ.setdefault('KIVY_NO_FILELOG','1')

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup

THEMES={
 'Black & White':('#000000','#101010','#191919','#FFFFFF','#B8B8B8','#FFFFFF','#000000'),
 'Black & Blue':('#06090F','#0D1420','#151E2D','#F5F8FF','#AEBBD0','#4AA3FF','#00111F'),
 'Black & Green':('#050A07','#0D1510','#152019','#F3FFF7','#AFC4B5','#39E27D','#001A0B'),
 'Black & Purple':('#08050B','#120C18','#1B1222','#FFF8FF','#C8B7D0','#B76CFF','#160020'),
 'White & Black':('#FFFFFF','#F1F1F1','#E4E4E4','#111111','#555555','#111111','#FFFFFF')}

DEFAULT={
 'theme':'Black & Blue','font_size':16,'server_url':'http://127.0.0.1:8080','model':'local-model',
 'llama_server':'','model_path':'','auto_start':False,'temperature':0.6,'max_tokens':512,
 'system_prompt':'You are SINA AI, a helpful, concise, friendly assistant. Answer naturally. If you are unsure, say so instead of inventing facts.',
 'context_messages':18}


def now(): return datetime.now().strftime('%H:%M')
def safe_json_load(path, default):
    try:
        with open(path,'r',encoding='utf-8') as f: return json.load(f)
    except Exception: return json.loads(json.dumps(default))
def safe_json_save(path,obj):
    tmp=path+'.tmp'
    try:
        with open(tmp,'w',encoding='utf-8') as f: json.dump(obj,f,ensure_ascii=False,indent=2)
        os.replace(tmp,path)
    except Exception: pass

def rgba(hexv,a=1):
    h=hexv.lstrip('#'); return tuple(int(h[i:i+2],16)/255 for i in (0,2,4))+(a,)

class Card(BoxLayout):
    def __init__(self,color,r=14,**kw):
        super().__init__(**kw); self.padding=dp(10)
        with self.canvas.before:
            self.c=Color(*rgba(color)); self.rect=RoundedRectangle(pos=self.pos,size=self.size,radius=[dp(r)])
        self.bind(pos=self.sync,size=self.sync)
    def sync(self,*_): self.rect.pos=self.pos; self.rect.size=self.size

class SINA(App):
    def build(self):
        self.title='SINA AI Local Pro'
        self.base=os.path.join(self.user_data_dir,'sina_local_pro'); os.makedirs(self.base,exist_ok=True)
        self.settings=safe_json_load(os.path.join(self.base,'settings.json'),DEFAULT)
        for k,v in DEFAULT.items(): self.settings.setdefault(k,v)
        self.chats=safe_json_load(os.path.join(self.base,'chats.json'),{'Default':[]})
        self.memory=safe_json_load(os.path.join(self.base,'memory.json'),{})
        self.current='Default'; self.busy=False; self.server_proc=None; self.request_no=0
        self.rootbox=BoxLayout(orientation='vertical')
        self.rebuild()
        Clock.schedule_once(lambda *_: self.auto_connect(),0.5)
        return self.rootbox

    @property
    def theme(self):
        b,p,c,t,m,a,at=THEMES.get(self.settings['theme'],THEMES['Black & Blue'])
        return {'bg':b,'panel':p,'card':c,'text':t,'muted':m,'accent':a,'accent_text':at}
    def save_all(self):
        safe_json_save(os.path.join(self.base,'settings.json'),self.settings)
        safe_json_save(os.path.join(self.base,'chats.json'),self.chats)
        safe_json_save(os.path.join(self.base,'memory.json'),self.memory)
    def btn(self,text,fn,w=80):
        t=self.theme; b=Button(text=text,size_hint_x=None,width=dp(w),background_normal='',background_color=rgba(t['accent']),color=rgba(t['accent_text']),font_size=dp(11),bold=True)
        b.bind(on_release=fn); return b
    def rebuild(self):
        self.rootbox.clear_widgets(); t=self.theme; Window.clearcolor=rgba(t['bg'])
        top=BoxLayout(size_hint_y=None,height=dp(58),padding=dp(7),spacing=dp(6))
        logo=Label(text='S',size_hint_x=None,width=dp(42),font_size=dp(23),bold=True,color=rgba(t['accent_text']),halign='center',valign='middle')
        with logo.canvas.before: Color(*rgba(t['accent'])); lr=RoundedRectangle(pos=logo.pos,size=logo.size,radius=[dp(12)])
        logo.bind(pos=lambda *_:setattr(lr,'pos',logo.pos),size=lambda *_:setattr(lr,'size',logo.size)); top.add_widget(logo)
        title=Label(text='SINA AI LOCAL PRO',font_size=dp(16),bold=True,color=rgba(t['text']),halign='left',valign='middle'); title.bind(size=lambda i,v:setattr(i,'text_size',v)); top.add_widget(title)
        top.add_widget(self.btn('NEW',self.new_chat,58)); top.add_widget(self.btn('TOOLS',self.tools,58)); top.add_widget(self.btn('SETTINGS',self.settings_popup,72)); self.rootbox.add_widget(top)
        self.scroll=ScrollView(do_scroll_x=False); self.messages=GridLayout(cols=1,spacing=dp(7),padding=dp(8),size_hint_y=None); self.messages.bind(minimum_height=self.messages.setter('height')); self.scroll.add_widget(self.messages); self.rootbox.add_widget(self.scroll)
        bottom=BoxLayout(size_hint_y=None,height=dp(72),padding=dp(7),spacing=dp(5))
        self.status=Label(text='LOCAL AI: checking...',size_hint_x=None,width=dp(92),font_size=dp(9),color=rgba(t['muted']))
        bottom.add_widget(self.status)
        self.input=TextInput(hint_text='Message SINA AI...',multiline=True,font_size=dp(self.settings['font_size']),background_color=rgba(t['card']),foreground_color=rgba(t['text']),cursor_color=rgba(t['accent']),padding=[dp(10),dp(10)])
        bottom.add_widget(self.input); bottom.add_widget(self.btn('MIC',lambda *_:None,48)); bottom.add_widget(self.btn('SEND',self.send,58)); self.rootbox.add_widget(bottom)
        self.render()
    def render(self):
        if not hasattr(self,'messages'): return
        self.messages.clear_widgets()
        for m in self.chats.get(self.current,[]): self.bubble(m.get('role','assistant'),m.get('content',''),m.get('time',''))
        Clock.schedule_once(lambda *_: setattr(self.scroll,'scroll_y',0),0.08)
    def bubble(self,role,text,stamp=''):
        t=self.theme; user=role=='user'; row=BoxLayout(size_hint_y=None,height=dp(70))
        if user: row.add_widget(BoxLayout())
        card=Card(t['accent'] if user else t['card'],r=14,size_hint_x=.88 if user else .93,size_hint_y=None,orientation='vertical',spacing=dp(3),padding=[dp(10)]*4)
        lab=Label(text=str(text),color=rgba(t['accent_text'] if user else t['text']),font_size=dp(self.settings['font_size']),halign='left',valign='top',size_hint_y=None)
        def resize(*_):
            lab.text_size=(max(dp(40),card.width-dp(20)),None); lab.height=max(dp(24),lab.texture_size[1]); card.height=lab.height+dp(28); row.height=card.height+dp(6)
        card.bind(width=resize); lab.bind(texture_size=resize); card.add_widget(lab)
        if stamp:
            s=Label(text=stamp,size_hint_y=None,height=dp(16),font_size=dp(9),color=rgba(t['muted'])); card.add_widget(s); card.height+=dp(16); row.height=card.height+dp(6)
        row.add_widget(card)
        if not user: row.add_widget(BoxLayout())
        self.messages.add_widget(row)
    def add(self,role,text):
        self.chats.setdefault(self.current,[]).append({'role':role,'content':text,'time':now()}); self.save_all(); self.render()
    def new_chat(self,*_):
        name='Chat '+datetime.now().strftime('%Y-%m-%d %H-%M-%S'); self.chats[name]=[]; self.current=name; self.render()
    def send(self,*_):
        if self.busy: return
        text=self.input.text.strip()
        if not text: return
        self.input.text=''; self.add('user',text); self.busy=True; self.status.text='LOCAL AI: thinking...'; self.request_no+=1; rid=self.request_no
        threading.Thread(target=self.worker,args=(rid,text),daemon=True).start()
    def worker(self,rid,text):
        try:
            reply=self.local_chat(text)
            err=None
        except Exception as e:
            reply=''; err=str(e)
        Clock.schedule_once(lambda *_: self.finish(rid,reply,err),0)
    def finish(self,rid,reply,err):
        if rid!=self.request_no: return
        self.busy=False
        if err:
            self.status.text='LOCAL AI: error'; self.add('assistant','Local AI is not ready yet.\n\n'+err+'\n\nOpen TOOLS → LOCAL AI SETUP for the exact setup steps.')
        else:
            self.status.text='LOCAL AI: ready'; self.add('assistant',reply)
    def endpoint(self,path): return self.settings['server_url'].rstrip('/')+path
    def local_chat(self,user_text):
        # Add small persistent memory context. Never sends secrets to a network endpoint;
        # this backend is expected to be localhost only.
        mem='\n'.join([f'- {k}: {v}' for k,v in self.memory.items()])[:5000]
        msgs=[{'role':'system','content':self.settings['system_prompt']+'\nPersistent user memory:\n'+(mem or '(none)')}]
        history=self.chats.get(self.current,[])[-int(self.settings.get('context_messages',18)):]
        for m in history: msgs.append({'role':m['role'],'content':m['content']})
        payload={'model':self.settings.get('model','local-model'),'messages':msgs,'temperature':float(self.settings.get('temperature',0.6)),'max_tokens':int(self.settings.get('max_tokens',512)),'stream':False}
        data=json.dumps(payload).encode(); req=urllib.request.Request(self.endpoint('/v1/chat/completions'),data=data,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=180) as r: raw=r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            body=e.read().decode('utf-8','replace'); raise RuntimeError(f'HTTP {e.code}: {body[:800]}')
        obj=json.loads(raw); choices=obj.get('choices') or []
        if not choices: raise RuntimeError('The local server returned no answer.')
        return str(choices[0].get('message',{}).get('content','')).strip() or 'The local model returned an empty response.'
    def auto_connect(self):
        threading.Thread(target=self.check_server,daemon=True).start()
    def check_server(self):
        ok=False; detail='offline'
        try:
            with urllib.request.urlopen(self.endpoint('/v1/models'),timeout=2) as r:
                obj=json.loads(r.read().decode()); ok=bool(obj.get('data')); detail='ready' if ok else 'no model'
        except Exception as e: detail='not running'
        Clock.schedule_once(lambda *_: self.set_status(ok,detail),0)
    def set_status(self,ok,detail): self.status.text='LOCAL AI: '+detail
    def tools(self,*_):
        t=self.theme; box=BoxLayout(orientation='vertical',spacing=dp(8),padding=dp(10))
        for txt,fn in [('LOCAL AI SETUP',self.setup_popup),('MEMORY',self.memory_popup),('EXPORT CHAT',self.export_chat),('NEW CHAT',self.new_chat)]: box.add_widget(self.btn(txt,fn,160))
        box.add_widget(self.btn('CLOSE',lambda *_: pop.dismiss(),160)); pop=Popup(title='TOOLS',content=box,size_hint=(.88,.62)); pop.open()
    def setup_popup(self,*_):
        t=self.theme; box=BoxLayout(orientation='vertical',spacing=dp(7),padding=dp(10))
        info=Label(text='SINA AI Local Pro uses llama.cpp on your phone. No cloud API key is required.\n\nInstall/build llama.cpp in Termux, download a GGUF model, then run llama-server on 127.0.0.1:8080.',color=rgba(t['text']),font_size=dp(12),halign='left',valign='top',size_hint_y=None,height=dp(105)); info.bind(size=lambda i,v:setattr(i,'text_size',(v[0],None))); box.add_widget(info)
        for key,label in [('server_url','Server URL'),('model','Model ID'),('llama_server','llama-server path'),('model_path','GGUF model path')]:
            box.add_widget(Label(text=label,color=rgba(t['muted']),size_hint_y=None,height=dp(22)))
            ti=TextInput(text=str(self.settings.get(key,'')),multiline=False,size_hint_y=None,height=dp(42),background_color=rgba(t['card']),foreground_color=rgba(t['text']))
            setattr(self,'setup_'+key,ti); box.add_widget(ti)
        buttons=BoxLayout(size_hint_y=None,height=dp(45),spacing=dp(5)); buttons.add_widget(self.btn('SAVE',lambda *_:save(),70)); buttons.add_widget(self.btn('CHECK',lambda *_:check(),70)); buttons.add_widget(self.btn('CLOSE',lambda *_:pop.dismiss(),70)); box.add_widget(buttons)
        def save():
            for key in ('server_url','model','llama_server','model_path'): self.settings[key]=getattr(self,'setup_'+key).text.strip()
            self.save_all(); pop.dismiss(); self.check_server_now()
        def check(): self.check_server_now()
        pop=Popup(title='LOCAL AI SETUP',content=box,size_hint=(.94,.9)); pop.open()
    def check_server_now(self): threading.Thread(target=self.check_server,daemon=True).start()
    def start_server(self,*_):
        path=self.settings.get('llama_server','').strip(); model=self.settings.get('model_path','').strip()
        if not path or not model:
            self.add('assistant','Set the llama-server path and GGUF model path in TOOLS → LOCAL AI SETUP first.'); return
        if self.server_proc and self.server_proc.poll() is None:
            self.add('assistant','Local AI server is already running.'); return
        try:
            self.server_proc=subprocess.Popen([path,'-m',model,'--host','127.0.0.1','--port','8080','-c','4096'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.status.text='LOCAL AI: starting...'; Clock.schedule_once(lambda *_:self.check_server_now(),3)
        except Exception as e: self.add('assistant','Could not start llama-server: '+str(e))
    def memory_popup(self,*_):
        t=self.theme; box=BoxLayout(orientation='vertical',spacing=dp(6),padding=dp(8));
        text='\n'.join([f'{k}: {v}' for k,v in self.memory.items()]) or 'No saved memory.'
        box.add_widget(Label(text=text,color=rgba(t['text']),halign='left',valign='top'))
        box.add_widget(self.btn('CLOSE',lambda *_:pop.dismiss(),100)); pop=Popup(title='MEMORY',content=box,size_hint=(.9,.75)); pop.open()
    def export_chat(self,*_):
        path=os.path.join(self.base,'SINA_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.txt')
        try:
            with open(path,'w',encoding='utf-8') as f:
                for m in self.chats.get(self.current,[]): f.write(f"{m['role'].upper()} [{m.get('time','')}]:\n{m['content']}\n\n")
            self.add('assistant','Chat exported to:\n'+path)
        except Exception as e: self.add('assistant','Export failed: '+str(e))
    def settings_popup(self,*_):
        t=self.theme; box=BoxLayout(orientation='vertical',spacing=dp(7),padding=dp(10)); box.add_widget(Label(text='Theme',color=rgba(t['muted']),size_hint_y=None,height=dp(24)))
        for name in THEMES:
            box.add_widget(self.btn(name,lambda inst,n=name:self.change_theme(n,pop),160))
        box.add_widget(self.btn('CLOSE',lambda *_:pop.dismiss(),100)); pop=Popup(title='SETTINGS',content=box,size_hint=(.9,.88)); pop.open()
    def change_theme(self,name,pop): self.settings['theme']=name; self.save_all(); pop.dismiss(); self.rebuild()
    def on_stop(self):
        self.save_all()
        try:
            if self.server_proc and self.server_proc.poll() is None: self.server_proc.terminate()
        except Exception: pass

if __name__=='__main__': SINA().run()
