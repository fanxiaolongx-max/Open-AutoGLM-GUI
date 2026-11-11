import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node required")
class SidebarFrontendTests(unittest.TestCase):
    def test_sidebar_state_clamping_labels_and_drag_controller(self):
        root = Path(__file__).resolve().parents[1]
        source = root / "web_app/static/js/sidebar.js"

        with tempfile.TemporaryDirectory() as folder:
            module = Path(folder) / "sidebar.mjs"
            module.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

            script = (
                """import assert from 'node:assert/strict';
                const {
                    SIDEBAR_CONFIG,
                    computeMaxSidebarWidth,
                    clampSidebarWidth,
                    resolveSidebarWidth,
                    loadSidebarState,
                    saveSidebarState,
                    getSessionCompactLabel,
                    createSidebarController,
                } = await import("""
                + json.dumps(module.as_uri())
                + """);

                // 1. Clamping & viewport-aware max widths
                assert.equal(clampSidebarWidth('nav', NaN), SIDEBAR_CONFIG.nav.defaultWidth);
                assert.equal(clampSidebarWidth('nav', 80), SIDEBAR_CONFIG.nav.minWidth);
                assert.equal(clampSidebarWidth('nav', 900), SIDEBAR_CONFIG.nav.maxWidth);
                assert.equal(clampSidebarWidth('chat', 50), SIDEBAR_CONFIG.chat.minWidth);
                assert.equal(clampSidebarWidth('chat', 900), SIDEBAR_CONFIG.chat.maxWidth);

                const narrowChatMax = computeMaxSidebarWidth('chat', 900, { navWidth: 300, navCollapsed: false });
                assert.equal(narrowChatMax, 300); // 900 - 300(nav) - 300(reserved)
                assert.equal(
                    resolveSidebarWidth('chat', true, 320, 1440, { navWidth: 240, navCollapsed: false }),
                    SIDEBAR_CONFIG.chat.collapsedWidth,
                );
                assert.equal(
                    resolveSidebarWidth('chat', false, 450, 900, { navWidth: 300, navCollapsed: false }),
                    300,
                );

                // 2. Persistence load & save
                const store = new Map();
                const storage = {
                    getItem: (k) => (store.has(k) ? store.get(k) : null),
                    setItem: (k, v) => store.set(k, String(v)),
                };
                store.set(SIDEBAR_CONFIG.nav.widthStorageKey, 'corrupt');
                store.set(SIDEBAR_CONFIG.chat.collapsedStorageKey, 'true');
                let loaded = loadSidebarState(storage);
                assert.equal(loaded.nav.width, 240);
                assert.equal(loaded.nav.collapsed, false);
                assert.equal(loaded.chat.collapsed, true);

                saveSidebarState(storage, 'nav', { width: 312.6, collapsed: true });
                saveSidebarState(storage, 'chat', { width: 295, collapsed: false });
                loaded = loadSidebarState(storage);
                assert.deepEqual(loaded.nav, { width: 313, collapsed: true });
                assert.deepEqual(loaded.chat, { width: 295, collapsed: false });

                // 3. Compact session badges
                assert.equal(getSessionCompactLabel({ title: '1+1' }), '1+');
                assert.equal(getSessionCompactLabel({ title: '你好' }), '你');
                assert.equal(getSessionCompactLabel({ title: '✈️ Telegram Chat Mode' }), '✈️');
                assert.equal(getSessionCompactLabel({ title: '/shell dumpsys power' }), '/s');
                assert.equal(getSessionCompactLabel({ title: '@MEIZU_20 打开' }), '@M');
                assert.equal(getSessionCompactLabel({ title: '   ' }), '新');

                // 4. Drag resize & toggle lifecycle
                const ref = (value) => ({ value });
                const navWidth = ref(240);
                const navCollapsed = ref(false);
                const chatWidth = ref(220);
                const chatCollapsed = ref(false);
                const activeDrag = ref('');
                const cssProps = new Map();
                const containerEl = { style: { setProperty: (k, v) => cssProps.set(k, v) } };
                const listeners = new Map();
                const bodyClasses = new Set();
                const queuedFrames = [];

                const win = {
                    addEventListener(type, fn) {
                        if (!listeners.has(type)) listeners.set(type, new Set());
                        listeners.get(type).add(fn);
                    },
                    removeEventListener(type, fn) {
                        listeners.get(type)?.delete(fn);
                    },
                    dispatch(type, evt = {}) {
                        for (const fn of Array.from(listeners.get(type) || [])) fn(evt);
                    },
                };
                const doc = {
                    body: {
                        classList: {
                            add: (cls) => bodyClasses.add(cls),
                            remove: (cls) => bodyClasses.delete(cls),
                        },
                    },
                };
                const controller = createSidebarController({
                    navWidth,
                    navCollapsed,
                    chatWidth,
                    chatCollapsed,
                    activeDrag,
                    getContainerEl: () => containerEl,
                    getViewportWidth: () => 1440,
                    storage,
                    win,
                    doc,
                    requestFrame: (cb) => {
                        queuedFrames.push(cb);
                        return queuedFrames.length;
                    },
                    cancelFrame: (id) => {
                        if (id >= 1 && id <= queuedFrames.length) queuedFrames[id - 1] = null;
                    },
                });

                // Dragging nav sidebar smoothly via rAF coalescing
                let prevented = false;
                controller.startResize('nav', { button: 0, clientX: 240, preventDefault: () => { prevented = true; } });
                assert.equal(prevented, true);
                assert.equal(activeDrag.value, 'nav');
                assert.equal(bodyClasses.has('sidebar-resizing'), true);

                // Multiple pointermoves before rAF fires coalesce to latest position
                win.dispatch('pointermove', { clientX: 280 });
                win.dispatch('pointermove', { clientX: 325 });
                assert.equal(queuedFrames.filter(Boolean).length, 1);
                queuedFrames.shift()();
                assert.equal(navWidth.value, 325);
                assert.equal(cssProps.get('--nav-sidebar-width'), '325px');

                // Drag beyond max clamps cleanly & pointerup persists
                win.dispatch('pointermove', { clientX: 800 });
                win.dispatch('pointerup', {});
                assert.equal(navWidth.value, SIDEBAR_CONFIG.nav.maxWidth);
                assert.equal(activeDrag.value, '');
                assert.equal(bodyClasses.has('sidebar-resizing'), false);
                assert.equal(listeners.get('pointermove')?.size || 0, 0);
                assert.equal(store.get(SIDEBAR_CONFIG.nav.widthStorageKey), String(SIDEBAR_CONFIG.nav.maxWidth));

                // Double-click reset + collapse toggle prevents drag while collapsed
                controller.resetWidth('nav');
                assert.equal(navWidth.value, 240);
                controller.toggle('chat');
                assert.equal(chatCollapsed.value, true);
                controller.startResize('chat', { button: 0, clientX: 220 });
                assert.equal(activeDrag.value, '');
                controller.toggle('chat');
                assert.equal(chatCollapsed.value, false);
                controller.startResize('chat', { button: 0, clientX: 220 });
                assert.equal(activeDrag.value, 'chat');
                controller.cleanup();
                assert.equal(activeDrag.value, '');
                assert.equal(bodyClasses.has('sidebar-resizing'), false);
                """
            )
            result = subprocess.run(
                ["node", "--input-type=module", "-e", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_sidebar_html_css_and_main_wiring(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "web_app/static/index.html").read_text(encoding="utf-8")
        css = (root / "web_app/static/css/style.css").read_text(encoding="utf-8")
        main_js = (root / "web_app/static/js/main.js").read_text(encoding="utf-8")

        self.assertIn("style.css?v=20261111-sidebar-resize", html)
        self.assertIn("main.js?v=20261111-sidebar-resize", html)
        self.assertIn("is-resizing-sidebar", html)
        self.assertIn("toggleNavSidebar", html)
        self.assertIn("toggleChatSidebar", html)
        self.assertIn("startSidebarResize('nav', $event)", html)
        self.assertIn("startSidebarResize('chat', $event)", html)
        self.assertIn("chat-session-compact-badge", html)

        self.assertIn("--nav-sidebar-width", css)
        self.assertIn(".sidebar.collapsed", css)
        self.assertIn(".sidebar-resizer", css)
        self.assertIn("body.sidebar-resizing", css)

        self.assertIn("./sidebar.js?v=20261111-sidebar-resize", main_js)
        self.assertIn("sidebarController.cleanup()", main_js)
