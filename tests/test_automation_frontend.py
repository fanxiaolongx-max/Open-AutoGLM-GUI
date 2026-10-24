"""Frontend behavior checks; uses Node when present, without browser or model calls."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which('node'),'Node is optional for frontend checks')
class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.root.joinpath('package.json').write_text('{"type":"module"}')
        shutil.copytree(Path(__file__).resolve().parents[1]/'web_app/static/js/automation',self.root/'automation')

    def tearDown(self):
        self.tmp.cleanup()

    def run_js(self,code):
        result=subprocess.run(['node','--input-type=module','-e',code],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_task_replay_keeps_devices_and_action_boundaries_separate(self):
        module=json.dumps((self.root/'automation/replay.js').as_uri())
        self.run_js('''import assert from 'node:assert/strict';
        const {buildTaskFrames,markerForAction}=await import('''+module+''');
        const events=[
          {seq:4,device_id:'a',kind:'screen',data:{image_id:'final',final:true}},
          {seq:3,device_id:'a',kind:'action',data:{action:{element:[200,700]}}},
          {seq:2,device_id:'b',kind:'action',data:{action:{element:[900,900]}}},
          {seq:1,device_id:'a',kind:'screen',data:{image_id:'first'}}];
        const frames=buildTaskFrames(events,'a');
        assert.deepEqual(frames.map(f=>f.image_id),['first','final']);
        assert.equal(markerForAction(frames[0].action).x,20);
        assert.equal(frames[1].action,undefined);
        assert.equal(markerForAction({element:['invalid',2]}),null);
        ''')

    def test_demonstration_coordinates_normalize_for_the_same_phone_surface(self):
        module=json.dumps((self.root/'automation/replay.js').as_uri())
        self.run_js('''import assert from 'node:assert/strict';
        const {buildDemoFrames,markerForAction}=await import('''+module+''');
        const demo={device_id:'phone',actions:[
          {kind:'swipe',image_id:'image',data:{start:[80,100],end:[240,300],width:320,height:400}},
          {kind:'text',data:{text:'{输入内容}',redacted:true}}]};
        const frames=buildDemoFrames(demo);
        assert.equal(frames.length,1);
        assert.deepEqual(markerForAction(frames[0].action),{x:25,y:25,x2:75,y2:75,swipe:true});
        assert.deepEqual(buildDemoFrames({actions:[]}),[]);
        ''')

    def environment(self):
        module=json.dumps((self.root/'automation/app.js').as_uri())
        return '''import assert from 'node:assert/strict';
        const watches=[],cleanups=[],calls=[];let interval;
        globalThis.Vue={ref:value=>({value}),reactive:value=>value,
          computed:get=>({get value(){return get();}}),
          watch(source,callback,options){watches.push({source,callback});if(options?.immediate)callback(source.value);},
          onMounted(){},onUnmounted(callback){cleanups.push(callback);}};
        globalThis.document={hidden:false};globalThis.location={search:''};
        globalThis.setInterval=callback=>{interval=callback;return 1;};
        globalThis.clearInterval=()=>{};
        globalThis.WebSocket=class{constructor(){throw Error('Must reuse the host connection');}};
        const task={id:'t',task_content:'test',device_ids:['phone'],status:'completed',steps:[{content:'test'}],executions:[],options:{}};
        const screens=[{seq:1,task_id:'t',device_id:'phone',kind:'screen',data:{image_id:'one'}},
          {seq:2,task_id:'t',device_id:'phone',kind:'screen',data:{image_id:'two'}}];
        globalThis.fetch=async(path,options={})=>{
          calls.push({path,method:options.method});
          let data={};
          if(path==='/health')data={status:'healthy',capabilities:{automation:true}};
          else if(path==='/api/automation/settings')data={timezone:'UTC',concurrency:2};
          else if(path==='/api/automation/tasks')data={tasks:[task]};
          else if(path==='/api/recipes')data={recipes:[]};
          else if(path==='/api/demonstrations')data={demonstrations:[]};
          else if(path==='/api/triggers')data={triggers:[]};
          else if(path==='/api/tasks/t')data=task;
          else if(path.startsWith('/api/tasks/t/events'))data={events:screens,cursor:2};
          else throw Error('Unexpected endpoint: '+path);
          return {ok:true,json:async()=>data};
        };
        const {useAutomation}=await import('''+module+''');
        const active={value:false},devices={value:[{id:'phone'}]},previewDevice={value:'phone'};
        const notifications=[];const state=useAutomation({active,devices,previewDevice,notify:message=>notifications.push(message)});
        const auth=watches.find(w=>w.source===active);
        const drain=async()=>{for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));};
        '''

    def test_authentication_lifecycle_reuses_devices_and_clears_cached_private_state(self):
        self.run_js(self.environment()+'''
        assert.equal(calls.length,0);
        assert.equal(state.devices,devices);assert.equal(state.previewDevice,previewDevice);
        active.value=true;auth.callback(true);await drain();
        assert.equal(state.tasks.value[0].id,'t');
        assert.equal(state.taskSource({options:{trial:true}}),'试运行');
        assert.equal(state.taskSource({options:{is_scheduled:true}}),'定时任务');
        assert.equal(state.taskSource({options:{}}),'手动任务');
        state.text.value='private input';state.parameterValues.value={secret:'value'};
        active.value=false;auth.callback(false);
        assert.equal(state.tasks.value.length,0);assert.equal(state.text.value,'');
        assert.deepEqual(state.parameterValues.value,{});assert.deepEqual(Object.keys(state.taskIndex),[]);
        cleanups.forEach(fn=>fn());
        ''')

    def test_playback_only_reads_history_and_stops_at_the_last_frame(self):
        self.run_js(self.environment()+'''
        active.value=true;auth.callback(true);await drain();
        await state.selectReplayTask('t');
        assert.equal(state.replayFrames.value.length,2);
        state.togglePlayback();assert.equal(state.playing.value,true);
        interval();assert.equal(state.currentFrame.value.image_id,'two');
        interval();assert.equal(state.playing.value,false);
        state.seekReplay(-10);assert.equal(state.replayPosition.value,0);
        assert.ok(calls.every(call=>call.method==='GET'));
        assert.ok(calls.every(call=>!call.path.includes('/scrcpy')&&!call.path.includes('/input')));
        cleanups.forEach(fn=>fn());
        ''')

    def test_old_backend_stops_polling_and_reports_one_actionable_error(self):
        self.run_js(self.environment()+'''
        const workingFetch=globalThis.fetch;
        globalThis.fetch=async path=>{calls.push({path,method:'GET'});return {ok:true,json:async()=>({status:'healthy'})};};
        active.value=true;auth.callback(true);await drain();
        assert.equal(state.ready.value,false);assert.equal(state.backendUnavailable.value,true);
        assert.deepEqual(calls.map(c=>c.path),['/health']);
        await state.refresh();await state.refresh();
        assert.equal(calls.length,1);assert.equal(notifications.length,1);
        await state.reconnect();assert.equal(notifications.length,1);
        assert.ok(notifications[0].includes('重启后端'));
        globalThis.fetch=workingFetch;await state.reconnect();
        assert.equal(state.ready.value,true);assert.equal(state.backendUnavailable.value,false);
        assert.equal(state.tasks.value[0].id,'t');
        cleanups.forEach(fn=>fn());
        ''')

    def test_http_errors_include_the_endpoint_without_exposing_query_values(self):
        module=json.dumps((self.root/'automation/api.js').as_uri())
        self.run_js('''import assert from 'node:assert/strict';
        const {api}=await import('''+module+''');
        globalThis.fetch=async()=>({ok:false,status:404,json:async()=>({detail:'Not Found'})});
        await assert.rejects(api('/api/automation/settings?token=private'),error=>{
          assert.equal(error.status,404);assert.equal(error.path,'/api/automation/settings');
          assert.ok(error.message.includes('重启后端'));assert.ok(!error.message.includes('private'));
          return true;
        });
        globalThis.fetch=async()=>({ok:false,status:500,json:async()=>{throw Error('not JSON');}});
        await assert.rejects(api('/api/automation/settings'),error=>error.message.includes('500'));
        ''')
