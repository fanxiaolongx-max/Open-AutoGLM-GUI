import base64
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from web_app.services.automation_catalog import Catalog
from web_app.services.automation_runtime import Runtime
from web_app.services.automation_storage import AutomationStorage
from web_app.services.scrcpy_service import ScrcpyService, ScrcpySession


class PointerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = ScrcpyService()
        self.session = ScrcpySession('phone',screen_width=100,screen_height=200)
        self.service._sessions['phone']=self.session
        self.touch = ScrcpyService.send_touch.__wrapped__
        self.adb = patch('web_app.services.scrcpy_service.subprocess.run',return_value=SimpleNamespace(returncode=0,stderr=b''))
        self.run = self.adb.start()

    async def asyncTearDown(self):
        self.adb.stop()

    async def send(self, action):
        return await self.touch(self.service,'phone',action,80,120,100,200)

    async def test_orphan_up_and_move_never_tap_phone(self):
        for action in ['up','up','move','cancel','up']:
            await self.send(action)
        self.run.assert_not_called()

    async def test_one_down_up_only_produces_one_tap(self):
        await self.send('down');await self.send('up')
        for _ in range(5):
            await self.send('up')
        self.run.assert_called_once()
        self.assertIn('tap',self.run.call_args.args[0])

    async def test_switching_modes_cancels_pending_adb_tap(self):
        await self.send('down');await self.send('cancel');await self.send('up')
        self.run.assert_not_called()

    async def test_native_scrcpy_cancel_has_android_cancel_action(self):
        with patch.object(self.service,'_can_use_scrcpy_control',return_value=True), \
             patch.object(self.service,'_send_scrcpy_control_packet',return_value=True), \
             patch.object(self.service,'_pack_scrcpy_touch_message',return_value=b'packet') as pack:
            await self.send('down');await self.send('cancel');await self.send('up')
            self.assertEqual([c.kwargs['action'] for c in pack.call_args_list],[0,3])
            self.assertEqual(pack.call_args_list[-1].kwargs['pressure'],0)
        self.run.assert_not_called()


class RecordingFrameTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.runtime=Runtime(AutomationStorage(Path(self.tmp.name)/'db'),devices=lambda:{'phone'})
        self.catalog=Catalog(self.runtime)
        self.demo=self.catalog.start_demo('phone')
        self.factory=Mock()
        self.factory.get_screenshot.return_value=SimpleNamespace(base64_data=base64.b64encode(b'PNG fixture').decode(),
                                                              is_sensitive=False,width=100,height=200)
        self.patch=patch('phone_agent.device_factory.get_device_factory',return_value=self.factory)
        self.patch.start()

    async def asyncTearDown(self):
        self.patch.stop();self.tmp.cleanup()

    async def test_h264_without_jpeg_cache_records_pre_action_frame(self):
        frame=await self.catalog.capture_manual_frame('phone','touch',{'action':'down'})
        self.catalog.record('phone','touch',{'action':'down','x':20,'y':30,'width':100,'height':200},image_id=frame)
        self.catalog.record('phone','touch',{'action':'up','x':20,'y':30})
        demo=self.runtime.store.get('demonstration',self.demo['id'])
        self.assertFalse(demo['record_text'])
        self.assertTrue(demo['record_images'])
        self.assertEqual(self.runtime.store.get_image(demo['actions'][0]['image_id']),b'PNG fixture')
        self.factory.get_screenshot.assert_called_once_with('phone')

    async def test_disabled_images_and_paused_recording_take_no_screenshots(self):
        self.catalog.demo_action(self.demo['id'],'pause')
        self.assertIsNone(await self.catalog.capture_manual_frame('phone','key',{}))
        self.catalog.demo_action(self.demo['id'],'finish')
        self.catalog.start_demo('phone',record_images=False)
        self.assertIsNone(await self.catalog.capture_manual_frame('phone','touch',{'action':'down'}))
        self.factory.get_screenshot.assert_not_called()

    async def test_capture_failure_is_visible_and_does_not_lose_action(self):
        self.factory.get_screenshot.side_effect=RuntimeError('no screenshot')
        self.assertIsNone(await self.catalog.capture_manual_frame('phone','key',{}))
        self.catalog.record('phone','key',{'keycode':3})
        demo=self.runtime.store.get('demonstration',self.demo['id'])
        self.assertIn('capture_error',demo)
        self.assertEqual(len(demo['actions']),1)

    async def test_cancelled_gesture_not_recorded_as_tap(self):
        self.catalog.record('phone','touch',{'action':'down','x':1,'y':2})
        self.catalog.record('phone','touch',{'action':'cancel','x':1,'y':2})
        self.catalog.record('phone','touch',{'action':'up','x':1,'y':2})
        self.assertEqual(self.runtime.store.get('demonstration',self.demo['id'])['actions'],[])


@unittest.skipUnless(shutil.which('node'),'Node required for browser handler checks')
class ModeButtonTests(unittest.TestCase):
    def test_repeated_live_button_never_sends_touch_and_mode_change_only_cancels(self):
        source=(Path(__file__).resolve().parents[1]/'web_app/static/js/main.js').read_text()
        functions=source[source.index('function cancelPreviewGesture()'):source.index('function showReplaySurface()')]
        script='''const assert=require('node:assert/strict');
        const sent=[],ref=value=>({value});
        const touchState={isDown:false,lastX:80,lastY:120,lastW:100,lastH:200};
        const previewMode=ref('live'),previewCanvas=ref({blur(){}}),showPhonePreview=ref(true),previewDeviceId=ref('phone');
        const document={activeElement:null};
        const _sendTouch=(...args)=>sent.push(args);
        const automation={stopPlayback(){}};
        async function pauseActiveRecording(){} async function openPhonePreview(){} async function openPreviewReplay(){}
        '''+functions+'''
        (async()=>{
          for(let i=0;i<10;i++){cancelPreviewGesture();await setPreviewMode('live');}
          assert.equal(sent.length,0);
          touchState.isDown=true;cancelPreviewGesture();await setPreviewMode('record');
          assert.deepEqual(sent.map(e=>e[0]),['cancel']);assert.equal(touchState.isDown,false);
          await setPreviewMode('live');assert.equal(sent.length,1);
        })().catch(e=>{console.error(e);process.exitCode=1;});'''
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
