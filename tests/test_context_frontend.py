import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which('node'),'Node required')
class ContextFrontendTests(unittest.TestCase):
    def test_history_marker_merging_is_ordered_and_polling_rejects_stale_responses(self):
        source=Path(__file__).resolve().parents[1]/'web_app/static/js/chat-context.js'
        with tempfile.TemporaryDirectory() as folder:
            module=Path(folder)/'context.mjs'
            module.write_text(source.read_text())
            script='''import assert from 'node:assert/strict';
            const {mergeContextEvents,createContextMonitor}=await import('''+json.dumps(module.as_uri())+''');
            const assistant={id:'answer',role:'assistant',status:'thinking'};
            const user={id:'question',role:'user'};
            const event={id:'event',source:'context_compaction',status:'compressing',created_at:'now',
                         context_event:{request_message_id:'answer'}};
            let merged=mergeContextEvents([user,assistant],[event]);
            assert.deepEqual(merged.map(m=>m.id),['question','event','answer']);
            merged=mergeContextEvents(merged,[{...event,status:'compressed'}]);
            assert.equal(merged.length,3);assert.equal(merged[1].status,'compressed');
            assert.equal(merged[2],assistant);
            const sessionId={value:'session'},messages={value:[user,assistant]},state={value:null},pending=[];
            const monitor=createContextMonitor({sessionId,messages,state,
                apiCall:()=>new Promise(resolve=>pending.push(resolve))});
            const first=monitor.refresh(),second=monitor.refresh();
            pending[1]({status:'ready',events:[{...event,status:'compressed'}]});await second;
            pending[0]({status:'compressing',events:[event]});await first;
            assert.equal(state.value.status,'ready');assert.equal(messages.value[1].status,'compressed');
            const obsolete=monitor.refresh();sessionId.value='other';pending[2]({status:'failed',events:[]});await obsolete;
            assert.equal(state.value.status,'ready');
            monitor.stop();
            '''
            result=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
