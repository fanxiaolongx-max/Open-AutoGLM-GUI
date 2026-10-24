"""Exercise the real send handler with API/DOM adapters, without phone access."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which('node'), 'Node is optional for frontend checks')
class ConversationFrontendTests(unittest.TestCase):
    def test_chat_plan_execute_and_failure_paths(self):
        source = (Path(__file__).resolve().parents[1]/'web_app/static/js/main.js').read_text()
        source = source[source.index('async function sendChatMessage()'):source.index('// Stop chat task')]
        script = r'''
        const assert = require('node:assert/strict');
        const makeHandler = new Function('env', 'with (env) {'+SOURCE+'; return sendChatMessage;}');
        const ref = value => ({value});
        function setup(intent='chat', device='', complex=false) {
          const calls=[], toasts=[];
          const env={contextMonitor:{start(){},stop(){},accept(){},async refresh(){}},chatInput:ref('你好'),chatRunning:ref(false), chatDeviceId:ref(device),
            currentSessionId:ref('session'), chatMessages:ref([]),chatCursorPos:ref(0),
            devices:ref([{id:'phone',name:'手机'}]), complexTaskMode:ref(complex),
            debugMode:ref(false),chatAcceptance:ref(''),chatAutoEmail:ref(false),
            subtaskTimeoutSeconds:ref(180), awaitingTodoListConfirmation:ref(false),
            parseAtDeviceTaskSequence:()=>({hasMentions:false}),
            scrollChatToBottom(){},saveCurrentSession(){},showToast:(...args)=>toasts.push(args),
            console:{error(){},warn(){}},
            async apiCall(url, options={}) {
              calls.push({url,body:options.body ? JSON.parse(options.body):null});
              if(url.endsWith('/messages')) return {id:calls.length===1?'user':'assistant'};
              if(url==='/api/models') return {services:[]};
              if(url.endsWith('/respond')) {
                if(intent==='failure') throw Error('AI timeout');
                return {intent,reply:'可以先讨论具体方案。',task:'打开时钟，设置明早08:00闹钟',tokens:12,model_name:'mock'};
              }
              if(url==='/api/tasks/run') return {task_id:'task'};
              if(url==='/api/tasks/decompose') return {todoList:[{content:'设置闹钟'}]};
              throw Error('Unexpected API: '+url);
            },
            async submitManagedChat(msg){msg.taskId='complex-task';},
            async executeSlashAdbCommand(){calls.push({url:'slash'});}
          };
          return {env,calls,toasts,send:makeHandler(env)};
        }
        (async()=>{
          for(const intent of ['chat','plan','clarify']) {
            const t=setup(intent, '', true); await t.send();
            assert.equal(t.env.chatMessages.value.at(-1).status, 'replied');
            assert.equal(t.env.chatMessages.value.at(-1).content, '可以先讨论具体方案。');
            assert.equal(t.env.chatMessages.value.at(-1).tokens,12);
            assert.equal(t.env.chatRunning.value,false);
            assert.equal(t.calls.some(c=>c.url.startsWith('/api/tasks/')),false);
          }
          const valid=setup('execute','phone');valid.env.chatInput.value='按刚才方案执行';
          await valid.send();
          const run=valid.calls.find(c=>c.url==='/api/tasks/run');
          assert.equal(run.body.task_content,'打开时钟，设置明早08:00闹钟');
          assert.equal(run.body.session_id,'session');
          assert.ok(valid.calls.findIndex(c=>c.url.endsWith('/respond')) < valid.calls.indexOf(run));
          assert.equal(valid.env.chatMessages.value.at(-1).taskId,'task');
          const missing=setup('execute');await missing.send();
          assert.equal(missing.env.chatMessages.value.at(-1).status,'replied');
          assert.equal(missing.calls.some(c=>c.url==='/api/tasks/run'),false);
          const failure=setup('failure','phone');await failure.send();
          assert.equal(failure.env.chatMessages.value.at(-1).status,'error');
          assert.equal(failure.calls.some(c=>c.url==='/api/tasks/run'),false);
          const planning=setup('plan','phone',true);await planning.send();
          assert.equal(planning.calls.some(c=>c.url==='/api/tasks/decompose'),false);
          const complex=setup('execute','phone',true);await complex.send();
          assert.equal(complex.env.chatMessages.value.at(-1).taskId,'complex-task');
          assert.equal(complex.calls.find(c=>c.url==='/api/tasks/decompose').body.message_id,'assistant');
          const mentions=setup('chat');
          mentions.env.parseAtDeviceTaskSequence=()=>({hasMentions:true,sequence:[],unresolved:['unknown'],ambiguous:[],emptyTasks:[]});
          await mentions.send();assert.equal(mentions.env.chatMessages.value.at(-1).status,'replied');
          const slash=setup('chat','phone');slash.env.chatInput.value='/home';await slash.send();
          assert.equal(slash.calls.some(c=>c.url.endsWith('/respond')),false);
          assert.equal(slash.calls.some(c=>c.url==='slash'),true);
          const double=setup();await Promise.all([double.send(),double.send()]);
          assert.equal(double.calls.filter(c=>c.url.endsWith('/respond')).length,1);
        })().catch(e=>{console.error(e);process.exitCode=1;});
        '''.replace('SOURCE', json.dumps(source))
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
