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


class KeyboardTextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = ScrcpyService()
        self.service._ime_restore_delay = 0.05
        self.session = ScrcpySession('phone', screen_width=1080, screen_height=2400)
        self.service._sessions['phone'] = self.session
        self.send_text = ScrcpyService.send_text.__wrapped__
        self.send_key = ScrcpyService.send_key.__wrapped__

    async def asyncTearDown(self):
        self.service.flush_ime_restore('phone')

    async def test_adb_keyboard_batches_ime_switch_and_auto_restores(self):
        cmds = []

        def fake_run(cmd, **kwargs):
            cmds.append(cmd)
            joined = ' '.join(cmd)
            if 'settings get secure default_input_method' in joined:
                return SimpleNamespace(returncode=0, stdout='com.sohu.inputmethod.sogou.meizu/.SogouIME\n', stderr='')
            if 'ime list -s' in joined:
                return SimpleNamespace(
                    returncode=0,
                    stdout='com.sohu.inputmethod.sogou.meizu/.SogouIME\ncom.android.adbkeyboard/.AdbIME\n',
                    stderr='',
                )
            return SimpleNamespace(returncode=0, stdout='Broadcast completed: result=0\n', stderr='')

        with patch('web_app.services.scrcpy_service.subprocess.run', side_effect=fake_run):
            ok1 = await self.send_text(self.service, 'phone', 'Hello_01!')
            ok2 = await self.send_text(self.service, 'phone', '你好世界\r\nline2')
            self.assertTrue(ok1)
            self.assertTrue(ok2)

            ime_sets = [c for c in cmds if c[:4] == ['adb', '-s', 'phone', 'shell'] and c[4:6] == ['ime', 'set']]
            self.assertEqual(ime_sets, [['adb', '-s', 'phone', 'shell', 'ime', 'set', 'com.android.adbkeyboard/.AdbIME']])

            broadcasts = [c for c in cmds if 'ADB_INPUT_B64' in c]
            self.assertEqual(len(broadcasts), 2)
            self.assertEqual(base64.b64decode(broadcasts[0][-1]).decode('utf-8'), 'Hello_01!')
            self.assertEqual(base64.b64decode(broadcasts[1][-1]).decode('utf-8'), '你好世界\nline2')

            import asyncio
            await asyncio.sleep(0.15)
            ime_sets_after = [c for c in cmds if c[:4] == ['adb', '-s', 'phone', 'shell'] and c[4:6] == ['ime', 'set']]
            self.assertEqual(ime_sets_after[-1][-1], 'com.sohu.inputmethod.sogou.meizu/.SogouIME')

    async def test_flush_ime_restore_runs_synchronously(self):
        self.service._ime_restore_delay = 5.0
        cmds = []

        def fake_run(cmd, **kwargs):
            cmds.append(cmd)
            joined = ' '.join(cmd)
            if 'settings get secure default_input_method' in joined:
                return SimpleNamespace(returncode=0, stdout='com.sohu.inputmethod.sogou.meizu/.SogouIME\n', stderr='')
            if 'ime list -s' in joined:
                return SimpleNamespace(returncode=0, stdout='com.android.adbkeyboard/.AdbIME\n', stderr='')
            return SimpleNamespace(returncode=0, stdout='', stderr='')

        with patch('web_app.services.scrcpy_service.subprocess.run', side_effect=fake_run):
            self.assertTrue(await self.send_text(self.service, 'phone', 'abc'))
            self.assertIn('phone', self.service._ime_sessions)
            self.service.flush_ime_restore('phone')
            self.assertNotIn('phone', self.service._ime_sessions)
            self.assertEqual(
                cmds[-1],
                ['adb', '-s', 'phone', 'shell', 'ime', 'set', 'com.sohu.inputmethod.sogou.meizu/.SogouIME'],
            )

    async def test_scrcpy_fallback_when_adb_keyboard_missing(self):
        def fake_run(cmd, **kwargs):
            joined = ' '.join(cmd)
            if 'settings get secure default_input_method' in joined:
                return SimpleNamespace(returncode=0, stdout='com.sohu.inputmethod.sogou.meizu/.SogouIME\n', stderr='')
            if 'ime list' in joined:
                return SimpleNamespace(returncode=0, stdout='com.sohu.inputmethod.sogou.meizu/.SogouIME\n', stderr='')
            return SimpleNamespace(returncode=1, stdout='', stderr='')

        packets = []
        with patch('web_app.services.scrcpy_service.subprocess.run', side_effect=fake_run), \
             patch.object(self.service, '_can_use_scrcpy_control', return_value=True), \
             patch.object(
                 self.service,
                 '_send_scrcpy_control_packet',
                 side_effect=lambda sess, dev, pkt, label: packets.append((label, pkt)) or True,
             ):
            self.assertTrue(await self.send_text(self.service, 'phone', 'User@123'))
            self.assertTrue(await self.send_text(self.service, 'phone', '中文粘贴'))
            self.assertTrue(await self.send_text(self.service, 'phone', 'line1\nline2'))

        self.assertEqual(packets[0][0], 'text')
        self.assertEqual(packets[0][1][0], 1)  # TYPE_INJECT_TEXT
        self.assertEqual(packets[1][0], 'clipboard-paste')
        self.assertEqual(packets[1][1][0], 9)  # TYPE_SET_CLIPBOARD
        self.assertEqual(packets[2][0], 'clipboard-paste')
        self.assertEqual(packets[2][1][0], 9)

    async def test_adb_ascii_fallback_empty_noop_and_meta_key_guard(self):
        cmds = []

        def fake_run(cmd, **kwargs):
            cmds.append(cmd)
            joined = ' '.join(cmd)
            if 'ime list' in joined:
                return SimpleNamespace(returncode=0, stdout='com.sohu.inputmethod.sogou.meizu/.SogouIME\n', stderr='')
            if 'settings get secure default_input_method' in joined:
                return SimpleNamespace(returncode=0, stdout='com.sohu.inputmethod.sogou.meizu/.SogouIME\n', stderr='')
            return SimpleNamespace(returncode=0, stdout='', stderr=b'')

        with patch('web_app.services.scrcpy_service.subprocess.run', side_effect=fake_run):
            self.assertFalse(await self.send_text(self.service, 'phone', ''))
            self.assertEqual(cmds, [])

            self.assertTrue(await self.send_text(self.service, 'phone', 'hello world'))
            input_cmds = [c for c in cmds if c[4:6] == ['input', 'text']]
            self.assertEqual(len(input_cmds), 1)
            self.assertEqual(input_cmds[0][-1], 'hello%sworld')

            cmds.clear()
            await self.send_key(self.service, 'phone', 29, meta_state=0x3000)
            self.assertEqual(cmds, [])

        with patch.object(self.service, '_can_use_scrcpy_control', return_value=True), \
             patch.object(self.service, '_send_scrcpy_control_packet', return_value=True), \
             patch.object(self.service, '_pack_scrcpy_key_message', return_value=b'k') as pack_key:
            await self.send_key(self.service, 'phone', 29, meta_state=0x3000)
            self.assertEqual(
                [(c.kwargs['action'], c.kwargs['keycode'], c.kwargs['meta_state']) for c in pack_key.call_args_list],
                [(0, 29, 0x3000), (1, 29, 0x3000)],
            )

    def test_send_text_has_manual_input_wrapper(self):
        self.assertTrue(hasattr(ScrcpyService.send_text, '__wrapped__'))


@unittest.skipUnless(shutil.which('node'), 'Node required for browser keyboard handler checks')
class PreviewKeyboardFrontendTests(unittest.TestCase):
    def test_keyboard_ime_paste_and_shortcuts_in_main_js(self):
        source = (Path(__file__).resolve().parents[1] / 'web_app/static/js/main.js').read_text()
        keyboard_block = source[
            source.index('function isPreviewKeyboardReady()'):source.index('function mapBrowserKeyToAndroidKeycode(')
        ]
        handle_start = source.index('function handlePreviewKeyboard(event)')
        handle_end = source.index('function onCanvasTouchStart', handle_start) if 'function onCanvasTouchStart' in source[handle_start:] else source.index('function togglePreviewFullscreen', handle_start) if 'function togglePreviewFullscreen' in source[handle_start:] else handle_start
        # Extract handlePreviewKeyboard cleanly by balanced brace scan
        brace_depth = 0
        end_idx = None
        for idx in range(source.index('{', handle_start), len(source)):
            ch = source[idx]
            if ch == '{':
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if brace_depth == 0:
                    end_idx = idx + 1
                    break
        self.assertIsNotNone(end_idx)
        handle_block = source[handle_start:end_idx]

        script = '''const assert = require('node:assert/strict');
        const sent = [];
        const ref = (value) => ({ value });
        const WebSocket = { OPEN: 1 };
        const streamWs = { readyState: 1, send: (msg) => sent.push(JSON.parse(msg)) };
        const showPhonePreview = ref(true);
        const previewMode = ref('live');
        const streamConnected = ref(true);
        const previewDeviceId = ref('phone');
        const previewCanvas = ref({ focus(){}, blur(){} });
        const previewTextInput = ref({ value: '', focus(){}, blur(){} });
        let previewComposing = false;
        const document = { activeElement: previewTextInput.value };
        function startStreamWithSettings() {}
        function mapBrowserKeyToAndroidKeycode(e) { return e.key === 'Backspace' ? 67 : null; }
        ''' + keyboard_block + '\n' + handle_block + '''
        const makeEvt = (overrides = {}) => {
          let prevented = false, stopped = false;
          return {
            preventDefault() { prevented = true; },
            stopPropagation() { stopped = true; },
            get _prevented() { return prevented; },
            get _stopped() { return stopped; },
            currentTarget: previewTextInput.value,
            ...overrides,
          };
        };

        // 1. Direct English + Shift symbol typing
        previewTextInput.value.value = 'Abc@123!';
        onPreviewTextInput(makeEvt({ isComposing: false }));
        assert.equal(previewTextInput.value.value, '');
        assert.deepEqual(sent.pop(), { type: 'text', text: 'Abc@123!' });

        // 2. Chinese IME composition does not send raw pinyin or intercept Enter/Backspace while composing
        onPreviewCompositionStart();
        const imeBs = makeEvt({ key: 'Backspace', isComposing: true });
        onPreviewInputKeydown(imeBs);
        assert.equal(imeBs._prevented, false);
        previewTextInput.value.value = 'nihao';
        onPreviewTextInput(makeEvt({ isComposing: true }));
        assert.equal(sent.length, 0);
        previewTextInput.value.value = '你好世界';
        onPreviewCompositionEnd(makeEvt({ data: '你好世界' }));
        assert.equal(previewTextInput.value.value, '');
        assert.deepEqual(sent.pop(), { type: 'text', text: '你好世界' });
        // Trailing post-composition input event sees empty textarea and does not duplicate
        onPreviewTextInput(makeEvt({ isComposing: false }));
        assert.equal(sent.length, 0);

        // 3. Blur cleans stuck composing state
        onPreviewCompositionStart();
        previewTextInput.value.value = 'ni';
        onPreviewInputBlur(makeEvt());
        assert.equal(previewTextInput.value.value, '');
        previewTextInput.value.value = 'ok';
        onPreviewTextInput(makeEvt({ isComposing: false }));
        assert.deepEqual(sent.pop(), { type: 'text', text: 'ok' });

        // 4. Paste
        const pasteEvt = makeEvt({ clipboardData: { getData: (t) => (t === 'text/plain' ? 'line1\\nline2' : '') } });
        onPreviewPaste(pasteEvt);
        assert.equal(pasteEvt._prevented, true);
        assert.deepEqual(sent.pop(), { type: 'text', text: 'line1\\nline2' });

        // 5. Special keys & Shift+Arrow
        const bsEvt = makeEvt({ key: 'Backspace', shiftKey: false });
        onPreviewInputKeydown(bsEvt);
        assert.equal(bsEvt._prevented, true);
        assert.deepEqual(sent.pop(), { type: 'key', keycode: 67 });

        const shiftLeft = makeEvt({ key: 'ArrowLeft', shiftKey: true });
        onPreviewInputKeydown(shiftLeft);
        assert.deepEqual(sent.pop(), { type: 'key', keycode: 21, meta_state: 0x41 });

        // 6. Shortcuts: Cmd/Ctrl + V (defer to paste), A/C/X/Z (send key), R (ignored)
        const cmdV = makeEvt({ key: 'v', metaKey: true });
        onPreviewInputKeydown(cmdV);
        assert.equal(cmdV._prevented, false);
        assert.equal(sent.length, 0);

        onPreviewInputKeydown(makeEvt({ key: 'a', metaKey: true }));
        assert.deepEqual(sent.pop(), { type: 'key', keycode: 29, meta_state: 0x3000 });
        onPreviewInputKeydown(makeEvt({ key: 'c', ctrlKey: true }));
        assert.deepEqual(sent.pop(), { type: 'key', keycode: 278 });
        onPreviewInputKeydown(makeEvt({ key: 'x', metaKey: true }));
        assert.deepEqual(sent.pop(), { type: 'key', keycode: 277 });
        onPreviewInputKeydown(makeEvt({ key: 'z', ctrlKey: true }));
        assert.deepEqual(sent.pop(), { type: 'key', keycode: 54, meta_state: 0x3000 });
        onPreviewInputKeydown(makeEvt({ key: 'r', metaKey: true }));
        assert.equal(sent.length, 0);

        // 7. Window handlePreviewKeyboard skips when textarea is active
        handlePreviewKeyboard(makeEvt({ key: 'Backspace' }));
        assert.equal(sent.length, 0);

        // 8. Replay mode blocks text & paste
        previewMode.value = 'replay';
        previewTextInput.value.value = 'blocked';
        onPreviewTextInput(makeEvt({ isComposing: false }));
        onPreviewPaste(makeEvt({ clipboardData: { getData: () => 'blocked' } }));
        assert.equal(sent.length, 0);
        '''
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

