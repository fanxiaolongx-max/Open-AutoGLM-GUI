import {ApiError} from './automation/api.js?v=20261024-context-preview';
import {useAutomation} from './automation/app.js?v=20261024-context-preview';
import * as automationComponents from './automation/components.js?v=20261024-context-preview';
import {isTerminal} from './automation/tasks.js?v=20261024-context-preview';
import {createContextMonitor} from './chat-context.js?v=20261024-compaction';
        // Wait for Vue to load, with fallback
        function initApp() {
            if (typeof Vue === 'undefined') {
                document.getElementById('app').innerHTML = '<div style="padding: 40px; text-align: center;"><h2>Loading failed</h2><p>Unable to load Vue.js. Please check your internet connection.</p><button onclick="location.reload()">Retry</button></div>';
                return;
            }

            const { createApp, ref, computed, onMounted, onUnmounted, watch } = Vue;

            const app = createApp({
                components: automationComponents,
                setup() {
                    // State
                    const schedulerTab = ref('schedule');
                    const activeRunTaskId = ref('');
                    const taskAcceptance = ref('');
                    const chatAcceptance = ref('');
                    const previewMode = ref('live');
                    const replayImageUnavailable = ref(false);
                    const schedulerRecipeDefinition = ref(null);
                    const currentPage = ref('chat');  // Default to chat page
                    const authChecking = ref(true);
                    const isAuthenticated = ref(false);
                    const currentUsername = ref('');
                    const defaultCredentials = ref(false);
                    const loginLoading = ref(false);
                    const loginError = ref('');
                    const loginForm = ref({ username: 'admin', password: '' });
                    const credentialsSaving = ref(false);
                    const credentialsForm = ref({
                        username: '',
                        current_password: '',
                        new_password: '',
                        confirm_password: '',
                    });
                    let authenticatedAppInitialized = false;
                    const devices = ref([]);
                    const selectedDevices = ref([]);
                    const taskContent = ref('');
                    const taskRunning = ref(false);
                    const taskProgress = ref(0);
                    const taskLogs = ref([]);
                    const taskScreenshot = ref('');
                    const parallelExecution = ref(false);  // Parallel multi-device execution
                    const scheduledTasks = ref([]);
                    const modelServices = ref([]);
                    const activeModel = ref(null);
                    const modelPresets = ref([]);
                    const showModelForm = ref(false);
                    const modelFormMode = ref('create');
                    const modelForm = ref(getDefaultModelForm());

                    function getDefaultModelForm() {
                        return {
                            id: '',
                            name: '',
                            base_url: '',
                            api_key: '',
                            model_name: '',
                            max_tokens: 3000,
                            context_window: 0,
                            temperature: 0.0,
                            top_p: 0.85,
                            frequency_penalty: 0.2,
                            description: '',
                            is_active: false,
                            protocol: 'openai',
                            category: '',
                        };
                    }

                    function onModelProtocolChange() {
                        if (modelForm.value.protocol !== 'ollama') {
                            return;
                        }
                        if (!modelForm.value.base_url) {
                            modelForm.value.base_url = 'http://127.0.0.1:11434/v1';
                        }
                        if (!modelForm.value.model_name) {
                            modelForm.value.model_name = 'qwen2.5:7b';
                        }
                    }
                    const emailConfig = ref({});
                    const screenshotConfig = ref({
                        max_dimension: 1920,
                        jpeg_quality: 70
                    });

                    // Telegram Bot configuration
                    const telegramConfig = ref({
                        bot_token: '',
                        enabled: false,
                        allowed_users: [],
                        send_screenshots: true,
                        send_logs: true,
                        status: 'stopped'
                    });
                    const telegramAllowedUsersStr = ref('');
                    const telegramBotInfo = ref(null);

                    // Rules configuration state
                    const appMappings = ref([]);
                    const timingConfig = ref(null);
                    const systemPrompts = ref(null);
                    const showAddAppModal = ref(false);
                    const editingApp = ref(null);
                    const appForm = ref({ app_name: '', package_name: '' });
                    // Action rules state
                    const actionRules = ref([]);
                    const expandedActions = ref({});
                    const showRuleModal = ref(false);
                    const editingRuleAction = ref('');
                    const editingRule = ref(null);
                    const ruleForm = ref({ condition: '', action: '', priority: 0, enabled: true });
                    const wsConnected = ref(false);
                    const loading = ref(false);
                    const toasts = ref([]);
                    const systemAlerts = ref([]);  // System alerts (banners from backend)
                    const devicePins = ref({});
                    const pinInputValues = ref({});  // Store input values for PIN fields
                    const showPinFor = ref('');  // Device ID for which PIN is visible
                    // Wireless pairing state
                    const pairAddress = ref('');
                    const pairCode = ref('');
                    const connectAddress = ref('');
                    const pairingLoading = ref(false);
                    const connectingLoading = ref(false);
                    const deviceLogs = ref([]);
                    // APK install state
                    const apkTargetDevice = ref('');
                    const apkFile = ref(null);
                    const apkInstalling = ref(false);
                    const monitorDeviceId = ref('');
                    const monitorStarting = ref(false);
                    const monitorMessage = ref('');
                    const monitorSuccess = ref(false);
                    const ipCamStreamUrl = ref('');
                    const ipCamImgError = ref(false);
                    const ipWebcamLaunching = ref(false);
                    const streamConfig = ref([{ url: '', name: '摄像头 1' }, { url: '', name: '摄像头 2' }, { url: '', name: '摄像头 3' }, { url: '', name: '摄像头 4' }]);
                    const gridConfigExpanded = ref(false);
                    const streamErrors = ref([false, false, false, false]);
                    const gridImgRefs = ref([null, null, null, null]);
                    const gridRecordCanvas = ref(null);
                    const gridRecording = ref(false);
                    let gridMediaRecorder = null;
                    let gridRecordChunks = [];
                    let gridRecordAnimationId = null;
                    const apkLogs = ref([]);
                    const apkFileInput = ref(null);
                    // File manager state
                    const fileDevice = ref('');
                    const filePath = ref('/sdcard');
                    const fileList = ref([]);
                    const fileLoading = ref(false);
                    const uploadSelectedFile = ref(null);
                    const fileUploading = ref(false);
                    const uploadFileInput = ref(null);
                    const logContainer = ref(null);
                    const showSchedulerForm = ref(false);
                    const schedulerFormMode = ref('create');
                    const schedulerForm = ref(getDefaultSchedulerForm());
                    // Scheduler logs state
                    const schedulerLogs = ref([]);
                    const showLogDetailModal = ref(false);
                    const logDetailData = ref({});

                    // Phone preview state
                    const showPhonePreview = ref(false);
                    const previewDeviceId = ref('');
                    const previewImage = ref(null);
                    const previewLoading = ref(false);
                    const previewPosition = ref({ x: 100, y: 100 });
                    const previewWidth = ref(270);
                    const previewAspect = ref(16 / 9);  // height/width ratio, updated from stream
                    const PREVIEW_TOOLBAR_WIDTH = 92;
                    const PREVIEW_TOOLBAR_HEIGHT_LANDSCAPE = 72;
                    const PREVIEW_SAFE_MARGIN = 28;
                    const PREVIEW_FIRST_OPEN_HINT_KEY = 'preview_first_open_hint_shown_v1';
                    let previewInterval = null;
                    let isDragging = false;
                    let isResizing = false;
                    let dragOffset = { x: 0, y: 0 };
                    let resizeStart = { x: 0, w: 0, left: 0, top: 0, edge: 'right' };

                    // Scrcpy stream state
                    const streamConnected = ref(false);
                    const streamConnecting = ref(false);
                    const streamReady = ref(false);
                    const streamLoadingText = ref('Connecting...');
                    const streamOrientationSwitching = ref(false);
                    const streamSwitchProgress = ref(0);
                    const streamFps = ref(0);
                    const streamMaxSize = ref(960);
                    const streamTargetFps = ref(24);
                    const streamBitRate = ref(4000000);
                    const streamAutoAdapt = ref(false);
                    const streamUseScrcpyControl = ref(true); // Advanced: on by default
                    const streamAudioEnabled = ref(false); // Separate passthrough audio channel (default off)
                    const streamAudioConnected = ref(false);
                    const streamAudioCodec = ref('raw');
                    const streamAudioSampleRate = ref(48000);
                    const streamAudioChannels = ref(2);
                    const streamControlActive = ref(false);
                    const streamVideoBitrateKbps = ref(0);
                    const streamAudioBitrateKbps = ref(0);
                    const streamLatencyMs = ref(0);
                    const streamLatencyJitterMs = ref(0);
                    const streamFrameJitterMs = ref(0);
                    const streamAudioJitterMs = ref(0);
                    const canvasWidth = ref(300);
                    const canvasHeight = ref(540);
                    const deviceScreenWidth = ref(0);
                    const deviceScreenHeight = ref(0);
                    const streamDisplayRotation = ref(0);
                    const streamSourceWidth = ref(0);
                    const streamSourceHeight = ref(0);
                    const previewCanvas = ref(null);
                    let streamWs = null;
                    let streamAudioWs = null;
                    let streamConnectToken = 0;
                    let streamSwitchTimer = null;
                    let fpsCounter = 0;
                    let fpsTimer = null;
                    let autoAdaptLowFpsStreak = 0;
                    let autoAdaptCooldownUntil = 0;
                    let wheelDeltaAccum = 0;
                    let wheelTimer = null;
                    let audioContext = null;
                    let audioProcessorNode = null;
                    let audioQueue = [];
                    let audioQueueOffset = 0;
                    const AUDIO_QUEUE_TARGET_MS = 100;
                    const AUDIO_QUEUE_MAX_MS = 120;
                    let telemetryVideoBytes = 0;
                    let telemetryAudioBytes = 0;
                    let telemetryTimer = null;
                    let telemetryProbeTimer = null;
                    let telemetryProbeSeq = 0;
                    const telemetryPendingProbeTs = new Map();
                    let telemetryLastVideoTs = 0;
                    let telemetryLastAudioTs = 0;
                    let telemetryVideoIntervalAvg = 0;
                    let telemetryAudioIntervalAvg = 0;
                    let telemetryRttAvg = 0;
                    let touchState = {
                        isDown: false, startX: 0, startY: 0, startTime: 0,
                        lastX: 0, lastY: 0, lastW: 0, lastH: 0,
                        longPressTimer: null, hasMoved: false
                    };

                    // Chat state
                    const chatMessages = ref([]);
                    const chatInput = ref('');
                    const chatDeviceId = ref('');
                    const chatRunning = ref(false);
                    const chatSegmentSequenceRunning = ref(false);
                    const chatMessagesRef = ref(null);
                    const chatAutoEmail = ref(false);  // Default: no auto email in chat mode
                    const complexTaskMode = ref(false);  // 复杂任务模式：先拆解成todolist再逐个执行
                    const debugMode = ref(false);  // 调试模式：点击前显示预览
                    const darkMode = ref(false);  // 暗黑模式
                    const currentLanguage = ref('zh');  // 语言设置: 'zh' 或 'en'

                    // Cloudflare Tunnel state
                    const tunnelStatus = ref('stopped'); // stopped | starting | running | error
                    const tunnelUrl = ref('');
                    const tunnelError = ref('');
                    const awaitingTodoListConfirmation = ref(false);  // 是否正在等待用户确认todoList
                    const subtaskTimeoutSeconds = ref(180);  // 子任务超时时间（秒），默认3分钟
                    const subtaskCountdown = ref(0);  // 子任务剩余秒数（用于倒计时显示）
                    let subtaskCountdownTimer = null;  // 倒计时定时器
                    let currentChatTaskId = null;
                    let chatScrollPosition = 0;  // 保存 Chat 滚动位置
                    const chatCursorPos = ref(0);
                    const adbSuggestionIndex = ref(-1);
                    const deviceMentionSuggestionIndex = ref(-1);
                    const adbQuickCommands = [
                        { command: '/help', desc: '查看 Slash 指令帮助' },
                        { command: '/shell input keyevent 26', desc: '点亮/熄灭屏幕（电源键）' },
                        { command: '/shell input keyevent 82', desc: '解锁滑动前唤醒菜单键' },
                        { command: '/shell screencap -p /sdcard/Download/shot.png', desc: '截图到设备存储' },
                        { command: '/shell settings get secure android_id', desc: '查看 Android ID' },
                        { command: '/shell wm size', desc: '查看屏幕分辨率' },
                        { command: '/shell wm density', desc: '查看屏幕密度' },
                        { command: '/shell settings get system screen_brightness', desc: '查看亮度值' },
                        { command: '/shell dumpsys battery', desc: '查看电池状态' },
                        { command: '/shell dumpsys power', desc: '查看电源状态' },
                        { command: '/shell dumpsys window', desc: '查看窗口与焦点信息' },
                        { command: '/shell dumpsys display', desc: '查看显示状态' },
                        { command: '/shell dumpsys activity activities', desc: '查看 Activity 栈' },
                        { command: '/shell dumpsys package', desc: '查看包管理信息' },
                        { command: '/shell dumpsys meminfo', desc: '查看内存概览' },
                        { command: '/shell getprop ro.product.model', desc: '查看设备型号' },
                        { command: '/shell getprop ro.build.version.release', desc: '查看 Android 版本' },
                        { command: '/shell getprop ro.build.version.sdk', desc: '查看 SDK 版本' },
                        { command: '/shell getprop ro.product.brand', desc: '查看品牌' },
                        { command: '/shell pm list packages', desc: '查看已安装应用' },
                        { command: '/shell pm list packages -3', desc: '查看第三方应用' },
                        { command: '/shell pm list packages -s', desc: '查看系统应用' },
                        { command: '/shell pm path com.android.settings', desc: '查看应用 APK 路径' },
                        { command: '/shell ls /sdcard', desc: '查看 SDCard 根目录' },
                        { command: '/shell ls /sdcard/Download', desc: '查看下载目录' },
                        { command: '/shell df -h', desc: '查看磁盘占用' },
                        { command: '/shell free -h', desc: '查看内存占用（设备支持时）' },
                        { command: '/shell ip addr', desc: '查看网络地址（设备支持时）' },
                        { command: '/shell settings list system', desc: '查看系统设置项' },
                        { command: '/shell settings list secure', desc: '查看安全设置项' },
                        { command: '/shell settings list global', desc: '查看全局设置项' },
                        { command: '/shell ip route', desc: '查看路由表（设备支持时）' },
                        { command: '/shell cat /proc/meminfo', desc: '查看内存详情' },
                        { command: '/key KEYCODE_HOME', desc: '按 Home 键' },
                        { command: '/key KEYCODE_BACK', desc: '按返回键' },
                        { command: '/tap 540 1800', desc: '点击坐标' },
                        { command: '/swipe 540 1800 540 400 260', desc: '上滑手势' },
                        { command: '/text hello%sworld', desc: '输入文本（空格用 %s）' },
                        { command: '/am start -a android.settings.SETTINGS', desc: '打开系统设置' },
                        { command: '/am force-stop com.tencent.mm', desc: '强制停止 App（修改）' },
                        { command: '/pm clear com.tencent.mm', desc: '清除 App 数据（修改）' },
                        { command: '/pm disable-user --user 0 com.android.browser', desc: '禁用应用（修改）' },
                        { command: '/pm enable com.android.browser', desc: '启用应用（修改）' },
                        { command: '/settings put system screen_brightness 120', desc: '设置亮度（修改）' },
                        { command: '/settings put system screen_off_timeout 600000', desc: '设置息屏超时10分钟（修改）' },
                        { command: '/settings put secure show_touches 1', desc: '开启触摸点显示（修改）' },
                        { command: '/settings put secure show_touches 0', desc: '关闭触摸点显示（修改）' },
                        { command: '/settings put global animator_duration_scale 0.5', desc: '动画速度 0.5x（修改）' },
                        { command: '/settings put global transition_animation_scale 0.5', desc: '过渡动画 0.5x（修改）' },
                        { command: '/settings put global window_animation_scale 0.5', desc: '窗口动画 0.5x（修改）' },
                        { command: '/settings put global adb_enabled 1', desc: '开启 adb 调试标记（修改，需权限）' },
                        { command: '/svc wifi enable', desc: '开启 Wi-Fi（修改）' },
                        { command: '/svc wifi disable', desc: '关闭 Wi-Fi（修改）' },
                        { command: '/svc data enable', desc: '开启移动数据（修改）' },
                        { command: '/svc data disable', desc: '关闭移动数据（修改）' },
                        { command: '/setprop debug.layout true', desc: '开启布局边界（修改，需支持）' },
                        { command: '/setprop debug.layout false', desc: '关闭布局边界（修改，需支持）' },
                        { command: '/appops set com.tencent.mm SYSTEM_ALERT_WINDOW allow', desc: '授予悬浮窗权限（修改）' },
                        { command: '/broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Download/shot.png', desc: '通知系统刷新媒体库（修改）' },
                    ];
                    const isAdbCommandMode = Vue.computed(() => {
                        const text = (chatInput.value || '').trim();
                        return text.startsWith('/');
                    });
                    const filteredAdbQuickCommands = Vue.computed(() => {
                        const keyword = (chatInput.value || '').trim().toLowerCase();
                        if (!keyword.startsWith('/')) {
                            return [];
                        }
                        if (keyword.length <= 1) {
                            return adbQuickCommands;
                        }
                        const candidates = adbQuickCommands.filter(item =>
                            item.command.toLowerCase().includes(keyword) ||
                            item.desc.toLowerCase().includes(keyword.slice(1))
                        );
                        return candidates;
                    });
                    const activeAdbSuggestionCommand = Vue.computed(() => {
                        const list = filteredAdbQuickCommands.value || [];
                        if (!list.length) return '';
                        if (adbSuggestionIndex.value < 0 || adbSuggestionIndex.value >= list.length) return '';
                        return list[adbSuggestionIndex.value].command;
                    });
                    function normalizeMentionToken(token) {
                        return (token || '')
                            .trim()
                            .replace(/[，,。;；:：!?！？]+$/g, '');
                    }
                    function compactMentionToken(token) {
                        return (token || '')
                            .toLowerCase()
                            .replace(/[\s_\-]+/g, '');
                    }
                    function formatDeviceMentionToken(device) {
                        const name = (device?.name || '').trim();
                        if (name) {
                            const compactName = name.replace(/\s+/g, '').replace(/[^\w.\-]/g, '');
                            if (compactName) return compactName;
                        }
                        return (device?.id || '').replace(/[^\w.\-:]/g, '');
                    }
                    function getMentionContext(input, cursorPos) {
                        const text = input || '';
                        const safeCursor = Math.max(0, Math.min(typeof cursorPos === 'number' ? cursorPos : text.length, text.length));
                        const head = text.slice(0, safeCursor);
                        const match = head.match(/(^|[\s，,。;；:：])@([^\s@]*)$/);
                        if (!match) {
                            return { active: false, query: '', start: -1, end: -1 };
                        }
                        const query = match[2] || '';
                        const start = safeCursor - query.length - 1;
                        return { active: true, query, start, end: safeCursor };
                    }
                    const mentionContext = Vue.computed(() => getMentionContext(chatInput.value || '', chatCursorPos.value));
                    const isDeviceMentionMode = Vue.computed(() =>
                        !isAdbCommandMode.value && mentionContext.value.active
                    );
                    const filteredDeviceMentionSuggestions = Vue.computed(() => {
                        if (!isDeviceMentionMode.value) return [];
                        const queryRaw = normalizeMentionToken(mentionContext.value.query || '');
                        const queryLower = queryRaw.toLowerCase();
                        const queryCompact = compactMentionToken(queryRaw);
                        const items = (devices.value || []).map(device => {
                            const name = (device.name || '').trim();
                            return {
                                id: device.id,
                                name: name,
                                mentionToken: formatDeviceMentionToken(device),
                                idLower: (device.id || '').toLowerCase(),
                                nameLower: name.toLowerCase(),
                                idCompact: compactMentionToken(device.id || ''),
                                nameCompact: compactMentionToken(name),
                            };
                        });
                        if (!queryRaw) {
                            return items;
                        }
                        const score = (item) => {
                            if (item.idLower === queryLower || item.nameLower === queryLower || item.nameCompact === queryCompact) return 0;
                            if (item.idLower.startsWith(queryLower) || item.nameLower.startsWith(queryLower) || item.nameCompact.startsWith(queryCompact)) return 1;
                            if (item.idCompact.startsWith(queryCompact)) return 2;
                            if (item.idLower.includes(queryLower) || item.nameLower.includes(queryLower) || item.nameCompact.includes(queryCompact)) return 3;
                            if (item.idCompact.includes(queryCompact)) return 4;
                            return -1;
                        };
                        return items
                            .map(item => ({ item, score: score(item) }))
                            .filter(entry => entry.score >= 0)
                            .sort((a, b) => a.score - b.score)
                            .map(entry => ({
                                id: entry.item.id,
                                name: entry.item.name,
                                mentionToken: entry.item.mentionToken,
                            }));
                    });
                    const activeDeviceMentionSuggestionId = Vue.computed(() => {
                        const list = filteredDeviceMentionSuggestions.value || [];
                        if (!list.length) return '';
                        if (deviceMentionSuggestionIndex.value < 0 || deviceMentionSuggestionIndex.value >= list.length) return '';
                        return list[deviceMentionSuggestionIndex.value].id;
                    });
                    const hasAtMention = Vue.computed(() => /(^|[\s，,。;；:：])@[^\s@]+/.test((chatInput.value || '').trim()));
                    const canSendChatMessage = Vue.computed(() => {
                        const text = (chatInput.value || '').trim();
                        if (!text || chatRunning.value) return false;
                        if (text.startsWith('/')) {
                            return !!chatDeviceId.value;
                        }
                        return true; // 普通对话不需要连接或选择设备。
                    });

                    // Tap preview modal state (debug mode)
                    const showTapPreview = ref(false);
                    const tapPreviewData = ref({ requestId: '', x: 0, y: 0, width: 0, height: 0, screenshot: '' });
                    const tapPreviewAdjustedX = ref(0);
                    const tapPreviewAdjustedY = ref(0);

                    // Dark Mode Functions
                    function applyTheme(theme) {
                        if (theme === 'dark') {
                            document.documentElement.setAttribute('data-theme', 'dark');
                        } else {
                            document.documentElement.removeAttribute('data-theme');
                        }
                    }

                    function toggleDarkMode() {
                        darkMode.value = !darkMode.value;
                        const theme = darkMode.value ? 'dark' : 'light';
                        applyTheme(theme);
                        localStorage.setItem('theme', theme);
                    }

                    // ── Cloudflare Tunnel Functions ──
                    async function checkTunnelStatus() {
                        try {
                            const data = await apiCall('/api/tunnel/status');
                            tunnelStatus.value = data.status;
                            tunnelUrl.value = data.url || '';
                            tunnelError.value = data.error || '';
                            if (!data.installed && tunnelStatus.value === 'stopped') {
                                tunnelError.value = '';
                            }
                        } catch (e) {
                            console.warn('Failed to check tunnel status:', e);
                        }
                    }

                    async function toggleTunnel() {
                        if (tunnelStatus.value === 'starting') return; // Prevent double-click

                        if (tunnelStatus.value === 'running') {
                            // Stop tunnel
                            tunnelStatus.value = 'stopping';
                            try {
                                await apiCall('/api/tunnel/stop', { method: 'POST' });
                                tunnelStatus.value = 'stopped';
                                tunnelUrl.value = '';
                                tunnelError.value = '';
                                showToast('公网隧道已关闭', 'info');
                            } catch (e) {
                                tunnelError.value = '关闭隧道失败: ' + e.message;
                                tunnelStatus.value = 'error';
                            }
                        } else {
                            // Start tunnel
                            tunnelStatus.value = 'starting';
                            tunnelError.value = '';
                            try {
                                const data = await apiCall('/api/tunnel/start', { method: 'POST' });
                                if (data.success) {
                                    tunnelStatus.value = 'running';
                                    tunnelUrl.value = data.url;
                                    tunnelError.value = '';
                                    showToast('公网隧道已开启', 'success');
                                } else {
                                    tunnelStatus.value = 'error';
                                    tunnelError.value = data.error || '启动失败';
                                    setTimeout(() => { tunnelStatus.value = 'stopped'; }, 3000);
                                }
                            } catch (e) {
                                tunnelStatus.value = 'error';
                                tunnelError.value = '启动失败: ' + e.message;
                                setTimeout(() => { tunnelStatus.value = 'stopped'; }, 3000);
                            }
                        }
                    }

                    async function copyTunnelUrl() {
                        if (!tunnelUrl.value) return;
                        const copied = await copyTextToClipboard(tunnelUrl.value);
                        if (copied) {
                            showToast('隧道 URL 已复制', 'success');
                        } else {
                            showToast('复制失败，请手动复制', 'error');
                        }
                    }

                    async function copyTextToClipboard(text) {
                        if (navigator.clipboard && window.isSecureContext) {
                            try {
                                await navigator.clipboard.writeText(text);
                                return true;
                            } catch (e) {
                                console.warn('Clipboard API copy failed, fallback to execCommand:', e);
                            }
                        }
                        let ta = null;
                        try {
                            ta = document.createElement('textarea');
                            ta.value = text;
                            ta.setAttribute('readonly', '');
                            ta.style.position = 'fixed';
                            ta.style.top = '-9999px';
                            ta.style.left = '-9999px';
                            ta.style.opacity = '0';
                            document.body.appendChild(ta);
                            ta.focus();
                            ta.select();
                            return !!document.execCommand('copy');
                        } catch (e) {
                            console.warn('execCommand copy failed:', e);
                            return false;
                        } finally {
                            if (ta && ta.parentNode) {
                                ta.parentNode.removeChild(ta);
                            }
                        }
                    }

                    // Translations Dictionary
                    const translations = {
                        zh: {
                            appTitle: '鱼塘管理器', appSubtitle: 'AI 手机自动化专家',
                            navChat: '对话', navDevices: '设备', navMonitor: '远程监控', navTasks: '任务执行', navScheduler: '定时任务',
                            navModels: '模型配置', navFiles: '文件管理', navRules: '规则配置', navSettings: '设置', navDatabase: '高级',
                            monitorTitle: '远程监控', monitorDesc: '通过 ADB 在安卓设备上启动摄像头，将手机作为远程监控使用。启动后点击「打开实时预览」即可在网页查看画面。',
                            monitorDevice: '选择设备', monitorStartCamera: '启动摄像头', monitorStarting: '启动中...', monitorOpenPreview: '打开实时预览',
                            monitorHint: '提示：需保持设备与电脑 ADB 连接；部分机型需在系统设置中允许「相机」权限。',
                            monitorIpCamTitle: 'IP 摄像头流（推荐 IP Webcam）', monitorIpCamDesc: '在手机上安装免费应用「IP Webcam」（Google Play 搜索），在 App 内点击「Start server」后，把显示的地址填到下面（如 http://192.168.1.100:8080/videofeed），即可直接看相机画面。',
                            monitorIpCamUrl: '流地址', monitorIpCamUrlPlaceholder: 'http://手机IP:8080/videofeed',
                            monitorIpCamSuggest: '根据设备填地址', monitorIpCamLaunch: '打开 IP Webcam', monitorIpCamLaunching: '打开中...',
                            monitorIpCamLive: '实时画面', monitorIpCamError: '无法加载画面，请确认手机已打开 IP Webcam 并点击 Start server，且与电脑在同一局域网。',
                            monitorIpCamHint: '推荐应用：IP Webcam（免费，支持 MJPEG）。若设备已无线 ADB 连接，可点「根据设备填地址」自动填入手机 IP。',
                            navGrid: '四宫格监控', gridTitle: 'RTSP 四宫格', gridDesc: '服务器拉取 RTSP 流并转成 MJPEG，通过本页同源输出；支持 Cloudflare 隧道外网观看。',
                            gridConfig: '配置流地址', gridName: '名称', gridCamera: '摄像头', gridNoUrl: '未配置 RTSP 地址', gridStreamError: '拉流失败（检查 ffmpeg 与地址）', gridTunnelHint: '通过 Cloudflare 隧道访问时，画面由本服务器拉流后转发，无需设备直连。需在运行本服务的机器上安装 ffmpeg。',
                            gridRecordStart: '开始录制', gridRecordStop: '停止录制', gridRecording: '录制中…',
                            dbTitle: '数据库管理', dbSelectTable: '选择表', dbSearch: '搜索记录...', dbRefresh: '刷新',
                            dbAddRow: '添加记录', dbEditRow: '编辑记录', dbDeleteRow: '删除记录', dbNoTable: '请选择一个数据表',
                            dbNoData: '此表暂无数据', dbDeleteConfirm: '确定要删除这条记录吗？此操作不可撤销。',
                            dbRows: '条记录', dbSave: '保存', dbCancel: '取消', dbConfirmDelete: '确认删除',
                            statusConnected: '已连接', statusDisconnected: '未连接',
                            controlThemeLight: '明亮', controlThemeDark: '暗黑', controlLanguage: '中文',
                            chatHistory: '会话历史', chatNewSession: '新建', chatNoSessions: '暂无会话记录',
                            chatDeviceLabel: '设备:', chatSelectDevice: '选择设备', chatConnected: '已连接',
                            chatSelectDeviceFirst: '可直接聊天', chatComplexTask: '复杂任务',
                            chatAutoEmail: '自动发送邮件', chatDebugMode: '调试模式', chatTimeout: '超时',
                            chatInputPlaceholder: '聊一聊、商讨计划，或告诉我需要操作手机做什么…', chatWelcome: '你好！可以先聊天、讨论方案，需要操作手机时再告诉我。',
                            chatExample: '例如：先帮我制定方案；确认后再说“按这个方案执行”。', chatExecuting: '正在执行任务...',
                            chatTaskList: '任务清单', chatExecutionLog: '执行日志', chatCompleted: '完成',
                            chatFailed: '失败', chatClickForDetails: '点击查看详情和截图 →',
                            devicesWireless: '无线连接', devicesWirelessPairing: '无线配对 (首次连接)',
                            devicesPairAddress: '配对地址 (如: 192.168.1.100:37000)', devicesPairCode: '6位配对码',
                            devicesPairButton: '配对', devicesPairing: '配对中...', devicesTcpConnect: 'TCP 连接 (已配对设备)',
                            devicesConnectAddress: '连接地址 (如: 192.168.1.100:5555)', devicesConnectButton: '连接',
                            devicesConnecting: '连接中...', devicesConnectionLogs: '连接日志:', devicesConnectedDevices: '已连接设备',
                            devicesRefresh: '刷新', devicesApkInstall: 'APK 安装', devicesSelectDevice: '选择设备',
                            devicesPleaseSelect: '请选择设备', devicesApkFile: 'APK 文件', devicesInstallButton: '安装',
                            devicesInstalling: '安装中...', devicesSelected: '已选择:', devicesNoDevices: '未发现设备',
                            devicesNoDevicesHint: '通过USB连接设备或使用上方无线配对，然后点击刷新', devicesLoading: '加载设备中...',
                            devicesUnlock: '解锁', devicesLock: '锁定', devicesDisconnect: '断开', devicesHidePin: '隐藏PIN', devicesShowPin: '显示PIN',
                            time1Min: '1分钟', time2Min: '2分钟', time3Min: '3分钟', time5Min: '5分钟', time10Min: '10分钟',
                            tasksSelectDevices: '选择设备', tasksSelectAll: '全选', tasksDeselectAll: '取消全选',
                            tasksNoDevices: '暂无已连接设备，请先连接设备', tasksOnline: '在线', tasksOffline: '离线',
                            tasksTask: '任务', tasksInputPlaceholder: '输入任务指令... (例如：打开微信并发送消息给...)',
                            tasksRun: '执行任务', tasksStop: '停止', tasksRunning: '执行中...', tasksScreenshot: '当前截图', tasksParallel: '并行执行',
                            tasksNoScreenshot: '暂无截图', tasksExecutionLog: '执行日志', tasksClearLog: '清空',
                            tasksNoLogs: '暂无日志', tasksRunLog: '执行任务日志', tasksScheduledLog: '定时任务日志', tasksProgress: '进度', tasksCurrentScreenshot: '当前截图',
                            schedulerTitle: '定时任务列表', schedulerNewTask: '新建任务', schedulerAddTask: '添加任务', schedulerNoTasks: '暂无定时任务',
                            schedulerNoTasksHint: '点击"新建任务"创建定时任务', schedulerTableName: '任务名称', schedulerTableSchedule: '计划',
                            schedulerTableNextRun: '下次执行', schedulerTableStatus: '状态', schedulerTableActions: '操作',
                            schedulerStatusEnabled: '已启用', schedulerStatusDisabled: '已禁用', schedulerRunNow: '立即执行',
                            schedulerCreateTask: '创建定时任务', schedulerEditTask: '编辑任务', schedulerFormName: '任务名称',
                            schedulerFormNamePlaceholder: '我的定时任务', schedulerFormContent: '任务内容', schedulerFormContentPlaceholder: '输入任务指令...',
                            schedulerFormType: '任务类型', schedulerTypeOnce: '单次', schedulerTypeInterval: '间隔', schedulerTypeDaily: '每天',
                            schedulerTypeWeekly: '每周', schedulerTypeMonthly: '每月', schedulerFormRunAt: '执行时间',
                            schedulerFormIntervalMinutes: '间隔时间（分钟）', schedulerFormDailyTime: '每天时间', schedulerFormWeeklyDays: '每周哪几天',
                            schedulerFormTime: '时间', schedulerFormMonthlyDay: '每月第几天', schedulerFormTargetDevices: '目标设备（留空表示所有设备）',
                            schedulerFormEnableTask: '立即启用任务', schedulerLogsTitle: '执行日志', schedulerLogsClearAll: '清空所有',
                            schedulerLogsRefresh: '刷新日志', schedulerLogsNoLogs: '暂无执行日志', schedulerLogsStatus: '状态',
                            schedulerLogsTaskName: '任务名称', schedulerLogsExecutionTime: '执行时间', schedulerLogsResult: '结果',
                            schedulerLogsDetails: '详情', schedulerLogDetailsTitle: '执行日志详情', schedulerLogDetailsTask: '任务',
                            schedulerLogDetailsTime: '时间', schedulerLogDetailsStatus: '状态', schedulerLogDetailsSuccess: '成功',
                            schedulerLogDetailsFailed: '失败', schedulerLogDetailsNoDetails: '无详细日志',
                            daySun: '日', dayMon: '一', dayTue: '二', dayWed: '三', dayThu: '四', dayFri: '五', daySat: '六',
                            modelsTitle: '模型配置', modelsPresets: '预设配置', modelsCustom: '自定义配置',
                            modelsProvider: '模型提供商', modelsModel: '模型名称', modelsApiKey: 'API密钥',
                            modelsBaseUrl: 'Base URL', modelsSave: '保存配置', modelsTest: '测试连接',
                            filesTitle: '文件管理', filesUpload: '上传文件', filesDownload: '下载', filesDelete: '删除',
                            filesName: '文件名', filesSize: '大小', filesTime: '时间', filesNoFiles: '暂无文件',
                            rulesTitle: '规则配置', rulesPrompt: '提示词规则', rulesAction: '动作规则',
                            rulesApp: '应用规则', rulesTiming: '时机规则', rulesAdd: '添加', rulesEdit: '编辑',
                            settingsTitle: '设置', settingsEmail: '邮件设置', settingsScreenshot: '截图设置',
                            settingsTelegram: 'Telegram设置', settingsSave: '保存', settingsTest: '测试',
                            commonSave: '保存', commonCancel: '取消', commonConfirm: '确认', commonClose: '关闭',
                            commonEdit: '编辑', commonDelete: '删除', commonAdd: '添加', commonRefresh: '刷新', commonCreate: '创建',
                            commonSaving: '保存中...', commonTesting: '测试中...', commonActivate: '激活', commonTest: '测试',
                            modelsName: '名称', modelsProtocol: '协议', modelsStatus: '状态', modelsActions: '操作',
                            modelsCurrentActive: '当前激活', modelsActivated: '已激活', modelsNotActivated: '未激活',
                            modelsActivateTitle: '激活此模型', modelsTestTitle: '测试连接', modelsEditTitle: '编辑',
                            modelsDeleteTitle: '删除', modelsNewModel: '新增模型', modelsQuickTemplates: '快速添加预设模板',
                            modelsOpenAI: 'OpenAI 协议', modelsOllama: 'Ollama 协议', modelsAnthropic: 'Anthropic 协议', modelsGemini: 'Gemini 协议',
                            modelsCreateModel: '创建模型', modelsEditModel: '编辑模型', modelsFormName: '服务名称',
                            modelsFormProtocol: '协议类型', modelsFormDescription: '描述',
                            filesSelectDevice: '选择设备', filesPleaseSelect: '请选择设备', filesCurrentPath: '当前路径',
                            filesGoButton: 'GO', filesSDCard: 'SD卡', filesPhotos: '相册', filesDownloads: '下载',
                            filesDocuments: '文件', filesUpToParent: '上级', filesUploadTo: '上传文件到当前目录',
                            filesSelectFile: '选择文件', filesNoFileSelected: '未选择任何文件', filesUploadButton: '上传',
                            filesNoFilesHint: '请先选择设备',
                            rulesAppName: '应用名称', rulesPackageName: '包名', rulesDescription: '描述',
                            rulesAddApp: '添加应用映射', rulesEditApp: '编辑应用映射', rulesAppNameLabel: '应用名称',
                            rulesPackageLabel: '包名', rulesDescLabel: '描述（可选）',
                            settingsSMTP: 'SMTP 服务器', settingsPort: '端口', settingsSender: '发送邮箱',
                            settingsPassword: '密码', settingsReceiver: '接收邮箱', settingsSaveSettings: '保存设置',
                            settingsSendTest: '发送测试邮件', settingsScreenshotTitle: '截图设置',
                            settingsScreenshotInterval: '截图间隔（秒）', settingsTelegramTitle: 'Telegram 设置',
                            settingsTelegramToken: 'Bot Token', settingsTelegramChatId: 'Chat ID',
                        },
                        en: {
                            appTitle: 'AutoGLM Manager', appSubtitle: 'AI Phone Automation Expert',
                            navChat: 'Chat', navDevices: 'Devices', navMonitor: 'Remote Monitor', navTasks: 'Tasks', navScheduler: 'Scheduler',
                            navModels: 'Models', navFiles: 'Files', navRules: 'Rules', navSettings: 'Settings', navDatabase: 'Advanced',
                            monitorTitle: 'Remote Monitor', monitorDesc: 'Launch the device camera via ADB to use your Android phone as a remote monitor. After starting, click "Open Live Preview" to view the feed in the browser.',
                            monitorDevice: 'Select device', monitorStartCamera: 'Start camera', monitorStarting: 'Starting...', monitorOpenPreview: 'Open live preview',
                            monitorHint: 'Keep the device connected via ADB. Some devices may require camera permission in system settings.',
                            monitorIpCamTitle: 'IP Camera Stream (e.g. IP Webcam)', monitorIpCamDesc: 'Install a free app like "IP Webcam" (Google Play), tap "Start server" in the app, then enter the URL shown (e.g. http://192.168.1.100:8080/videofeed) below to view the camera feed.',
                            monitorIpCamUrl: 'Stream URL', monitorIpCamUrlPlaceholder: 'http://phone-ip:8080/videofeed',
                            monitorIpCamSuggest: 'Fill from device', monitorIpCamLaunch: 'Open IP Webcam', monitorIpCamLaunching: 'Opening...',
                            monitorIpCamLive: 'Live view', monitorIpCamError: 'Cannot load stream. Ensure IP Webcam is running (Start server) and phone is on the same network.',
                            monitorIpCamHint: 'Recommended: IP Webcam (free, MJPEG). If device is on wireless ADB, use "Fill from device" to auto-fill the phone IP.',
                            navGrid: 'Grid Monitor', gridTitle: 'RTSP 4-Grid', gridDesc: 'Server pulls RTSP and serves as MJPEG (same-origin). Works through Cloudflare tunnel.',
                            gridConfig: 'Config streams', gridName: 'Name', gridCamera: 'Camera', gridNoUrl: 'No RTSP URL', gridStreamError: 'Stream failed (check ffmpeg & URL)', gridTunnelHint: 'When using Cloudflare tunnel, streams are pulled by the server and forwarded; no direct device access needed. Install ffmpeg on the server.',
                            gridRecordStart: 'Start record', gridRecordStop: 'Stop', gridRecording: 'Recording…',
                            dbTitle: 'Database Management', dbSelectTable: 'Select Table', dbSearch: 'Search records...', dbRefresh: 'Refresh',
                            dbAddRow: 'Add Record', dbEditRow: 'Edit Record', dbDeleteRow: 'Delete Record', dbNoTable: 'Please select a table',
                            dbNoData: 'No data in this table', dbDeleteConfirm: 'Are you sure you want to delete this record? This cannot be undone.',
                            dbRows: 'rows', dbSave: 'Save', dbCancel: 'Cancel', dbConfirmDelete: 'Confirm Delete',
                            statusConnected: 'Connected', statusDisconnected: 'Disconnected',
                            controlThemeLight: 'Light', controlThemeDark: 'Dark', controlLanguage: 'En',
                            chatHistory: 'Chat History', chatNewSession: 'New', chatNoSessions: 'No chat sessions',
                            chatDeviceLabel: 'Device:', chatSelectDevice: 'Select Device', chatConnected: 'Connected',
                            chatSelectDeviceFirst: 'Chat without a device', chatComplexTask: 'Complex Task',
                            chatAutoEmail: 'Auto Email', chatDebugMode: 'Debug Mode', chatTimeout: 'Timeout',
                            chatInputPlaceholder: 'Chat, plan together, or ask me to operate your phone…', chatWelcome: 'Hello! We can chat and discuss a plan before using your phone.',
                            chatExample: 'For example: Help me make a plan, then say “Execute this plan” when ready.', chatExecuting: 'Executing task...',
                            chatTaskList: 'Task List', chatExecutionLog: 'Execution Log', chatCompleted: 'Completed',
                            chatFailed: 'Failed', chatClickForDetails: 'Click for details and screenshots →',
                            devicesWireless: 'Wireless Connection', devicesWirelessPairing: 'Wireless Pairing (First Time)',
                            devicesPairAddress: 'Pairing Address (e.g., 192.168.1.100:37000)', devicesPairCode: '6-digit Pairing Code',
                            devicesPairButton: 'Pair', devicesPairing: 'Pairing...', devicesTcpConnect: 'TCP Connection (Paired Devices)',
                            devicesConnectAddress: 'Connect Address (e.g., 192.168.1.100:5555)', devicesConnectButton: 'Connect',
                            devicesConnecting: 'Connecting...', devicesConnectionLogs: 'Connection Logs:', devicesConnectedDevices: 'Connected Devices',
                            devicesRefresh: 'Refresh', devicesApkInstall: 'APK Installation', devicesSelectDevice: 'Select Device',
                            devicesPleaseSelect: 'Please select a device', devicesApkFile: 'APK File', devicesInstallButton: 'Install',
                            devicesInstalling: 'Installing...', devicesSelected: 'Selected:', devicesNoDevices: 'No devices found',
                            devicesNoDevicesHint: 'Connect a device via USB or use wireless pairing above, then refresh', devicesLoading: 'Loading devices...',
                            devicesUnlock: 'Unlock', devicesLock: 'Lock', devicesDisconnect: 'Disconnect', devicesHidePin: 'Hide PIN', devicesShowPin: 'Show PIN',
                            time1Min: '1 min', time2Min: '2 mins', time3Min: '3 mins', time5Min: '5 mins', time10Min: '10 mins',
                            tasksSelectDevices: 'Select Devices', tasksSelectAll: 'Select All', tasksDeselectAll: 'Deselect All',
                            tasksNoDevices: 'No connected devices, please connect first', tasksOnline: 'Online', tasksOffline: 'Offline',
                            tasksTask: 'Task', tasksInputPlaceholder: 'Enter task instructions... (e.g., Open WeChat and send a message to...)',
                            tasksRun: 'Run Task', tasksStop: 'Stop', tasksRunning: 'Running...', tasksScreenshot: 'Current Screenshot', tasksParallel: 'Parallel',
                            tasksNoScreenshot: 'No screenshot', tasksExecutionLog: 'Execution Log', tasksClearLog: 'Clear',
                            tasksNoLogs: 'No logs', tasksRunLog: 'Run Task Log', tasksScheduledLog: 'Scheduled Task Log', tasksProgress: 'Progress', tasksCurrentScreenshot: 'Current Screenshot',
                            schedulerTitle: 'Scheduled Tasks List', schedulerNewTask: 'New Task', schedulerAddTask: 'Add Task', schedulerNoTasks: 'No scheduled tasks',
                            schedulerNoTasksHint: 'Click "New Task" to create a scheduled task', schedulerTableName: 'Task Name', schedulerTableSchedule: 'Schedule',
                            schedulerTableNextRun: 'Next Run', schedulerTableStatus: 'Status', schedulerTableActions: 'Actions',
                            schedulerStatusEnabled: 'Enabled', schedulerStatusDisabled: 'Disabled', schedulerRunNow: 'Run Now',
                            schedulerCreateTask: 'Create Scheduled Task', schedulerEditTask: 'Edit Task', schedulerFormName: 'Task Name',
                            schedulerFormNamePlaceholder: 'My Scheduled Task', schedulerFormContent: 'Task Content', schedulerFormContentPlaceholder: 'Enter task instruction...',
                            schedulerFormType: 'Task Type', schedulerTypeOnce: 'Once', schedulerTypeInterval: 'Interval', schedulerTypeDaily: 'Daily',
                            schedulerTypeWeekly: 'Weekly', schedulerTypeMonthly: 'Monthly', schedulerFormRunAt: 'Run At',
                            schedulerFormIntervalMinutes: 'Interval (minutes)', schedulerFormDailyTime: 'Daily Time', schedulerFormWeeklyDays: 'Days of Week',
                            schedulerFormTime: 'Time', schedulerFormMonthlyDay: 'Day of Month', schedulerFormTargetDevices: 'Target Devices (leave empty for all)',
                            schedulerFormEnableTask: 'Enable task immediately', schedulerLogsTitle: 'Execution Log', schedulerLogsClearAll: 'Clear All',
                            schedulerLogsRefresh: 'Refresh Logs', schedulerLogsNoLogs: 'No execution logs', schedulerLogsStatus: 'Status',
                            schedulerLogsTaskName: 'Task Name', schedulerLogsExecutionTime: 'Execution Time', schedulerLogsResult: 'Result',
                            schedulerLogsDetails: 'Details', schedulerLogDetailsTitle: 'Execution Log Details', schedulerLogDetailsTask: 'Task',
                            schedulerLogDetailsTime: 'Time', schedulerLogDetailsStatus: 'Status', schedulerLogDetailsSuccess: 'Success',
                            schedulerLogDetailsFailed: 'Failed', schedulerLogDetailsNoDetails: 'No detailed logs',
                            daySun: 'Sun', dayMon: 'Mon', dayTue: 'Tue', dayWed: 'Wed', dayThu: 'Thu', dayFri: 'Fri', daySat: 'Sat',
                            modelsTitle: 'Model Configuration', modelsPresets: 'Preset Configs', modelsCustom: 'Custom Config',
                            modelsProvider: 'Provider', modelsModel: 'Model Name', modelsApiKey: 'API Key',
                            modelsBaseUrl: 'Base URL', modelsSave: 'Save Config', modelsTest: 'Test Connection',
                            filesTitle: 'File Management', filesUpload: 'Upload File', filesDownload: 'Download', filesDelete: 'Delete',
                            filesName: 'File Name', filesSize: 'Size', filesTime: 'Time', filesNoFiles: 'No files',
                            rulesTitle: 'Rules Configuration', rulesPrompt: 'Prompt Rules', rulesAction: 'Action Rules',
                            rulesApp: 'App Rules', rulesTiming: 'Timing Rules', rulesAdd: 'Add', rulesEdit: 'Edit',
                            settingsTitle: 'Settings', settingsEmail: 'Email Settings', settingsScreenshot: 'Screenshot Settings',
                            settingsTelegram: 'Telegram Settings', settingsSave: 'Save', settingsTest: 'Test',
                            commonSave: 'Save', commonCancel: 'Cancel', commonConfirm: 'Confirm', commonClose: 'Close',
                            commonEdit: 'Edit', commonDelete: 'Delete', commonAdd: 'Add', commonRefresh: 'Refresh', commonCreate: 'Create',
                            commonSaving: 'Saving...', commonTesting: 'Testing...', commonActivate: 'Activate', commonTest: 'Test',
                            modelsName: 'Name', modelsProtocol: 'Protocol', modelsStatus: 'Status', modelsActions: 'Actions',
                            modelsCurrentActive: 'Currently Active', modelsActivated: 'Activated', modelsNotActivated: 'Not Activated',
                            modelsActivateTitle: 'Activate this model', modelsTestTitle: 'Test connection', modelsEditTitle: 'Edit',
                            modelsDeleteTitle: 'Delete', modelsNewModel: 'New Model', modelsQuickTemplates: 'Quick Templates',
                            modelsOpenAI: 'OpenAI Protocol', modelsOllama: 'Ollama Protocol', modelsAnthropic: 'Anthropic Protocol', modelsGemini: 'Gemini Protocol',
                            modelsCreateModel: 'Create Model', modelsEditModel: 'Edit Model', modelsFormName: 'Service Name',
                            modelsFormProtocol: 'Protocol Type', modelsFormDescription: 'Description',
                            filesSelectDevice: 'Select Device', filesPleaseSelect: 'Please select a device', filesCurrentPath: 'Current Path',
                            filesGoButton: 'GO', filesSDCard: 'SD Card', filesPhotos: 'Photos', filesDownloads: 'Downloads',
                            filesDocuments: 'Documents', filesUpToParent: 'Parent', filesUploadTo: 'Upload file to current directory',
                            filesSelectFile: 'Select file', filesNoFileSelected: 'No file selected', filesUploadButton: 'Upload',
                            filesNoFilesHint: 'Please select a device first',
                            rulesAppName: 'App Name', rulesPackageName: 'Package Name', rulesDescription: 'Description',
                            rulesAddApp: 'Add App Mapping', rulesEditApp: 'Edit App Mapping', rulesAppNameLabel: 'App Name',
                            rulesPackageLabel: 'Package Name', rulesDescLabel: 'Description (Optional)',
                            settingsSMTP: 'SMTP Server', settingsPort: 'Port', settingsSender: 'Sender Email',
                            settingsPassword: 'Password', settingsReceiver: 'Receiver Email', settingsSaveSettings: 'Save Settings',
                            settingsSendTest: 'Send Test Email', settingsScreenshotTitle: 'Screenshot Settings',
                            settingsScreenshotInterval: 'Screenshot Interval (seconds)', settingsTelegramTitle: 'Telegram Settings',
                            settingsTelegramToken: 'Bot Token', settingsTelegramChatId: 'Chat ID',
                        }
                    };

                    // Translation helper - computed property
                    const t = Vue.computed(() => {
                        return (key) => translations[currentLanguage.value]?.[key] || key;
                    });

                    // Language Toggle Function
                    function toggleLanguage() {
                        currentLanguage.value = currentLanguage.value === 'zh' ? 'en' : 'zh';
                        localStorage.setItem('language', currentLanguage.value);
                    }

                    // Chat sessions state
                    const chatSessions = ref([]);
                    const currentSessionId = ref('');
                    const chatContext = ref(null);
                    const contextMonitor = createContextMonitor({apiCall, sessionId:currentSessionId,
                        messages:chatMessages, state:chatContext});
                    watch(currentSessionId, () => { contextMonitor.stop(); chatContext.value=null; void contextMonitor.refresh(); });
                    const sessionSearchQuery = ref('');
                    const SESSIONS_STORAGE_KEY = 'autoglm_chat_sessions';

                    // Filtered sessions (search)
                    const filteredSessions = Vue.computed(() => {
                        const q = sessionSearchQuery.value.trim().toLowerCase();
                        if (!q) return chatSessions.value;
                        return chatSessions.value.filter(s =>
                            (s.title || '').toLowerCase().includes(q) ||
                            (s.messages || []).some(m => (m.content || '').toLowerCase().includes(q))
                        );
                    });

                    // Task detail modal state
                    const showTaskDetail = ref(false);
                    const taskDetailData = ref({});

                    function getPreviewViewportBounds(width = previewWidth.value, aspect = previewAspect.value) {
                        const safeAspect = Math.max(0.2, aspect || (16 / 9));
                        const pw = Math.max(1, Math.round(width));
                        const ph = Math.max(1, Math.round(pw * safeAspect));
                        const toolbarReserveX = getPreviewToolbarWidthReserve();
                        const toolbarReserveY = getPreviewToolbarHeightReserve();
                        const minX = PREVIEW_SAFE_MARGIN;
                        const minY = PREVIEW_SAFE_MARGIN;
                        const maxX = Math.max(minX, window.innerWidth - pw - toolbarReserveX - PREVIEW_SAFE_MARGIN);
                        const maxY = Math.max(minY, window.innerHeight - ph - toolbarReserveY - PREVIEW_SAFE_MARGIN);
                        return { minX, maxX, minY, maxY };
                    }

                    function getPreviewWidthRange(left, top) {
                        const minBase = 220;
                        const safeAspect = Math.max(0.2, previewAspect.value || (16 / 9));
                        const isLandscapePreview = safeAspect < 1;
                        const maxBase = isLandscapePreview
                            ? Math.max(920, Math.floor(window.innerWidth * 0.9))
                            : 760;
                        const toolbarReserveX = getPreviewToolbarWidthReserve();
                        const toolbarReserveY = getPreviewToolbarHeightReserve();
                        const maxByWidth = Math.floor(window.innerWidth - PREVIEW_SAFE_MARGIN - toolbarReserveX - left);
                        const maxByHeight = Math.floor((window.innerHeight - PREVIEW_SAFE_MARGIN - toolbarReserveY - top) / safeAspect);
                        let maxAllowed = Math.min(maxBase, maxByWidth, maxByHeight);
                        if (!Number.isFinite(maxAllowed)) maxAllowed = maxBase;
                        maxAllowed = Math.max(120, maxAllowed);
                        const minAllowed = Math.min(minBase, maxAllowed);
                        return { minAllowed, maxAllowed };
                    }

                    function ensurePreviewInViewport() {
                        const bounds = getPreviewViewportBounds();
                        let nextX = Math.max(bounds.minX, Math.min(bounds.maxX, previewPosition.value.x));
                        let nextY = Math.max(bounds.minY, Math.min(bounds.maxY, previewPosition.value.y));

                        const { maxAllowed } = getPreviewWidthRange(nextX, nextY);
                        if (previewWidth.value > maxAllowed) {
                            previewWidth.value = maxAllowed;
                        }

                        const finalBounds = getPreviewViewportBounds();
                        nextX = Math.max(finalBounds.minX, Math.min(finalBounds.maxX, nextX));
                        nextY = Math.max(finalBounds.minY, Math.min(finalBounds.maxY, nextY));
                        previewPosition.value = { x: nextX, y: nextY };
                    }

                    // Calculate safe position for preview window
                    function updatePreviewPosition() {
                        const bounds = getPreviewViewportBounds();
                        previewPosition.value = {
                            x: bounds.maxX,
                            y: bounds.maxY,
                        };
                    }

                    function getDefaultSchedulerForm() {
                        return {
                            id: '',
                            name: '',
                            task_content: '',
                            enabled: true,
                            schedule_type: 'daily',
                            run_at: '',
                            interval_minutes: 60,
                            daily_time: '09:00',
                            weekly_days: [1],
                            weekly_time: '09:00',
                            monthly_day: 1,
                            monthly_time: '09:00',
                            devices: [], recipe_id:'',recipe_revision:null,recipe_parameters:{},busy_policy:'queue',timezone:'',
                        };
                    }

                    // WebSocket
                    let ws = null;
                    let reconnectTimer = null;

                    function showToast(message, type = 'success') {
                        const id = Date.now();
                        toasts.value.push({ id, message, type });
                        setTimeout(() => {
                            toasts.value = toasts.value.filter(t => t.id !== id);
                        }, 3000);
                    }

                    function upsertSystemAlert({ id, level = 'warning', title = '系统通知', message = '', autoDismiss = 0 }) {
                        if (!id) return;
                        const existing = systemAlerts.value.findIndex(a => a.id === id);
                        const payload = { id, level, title, message };
                        if (existing >= 0) {
                            systemAlerts.value.splice(existing, 1, payload);
                        } else {
                            systemAlerts.value.push(payload);
                        }
                        if (autoDismiss > 0) {
                            setTimeout(() => {
                                systemAlerts.value = systemAlerts.value.filter(a => a.id !== id);
                            }, autoDismiss * 1000);
                        }
                    }

                    function dismissSystemAlert(alertId) {
                        systemAlerts.value = systemAlerts.value.filter(a => a.id !== alertId);
                    }

                    async function checkAuth() {
                        authChecking.value = true;
                        try {
                            const response = await fetch('/api/auth/status', { cache: 'no-store' });
                            const data = await response.json();
                            isAuthenticated.value = Boolean(data.authenticated);
                            currentUsername.value = data.username || '';
                            defaultCredentials.value = Boolean(data.default_credentials);
                            if (isAuthenticated.value) {
                                loginForm.value.username = currentUsername.value;
                            }
                        } catch (error) {
                            isAuthenticated.value = false;
                            loginError.value = '无法连接服务器，请稍后重试';
                        } finally {
                            authChecking.value = false;
                        }
                    }

                    function initializeAuthenticatedApp() {
                        if (authenticatedAppInitialized || !isAuthenticated.value) return;
                        authenticatedAppInitialized = true;
                        connectWebSocket();
                        refreshDevices({silent:true});
                        loadModels();
                        loadDevicePins();
                        initChatSessions();
                        checkTunnelStatus();
                    }

                    async function login() {
                        loginLoading.value = true;
                        loginError.value = '';
                        try {
                            const response = await fetch('/api/auth/login', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify(loginForm.value),
                            });
                            const data = await response.json();
                            if (!response.ok) {
                                throw new Error(data.detail || '登录失败');
                            }
                            isAuthenticated.value = true;
                            currentUsername.value = data.username || loginForm.value.username;
                            defaultCredentials.value = (
                                loginForm.value.username === 'admin'
                                && loginForm.value.password === 'admin'
                            );
                            loginForm.value.password = '';
                            initializeAuthenticatedApp();
                        } catch (error) {
                            loginError.value = error.message || '登录失败';
                        } finally {
                            loginLoading.value = false;
                        }
                    }

                    function clearAuthenticatedConnections() {
                        authenticatedAppInitialized = false;
                        if (reconnectTimer) {
                            clearTimeout(reconnectTimer);
                            reconnectTimer = null;
                        }
                        if (ws) {
                            ws.onclose = null;
                            ws.close();
                            ws = null;
                        }
                        disconnectStream();
                        disconnectAudioStream();
                        showPhonePreview.value = false;
                        wsConnected.value = false;
                    }

                    async function logout() {
                        await pauseActiveRecording().catch(()=>{});
                        automation.stopPlayback();
                        try {
                            await fetch('/api/auth/logout', { method: 'POST' });
                        } finally {
                            clearAuthenticatedConnections();
                            isAuthenticated.value = false;
                            currentUsername.value = '';
                            loginForm.value.password = '';
                            loginError.value = '';
                        }
                    }

                    async function loadCredentials() {
                        try {
                            const data = await apiCall('/api/auth/credentials');
                            credentialsForm.value.username = data.username || currentUsername.value;
                        } catch (error) {
                            console.error('Failed to load login credentials:', error);
                        }
                    }

                    async function saveCredentials() {
                        const form = credentialsForm.value;
                        if (!form.username.trim()) {
                            showToast('登录账号不能为空', 'error');
                            return;
                        }
                        if (form.new_password.length < 4) {
                            showToast('新密码至少需要 4 个字符', 'error');
                            return;
                        }
                        if (form.new_password !== form.confirm_password) {
                            showToast('两次输入的新密码不一致', 'error');
                            return;
                        }

                        credentialsSaving.value = true;
                        try {
                            const data = await apiCall('/api/auth/credentials', {
                                method: 'PUT',
                                body: JSON.stringify({
                                    username: form.username,
                                    current_password: form.current_password,
                                    new_password: form.new_password,
                                }),
                            });
                            currentUsername.value = data.username;
                            defaultCredentials.value = false;
                            loginForm.value.username = data.username;
                            credentialsForm.value.current_password = '';
                            credentialsForm.value.new_password = '';
                            credentialsForm.value.confirm_password = '';
                            showToast('登录账号和密码已更新', 'success');
                        } finally {
                            credentialsSaving.value = false;
                        }
                    }

                    // API calls
                    async function apiCall(url, options = {}) {
                        try {
                            const response = await fetch(url, {
                                ...options,
                                headers: {
                                    'Content-Type': 'application/json',
                                    ...options.headers,
                                },
                            });
                            const data = await response.json();
                            if (!response.ok) {
                                if (response.status === 401) {
                                    clearAuthenticatedConnections();
                                    isAuthenticated.value = false;
                                    loginError.value = '登录已失效，请重新登录';
                                }
                                throw new ApiError(url,options.method||'GET',response.status,data.detail,response.statusText);
                            }
                            return data;
                        } catch (error) {
                            showToast(error.message, 'error');
                            throw error;
                        }
                    }

                    // WebSocket connection
                    function connectWebSocket() {
                        if (!isAuthenticated.value) return;
                        try {
                            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                            const wsUrl = `${protocol}//${window.location.host}/ws`;
                            ws = new WebSocket(wsUrl);

                            ws.onopen = () => {
                                wsConnected.value = true;
                                automation.reconnect();
                                console.log('WebSocket connected');
                            };

                            ws.onclose = () => {
                                wsConnected.value = false;
                                console.log('WebSocket disconnected');
                                if (isAuthenticated.value) {
                                    reconnectTimer = setTimeout(connectWebSocket, 3000);
                                }
                            };

                            ws.onmessage = (event) => {
                                try {
                                    const data = JSON.parse(event.data);
                                    handleWebSocketMessage(data);
                                } catch (e) {
                                    console.error('WebSocket message error:', e);
                                }
                            };

                            ws.onerror = (error) => {
                                console.error('WebSocket error:', error);
                            };
                        } catch (e) {
                            console.error('WebSocket connection error:', e);
                        }
                    }

                    function handleWebSocketMessage(data) {
                        switch (data.type) {
                            case 'init':
                                if (data.task_status) {
                                    const task=data.task_status.task;
                                    if(task && task.task_type==='manual'){
                                        activeRunTaskId.value=task.id;
                                        taskRunning.value=!isTerminal(task.status);
                                        taskProgress.value=task.progress||0;
                                    }
                                }
                                break;
                            case 'task_log':
                                // 1. Run Task Page Logs (taskLogs) - Only for manual tasks
                                if ((!data.task_type || data.task_type === 'manual') && (!activeRunTaskId.value || data.task_id===activeRunTaskId.value)) {
                                    taskLogs.value.push({
                                        time: new Date().toLocaleTimeString(),
                                        message: data.message,
                                    });
                                }

                                // 2. Scheduler Page: Don't add real-time logs here
                                // schedulerLogs is populated from API (summary per execution cycle)
                                // Real-time logs for scheduled tasks are not displayed in scheduler page

                                // 3. Chat Page Logs (chatMessages)
                                if (chatMessages.value.length > 0) {
                                    // 找到匹配taskId的消息，或者最后一条running状态的assistant消息
                                    // 对于复杂任务，也接受有todoList的消息
                                    let targetMsg = null;
                                    for (let i = chatMessages.value.length - 1; i >= 0; i--) {
                                        const msg = chatMessages.value[i];
                                        if (msg.role === 'assistant') {
                                            // 如果消息正在运行，或者是有todoList的复杂任务（正在执行中）
                                            const isRunning = msg.status === 'running';
                                            const isComplexTaskRunning = msg.todoList && msg.todoList.length > 0 &&
                                                msg.todoList.some(t => t.status === 'running' || t.status === 'pending');

                                            if (isRunning || isComplexTaskRunning) {
                                                // 如果有taskId则必须匹配，否则使用最后一条
                                                if (data.task_id && msg.taskId && msg.taskId !== data.task_id) {
                                                    continue;  // taskId不匹配，跳过
                                                }
                                                targetMsg = msg;
                                                break;
                                            }
                                        }
                                    }

                                    if (targetMsg) {
                                        // 使用数组扩展运算符强制触发 Vue 更新 (Reactivity)
                                        const newLogs = targetMsg.logs ? [...targetMsg.logs, data.message] : [data.message];
                                        targetMsg.logs = newLogs;

                                        // 复杂任务模式：将日志也添加到当前执行的子任务
                                        // 不检查子任务状态，因为日志可能在状态变更后才到达
                                        if (targetMsg.todoList && targetMsg.currentTodoIndex !== undefined && targetMsg.currentTodoIndex >= 0) {
                                            const currentTodo = targetMsg.todoList[targetMsg.currentTodoIndex];
                                            if (currentTodo) {
                                                const subNewLogs = currentTodo.logs ? [...currentTodo.logs, data.message] : [data.message];
                                                currentTodo.logs = subNewLogs;
                                            }
                                        }

                                        scrollChatToBottom();
                                    }
                                }
                                break;
                            case 'task_progress':
                                if(data.task_id===activeRunTaskId.value)taskProgress.value = data.progress;
                                break;
                            case 'automation_event': {
                                automation.handleEvent(data);
                                if (data.kind === 'screen' && data.data?.image_id && (!activeRunTaskId.value || data.task_id === activeRunTaskId.value)) {
                                    taskScreenshot.value = '/api/automation/images/' + data.data.image_id;
                                }
                                const target = chatMessages.value.find(m => m.taskId === data.task_id);
                                if (target && data.kind === 'subtask' && target.todoList) {
                                    target.currentTodoIndex = data.data.index;
                                    target.todoList.forEach((item,i) => item.status = i < data.data.index ? 'completed' : i === data.data.index ? 'running' : 'pending');
                                }
                                if (target && data.kind === 'state') {
                                    target.content = data.data.reason || ('任务状态：' + data.data.status);
                                }
                                if (target && data.kind === 'task_finished') {
                                    apiCall(`/api/tasks/${data.task_id}`).then(task => {
                                        target.status = task.status === 'completed' ? 'success' : 'error';
                                        target.content = task.status === 'completed' ? '执行结束，点击本消息可查看详情。' : task.executions.map(c=>c.message).join('；');
                                        if (target.todoList) target.todoList.forEach((item,i)=> item.status = task.executions.every(c=>c.step_index>i) ? 'completed' : 'failed');
                                        chatRunning.value = false;
                                        saveCurrentSession();
                                    });
                                }
                                break;
                            }
                            case 'task_finished':
                                if (chatMessages.value.some(m=>m.taskId===data.task_id)) break;
                                if(data.task_id===activeRunTaskId.value)taskRunning.value = false;
                                // 检查最后一条消息是否是复杂任务（有 todoList）
                                const lastMsgForToast = chatMessages.value.length > 0 ? chatMessages.value[chatMessages.value.length - 1] : null;
                                const isComplexTask = lastMsgForToast && lastMsgForToast.todoList && lastMsgForToast.todoList.length > 0;
                                const isSegmentSequenceTask = chatSegmentSequenceRunning.value;

                                if (isComplexTask) {
                                    // 复杂任务子任务完成，显示简短提示
                                    const currentIdx = lastMsgForToast.currentTodoIndex;
                                    if (currentIdx !== undefined && currentIdx >= 0 && currentIdx < lastMsgForToast.todoList.length) {
                                        showToast(`子任务 ${currentIdx + 1}/${lastMsgForToast.todoList.length} ${data.success ? '完成' : '失败'}`, data.success ? 'success' : 'error');
                                    }
                                } else if (isSegmentSequenceTask) {
                                    // @设备分段模式：每段完成由主循环继续调度，避免这里提前结束 chatRunning
                                    showToast(`分段步骤${data.success ? '完成' : '失败'}，继续执行下一步...`, data.success ? 'success' : 'error');
                                } else {
                                    // 普通任务，显示完整提示
                                    showToast(data.message, data.success ? 'success' : 'error');
                                }
                                // Update chat message status and use screenshot from WebSocket
                                // 复杂任务模式下（消息有todoList），不要在这里修改状态，让循环自己控制
                                // 普通任务（消息没有todoList）才在这里更新状态
                                if (chatRunning.value && chatMessages.value.length > 0 && !isComplexTask && !isSegmentSequenceTask) {
                                    const lastMsg = chatMessages.value[chatMessages.value.length - 1];
                                    if (lastMsg.role === 'assistant' && lastMsg.status === 'running') {
                                        lastMsg.status = data.success ? 'success' : 'error';
                                        // 显示具体的错误信息
                                        if (data.success) {
                                            lastMsg.content = '✅ 任务执行完成！';
                                        } else {
                                            // 提取并格式化错误信息
                                            let errorMsg = data.message || '任务执行失败';
                                            if (errorMsg.includes('Token error') || errorMsg.includes('limited')) {
                                                errorMsg = '❌ ' + errorMsg + '\n\n💡 提示：模型服务被限流，请稍后再试。';
                                            } else if (errorMsg.includes('Task failed:')) {
                                                errorMsg = '❌ ' + errorMsg.replace('Task failed:', '任务失败:');
                                            } else {
                                                errorMsg = '❌ 任务执行失败: ' + errorMsg;
                                            }
                                            lastMsg.content = errorMsg;
                                        }
                                        // 使用 screenshot_id 从数据库加载截图，不再使用 base64
                                        if (data.screenshot_id && currentSessionId.value && lastMsg.id) {
                                            // 立即更新消息的 screenshots 数组，使用 screenshot_id 构建 image_url
                                            if (!lastMsg.screenshots) {
                                                lastMsg.screenshots = [];
                                            }
                                            // 检查是否已经存在这个截图，避免重复添加
                                            const exists = lastMsg.screenshots.some(s => s.id === data.screenshot_id);
                                            if (!exists) {
                                                lastMsg.screenshots.push({
                                                    id: data.screenshot_id,
                                                    image_url: `/api/chat/screenshots/${data.screenshot_id}`
                                                });
                                            }
                                        }
                                    }
                                    chatRunning.value = false;
                                    // Save session after task completes
                                    saveCurrentSession();
                                }
                                // Refresh scheduler logs when a scheduled task finishes
                                if (data.task_type === 'scheduled') {
                                    loadSchedulerLogs();
                                }
                                break;
                            case 'task_tokens':
                                // Update chat message tokens - only for current session
                                if (chatMessages.value.length > 0) {
                                    // Check session_id matches current session
                                    if (!data.session_id || data.session_id !== currentSessionId.value) {
                                        console.log(`Token for session ${data.session_id} ignored (current: ${currentSessionId.value})`);
                                        break;
                                    }

                                    // Find target message - only match RUNNING tasks
                                    // Do NOT match completed tasks to avoid accumulating tokens on old messages
                                    let targetMsg = null;
                                    for (let i = chatMessages.value.length - 1; i >= 0; i--) {
                                        const msg = chatMessages.value[i];
                                        if (msg.role === 'assistant') {
                                            if (data.message_id && msg.id !== data.message_id) continue;
                                            // Only match running tasks - NOT completed ones
                                            const isRunning = msg.status === 'running';
                                            const isComplexTaskRunning = msg.todoList && msg.todoList.length > 0 &&
                                                msg.todoList.some(t => t.status === 'running');

                                            if (isRunning || isComplexTaskRunning) {
                                                if (data.task_id && msg.taskId && msg.taskId !== data.task_id) {
                                                    continue;
                                                }
                                                targetMsg = msg;
                                                break;
                                            }
                                        }
                                    }

                                    if (targetMsg) {
                                        if (!targetMsg.tokens) targetMsg.tokens = 0;
                                        // 累加 token (因为是一次次推过来的)
                                        targetMsg.tokens += data.total_tokens;
                                        // 保存 token 到数据库
                                        saveMessageStatusToServer();
                                    }
                                }
                                break;
                            case 'devices':
                                devices.value = data.devices;
                                break;
                            case 'ping':
                                if (ws && ws.readyState === WebSocket.OPEN) {
                                    ws.send(JSON.stringify({ type: 'pong' }));
                                }
                                break;
                            case 'tap_preview_request':
                                // Debug mode: show tap preview modal
                                if (debugMode.value) {
                                    tapPreviewData.value = {
                                        requestId: data.request_id,
                                        x: data.x,
                                        y: data.y,
                                        width: data.width,
                                        height: data.height,
                                        screenshot: data.screenshot
                                    };
                                    tapPreviewAdjustedX.value = data.x;
                                    tapPreviewAdjustedY.value = data.y;
                                    showTapPreview.value = true;
                                } else {
                                    // Auto-confirm if debug mode is not enabled
                                    if (ws && ws.readyState === WebSocket.OPEN) {
                                        ws.send(JSON.stringify({
                                            type: 'tap_preview_response',
                                            request_id: data.request_id,
                                            proceed: true,
                                            x: data.x,
                                            y: data.y
                                        }));
                                    }
                                }
                                break;
                            case 'system_alert':
                                // System alert from backend (e.g., Telegram conflict)
                                const alertId = Date.now();
                                systemAlerts.value.push({
                                    id: alertId,
                                    level: data.level || 'warning',
                                    title: data.title || '系统通知',
                                    message: data.message || '',
                                });
                                // Auto dismiss if specified
                                if (data.auto_dismiss > 0) {
                                    setTimeout(() => {
                                        systemAlerts.value = systemAlerts.value.filter(a => a.id !== alertId);
                                    }, data.auto_dismiss * 1000);
                                }
                                break;
                        }
                    }

                    // Device functions

                    // Chat Session Management Functions
                    function loadSessions() {
                        try {
                            const stored = localStorage.getItem(SESSIONS_STORAGE_KEY);
                            if (stored) {
                                chatSessions.value = JSON.parse(stored);
                                // Sort by updatedAt descending
                                chatSessions.value.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
                            }
                        } catch (e) {
                            console.error('Failed to load sessions:', e);
                            chatSessions.value = [];
                        }
                    }

                    function saveSessions() {
                        try {
                            // Deep copy sessions to avoid modifying reactive state
                            const sessionsToSave = JSON.parse(JSON.stringify(chatSessions.value));

                            // Remove heavy data (screenshots metadata and large logs) from saved sessions
                            sessionsToSave.forEach(session => {
                                if (session.messages) {
                                    session.messages.forEach(msg => {
                                        // Remove screenshot base64 (if any legacy data exists)
                                        if (msg.screenshot) {
                                            msg.screenshot = null;
                                        }
                                        // Screenshots are stored in database, only keep minimal metadata
                                        // Limit logs size
                                        if (msg.logs && msg.logs.length > 50) {
                                            msg.logs = msg.logs.slice(-50); // Keep only last 50 logs
                                        }
                                        // Clean subtask logs too
                                        if (msg.todoList) {
                                            msg.todoList.forEach(todo => {
                                                if (todo.logs && todo.logs.length > 20) {
                                                    todo.logs = todo.logs.slice(-20);
                                                }
                                            });
                                        }
                                    });
                                }
                            });

                            localStorage.setItem(SESSIONS_STORAGE_KEY, JSON.stringify(sessionsToSave));
                        } catch (e) {
                            console.error('Failed to save sessions:', e);
                            // Fallback: try to save only the current session if full save fails
                            if (e.name === 'QuotaExceededError') {
                                try {
                                    // Try to clean up old sessions
                                    const currentSession = sessionsToSave.find(s => s.id === currentSessionId.value);
                                    if (currentSession) {
                                        localStorage.setItem(SESSIONS_STORAGE_KEY, JSON.stringify([currentSession]));
                                        showToast('存储空间不足，已清理旧会话', 'warning');
                                    }
                                } catch (retryError) {
                                    showToast('存储空间已满，无法保存会话', 'error');
                                }
                            }
                        }
                    }

                    function saveCurrentSession() {
                        if (!currentSessionId.value) return;

                        const session = chatSessions.value.find(s => s.id === currentSessionId.value);
                        if (session) {
                            session.messages = chatMessages.value;
                            // 会话时间以最新消息时间为准
                            if (chatMessages.value.length > 0) {
                                const lastMsg = chatMessages.value[chatMessages.value.length - 1];
                                if (lastMsg.timestamp) {
                                    session.updatedAt = lastMsg.timestamp;
                                }
                            }
                            // Update title from first user message if not set
                            if (!session.title || session.title === '新会话') {
                                const firstUserMsg = chatMessages.value.find(m => m.role === 'user');
                                if (firstUserMsg) {
                                    const newTitle = firstUserMsg.content.substring(0, 30) + (firstUserMsg.content.length > 30 ? '...' : '');
                                    session.title = newTitle;
                                    // Sync title to server
                                    apiCall(`/api/chat/sessions/${session.id}`, {
                                        method: 'PATCH',
                                        body: JSON.stringify({ title: newTitle })
                                    }).catch(err => console.warn('Failed to sync session title:', err));
                                }
                            }
                            
                            // 重新按更新时间排序会话列表
                            chatSessions.value.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
                            
                            saveSessions();

                            // 同步 assistant 消息的 status 和 todoList 到服务器数据库
                            saveMessageStatusToServer();
                        }
                    }

                    // 保存消息状态到服务器（非阻塞，不影响本地操作）
                    // 🆕 使用防抖避免频繁请求
                    let saveMessageTimer = null;
                    let lastSavedMessageStates = new Map(); // 记录每条消息上次保存的状态

                    function syncLastSavedStates() {
                        lastSavedMessageStates.clear();
                        if (chatMessages.value && chatMessages.value.length > 0) {
                            chatMessages.value.forEach(msg => {
                                if (msg.role === 'assistant' && msg.id) {
                                    const state = `${msg.status || ''}-${JSON.stringify(msg.todoList || null)}-${msg.tokens || 0}-${msg.model_name || ''}`;
                                    lastSavedMessageStates.set(msg.id, state);
                                }
                            });
                        }
                    }

                    async function saveMessageStatusToServer() {
                        // 清除之前的定时器
                        if (saveMessageTimer) {
                            clearTimeout(saveMessageTimer);
                        }

                        // 延迟300ms执行，如果300ms内再次调用则重新计时
                        saveMessageTimer = setTimeout(async () => {
                            if (!currentSessionId.value) return;

                            // 找出需要保存状态的 assistant 消息
                            for (const msg of chatMessages.value) {
                                // These states belong to the conversation endpoint; avoid stale browser writes.
                                if (msg.status === 'thinking' || msg.status === 'ready') continue;
                                if (msg.role === 'assistant' && msg.id && (msg.status || msg.todoList || msg.tokens)) {
                                    // 计算当前消息的状态指纹（包含 tokens 和 model_name）
                                    const currentState = `${msg.status || ''}-${JSON.stringify(msg.todoList || null)}-${msg.tokens || 0}-${msg.model_name || ''}`;
                                    const lastState = lastSavedMessageStates.get(msg.id);

                                    // 跳过未变化的消息
                                    if (lastState === currentState) {
                                        continue;
                                    }

                                    // 先乐观更新本地状态，防止网络延迟导致的并发堆叠
                                    lastSavedMessageStates.set(msg.id, currentState);

                                    try {
                                        await apiCall(`/api/chat/sessions/${currentSessionId.value}/messages/${msg.id}`, {
                                            method: 'PATCH',
                                            body: JSON.stringify({
                                                status: msg.status || null,
                                                content: msg.content || null,
                                                todo_list: msg.todoList || null,
                                                tokens: msg.tokens || 0,
                                                model_name: msg.model_name || null
                                            })
                                        });

                                    } catch (error) {
                                        // 失败时恢复状态，以便下次重试
                                        lastSavedMessageStates.delete(msg.id);
                                        // 静默失败，不影响用户体验
                                        console.debug('Failed to save message status to server:', error);
                                    }
                                }
                            }
                        }, 300); // 300ms防抖延迟
                    }

                    async function createNewSession() {
                        // Save current session first
                        saveCurrentSession();

                        // 始终在服务器创建会话，确保 ID 同步
                        const deviceId = chatDeviceId.value || 'default';
                        const serverSession = await apiCall('/api/chat/sessions', {
                            method: 'POST',
                            body: JSON.stringify({
                                device_id: deviceId,
                                title: '新会话'
                            })
                        });

                        const newSession = {
                            id: serverSession.id,
                            title: serverSession.title || '新会话',
                            deviceId: serverSession.device_id,
                            messages: [],
                            createdAt: serverSession.created_at,
                            updatedAt: serverSession.updated_at
                        };
                        chatSessions.value.unshift(newSession);
                        currentSessionId.value = newSession.id;
                        chatMessages.value = [];
                        saveSessions();
                    }

                    // HTTP 对话刷新后可补齐回复，绝不把待提交的意图自动重发为手机任务。
                    async function recoverConversationReplies(sessionId) {
                        const pending = chatMessages.value.filter(m => m.id && m.status === 'thinking');
                        if (!pending.length) return;
                        contextMonitor.start(sessionId);
                        while (currentSessionId.value === sessionId) {
                            try {
                                for (const msg of pending.filter(m => m.status === 'thinking')) {
                                    const saved = await apiCall(`/api/chat/sessions/${sessionId}/messages/${msg.id}`);
                                    if (currentSessionId.value !== sessionId) return;
                                    Object.assign(msg, {content:saved.content, status:saved.status,
                                        tokens:saved.tokens, model_name:saved.model_name});
                                    void contextMonitor.refresh(sessionId);
                                }
                            } catch (_) { contextMonitor.stop(); return; }
                            if (pending.every(m => m.status !== 'thinking')) {
                                contextMonitor.stop();
                                void contextMonitor.refresh(sessionId);
                                saveCurrentSession();
                                scrollChatToBottom();
                                return;
                            }
                            await new Promise(resolve => setTimeout(resolve, 2000));
                        }
                    }

                    async function switchSession(sessionId) {
                        if (sessionId === currentSessionId.value) return;

                        // Save current session first
                        saveCurrentSession();

                        const session = chatSessions.value.find(s => s.id === sessionId);
                        if (session) {
                            currentSessionId.value = session.id;

                            // Trigger session switch animation
                            const messagesEl = chatMessagesRef.value;
                            if (messagesEl) {
                                messagesEl.classList.remove('session-switching');
                                // Force reflow to restart animation
                                void messagesEl.offsetWidth;
                                messagesEl.classList.add('session-switching');
                                messagesEl.addEventListener('animationend', () => {
                                    messagesEl.classList.remove('session-switching');
                                }, { once: true });
                            }

                            // 优先从服务器加载完整的消息数据（包括 screenshots, tokens, model_name）
                            try {
                                const detailData = await apiCall(`/api/chat/sessions/${sessionId}/detail`);
                                if (detailData && detailData.messages) {
                                    // 使用服务器数据作为主要数据源，并映射字段名
                                    chatMessages.value = detailData.messages.map(msg => ({
                                        ...msg,
                                        timestamp: msg.created_at || msg.timestamp,  // Map created_at to timestamp
                                        screenshots: msg.screenshots || []
                                    }));

                                    // 更新会话对象中的消息缓存
                                    session.messages = chatMessages.value;
                                } else {
                                    // 服务器没有返回消息，使用本地缓存
                                    chatMessages.value = session.messages || [];
                                }
                            } catch (error) {
                                // 如果会话不存在（404），从列表中移除
                                if (error.message && error.message.includes('Session not found')) {
                                    console.warn(`Session ${sessionId} not found, removing from list`);
                                    const index = chatSessions.value.findIndex(s => s.id === sessionId);
                                    if (index !== -1) {
                                        chatSessions.value.splice(index, 1);
                                        saveSessions();

                                        // 如果有其他会话，切换到下一个，否则创建新会话
                                        if (chatSessions.value.length > 0) {
                                            await switchSession(chatSessions.value[0].id);
                                            return;
                                        } else {
                                            createNewSession();
                                            return;
                                        }
                                    }
                                } else {
                                    console.error('Failed to load session detail from server:', error);
                                    // 其他错误继续使用本地数据
                                    chatMessages.value = session.messages || [];
                                }
                            }
                            
                            syncLastSavedStates();

                            recoverConversationReplies(sessionId);
                            void contextMonitor.refresh(sessionId);

                            // 使用 nextTick 确保 DOM 更新后再滚动
                            Vue.nextTick(() => {
                                scrollChatToBottom();
                            });
                        }
                    }

                    async function deleteSession(sessionId) {
                        if (!confirm('确定要删除这个会话吗？')) return;

                        // 从服务器删除会话
                        try {
                            await apiCall(`/api/chat/sessions/${sessionId}`, { method: 'DELETE' });
                        } catch (error) {
                            console.error('Failed to delete session from server:', error);
                            // 继续删除本地会话，即使服务器删除失败
                        }

                        // 从本地删除会话
                        const index = chatSessions.value.findIndex(s => s.id === sessionId);
                        if (index !== -1) {
                            chatSessions.value.splice(index, 1);
                            saveSessions();

                            // If deleted current session, switch to another or create new
                            if (sessionId === currentSessionId.value) {
                                if (chatSessions.value.length > 0) {
                                    await switchSession(chatSessions.value[0].id);
                                } else {
                                    await createNewSession();
                                }
                            }
                        }
                    }

                    async function clearAllSessions() {
                        if (!confirm('确定要清除所有会话历史吗？此操作不可撤销。')) return;

                        // 从服务器逐个删除
                        for (const session of chatSessions.value) {
                            try {
                                await apiCall(`/api/chat/sessions/${session.id}`, { method: 'DELETE' });
                            } catch (e) {
                                console.warn(`Failed to delete session ${session.id} from server:`, e);
                            }
                        }

                        // 清空本地
                        chatSessions.value = [];
                        saveSessions();
                        sessionSearchQuery.value = '';

                        // 创建新会话
                        await createNewSession();
                        showToast('所有会话已清除', 'success');
                    }

                    function formatSessionTime(isoString) {
                        if (!isoString) return '';
                        const date = new Date(isoString);
                        const now = new Date();
                        const diffMs = now - date;
                        const diffMins = Math.floor(diffMs / 60000);
                        const diffHours = Math.floor(diffMs / 3600000);
                        const diffDays = Math.floor(diffMs / 86400000);

                        if (diffMins < 1) return '刚刚';
                        if (diffMins < 60) return `${diffMins}分钟前`;
                        if (diffHours < 24) return `${diffHours}小时前`;
                        if (diffDays < 7) return `${diffDays}天前`;
                        return date.toLocaleDateString();
                    }

                    function formatMsgTime(timestamp) {
                        if (!timestamp) return '';
                        const date = new Date(timestamp);
                        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                    }

                    async function initChatSessions() {
                        // 只从服务器加载会话列表，数据库是唯一数据源
                        try {
                            const serverSessions = await apiCall('/api/chat/sessions?limit=50');
                            if (serverSessions && serverSessions.length > 0) {
                                // 将服务器会话转换为前端格式
                                const serverSessionsFormatted = serverSessions.map(s => ({
                                    id: s.id,
                                    title: s.title || '新会话',
                                    deviceId: s.device_id,
                                    status: s.status,
                                    updatedAt: s.updated_at,
                                    totalTokens: s.total_tokens || 0,
                                    messages: []  // 消息稍后加载
                                }));

                                // 按更新时间排序
                                serverSessionsFormatted.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
                                chatSessions.value = serverSessionsFormatted;
                                saveSessions();
                            } else {
                                // 服务器没有会话
                                chatSessions.value = [];
                            }
                        } catch (error) {
                            console.error('Failed to load sessions from server:', error);
                            // 服务器加载失败，显示空列表
                            chatSessions.value = [];
                        }

                        // Auto-enter most recent session or create new one
                        if (chatSessions.value.length > 0) {
                            const mostRecent = chatSessions.value[0];
                            currentSessionId.value = mostRecent.id;

                            // 如果本地有消息数据，先使用本地数据
                            if (mostRecent.messages && mostRecent.messages.length > 0) {
                                chatMessages.value = mostRecent.messages;
                            } else {
                                chatMessages.value = [];
                            }
                            syncLastSavedStates();

                            // 尝试从服务器加载完整的消息数据（包括 screenshots）
                            // 这样可以确保服务重启后也能看到截图
                            try {
                                // 在加载服务器数据前，先保存本地消息的状态和 todoList（服务器不保存这些字段）
                                const localDataMap = {};
                                if (chatMessages.value && chatMessages.value.length > 0) {
                                    chatMessages.value.forEach(msg => {
                                        if (msg.id) {
                                            localDataMap[msg.id] = {
                                                status: msg.status,
                                                todoList: msg.todoList,
                                                currentTodoIndex: msg.currentTodoIndex,
                                                logs: msg.logs || []  // 也保存本地日志作为后备
                                            };
                                        }
                                    });
                                }

                                const detailData = await apiCall(`/api/chat/sessions/${mostRecent.id}/detail`);
                                if (detailData && detailData.messages) {
                                    // 使用服务器的消息数据（更完整，包含 screenshots）
                                    chatMessages.value = detailData.messages.map(msg => {
                                        const localData = localDataMap[msg.id] || {};
                                        // 优先使用服务器状态，其次使用本地保存的状态，最后默认 success
                                        let status = null;
                                        let todoList = null;
                                        if (msg.role === 'assistant') {
                                            // 服务器现在可能返回 status 和 todo_list
                                            status = msg.status || localData.status || 'success';
                                            // todo_list 从服务器返回（如果有），否则使用本地
                                            todoList = msg.todo_list || localData.todoList || null;
                                        }

                                        // 日志：优先使用服务器日志（更完整），如果服务器没有则用本地
                                        let logs = [];
                                        if (msg.logs && msg.logs.length > 0) {
                                            logs = msg.logs.map(l => l.content || l);
                                        } else if (localData.logs && localData.logs.length > 0) {
                                            logs = localData.logs;
                                        }

                                        return {
                                            id: msg.id,
                                            role: msg.role,
                                            content: msg.content,
                                            timestamp: msg.created_at,
                                            logs: logs,
                                            screenshots: msg.screenshots || [],
                                            status: status,
                                            // 优先使用服务器的 todoList，其次是本地数据
                                            todoList: todoList,
                                            currentTodoIndex: localData.currentTodoIndex,
                                            tokens: msg.tokens || 0,
                                            model_name: msg.model_name || null
                                        };
                                    });

                                    // 更新会话中的消息数据
                                    mostRecent.messages = chatMessages.value;
                                    syncLastSavedStates();
                                    saveSessions();
                                }
                            } catch (error) {
                                // 如果会话不存在（404），从列表中移除
                                if (error.message && error.message.includes('Session not found')) {
                                    console.warn(`Session ${mostRecent.id} not found, removing from list`);
                                    const index = chatSessions.value.findIndex(s => s.id === mostRecent.id);
                                    if (index !== -1) {
                                        chatSessions.value.splice(index, 1);
                                        saveSessions();

                                        // 如果有其他会话，切换到下一个
                                        if (chatSessions.value.length > 0) {
                                            await switchSession(chatSessions.value[0].id);
                                            return;
                                        } else {
                                            createNewSession();
                                            return;
                                        }
                                    }
                                } else {
                                    console.error('Failed to load session detail from server:', error);
                                    // 继续使用本地数据
                                }
                            }

                            recoverConversationReplies(currentSessionId.value);
                            void contextMonitor.refresh(currentSessionId.value);
                            // Restore state by persistent message/task association.
                            try {
                                const records = automation.ready ? (await apiCall('/api/automation/tasks?limit=500')).tasks : null;
                                chatMessages.value.forEach(msg => {
                                    if (!records || msg.role !== 'assistant' || msg.status !== 'running') return;
                                    const task = records.find(t=>t.id===msg.taskId || t.options.message_id===msg.id);
                                    if (!task) {
                                        msg.status = 'error';
                                        msg.content = '执行状态未知，请在任务执行页的队列与历史中检查；未判定为成功。';
                                        return;
                                    }
                                    msg.taskId = task.id;
                                    const ended = isTerminal(task.status);
                                    msg.status = ended ? (task.status==='completed'?'success':'error') : 'running';
                                    if (!ended) chatRunning.value = true;
                                    msg.content = ended ? task.executions.map(c=>c.message).join('；') : '任务状态：'+task.status;
                                });
                            } catch (statusError) {
                                console.error('Failed to check task status:', statusError);
                                chatMessages.value.forEach(msg => {
                                    if (msg.role === 'assistant' && msg.status === 'running') {
                                        msg.content = '暂时无法获取执行状态，请在任务详情中核查。';
                                    }
                                });
                            }
                            // 保存修复后的状态
                            saveCurrentSession();
                            // 页面加载后自动滚动到最新消息
                            Vue.nextTick(() => {
                                scrollChatToBottom();
                            });
                        } else {
                            createNewSession();
                        }
                    }

                    // Chat functions
                    function scrollChatToBottom() {
                        setTimeout(() => {
                            if (chatMessagesRef.value) {
                                chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight;
                            }
                        }, 50);
                    }

                    function onChatDeviceChange() {
                        // Auto-select device for preview too
                        if (chatDeviceId.value && !previewDeviceId.value) {
                            previewDeviceId.value = chatDeviceId.value;
                        }
                    }

                    function adjustChatInputHeight(e) {
                        const el = e.target;
                        el.style.height = 'auto';
                        el.style.height = Math.min(el.scrollHeight, 100) + 'px';
                        chatCursorPos.value = typeof el.selectionStart === 'number'
                            ? el.selectionStart
                            : (el.value || '').length;
                    }

                    function syncChatCursor(e) {
                        const el = e?.target;
                        if (!el) return;
                        chatCursorPos.value = typeof el.selectionStart === 'number'
                            ? el.selectionStart
                            : (el.value || '').length;
                    }

                    // 监听输入内容变化，自动调整高度
                    watch(chatInput, () => {
                        Vue.nextTick(() => {
                            const el = document.querySelector('.chat-input');
                            if (el) {
                                el.style.height = 'auto';
                                // 如果内容为空，重置为初始高度（通过 rows 属性控制）
                                if (!chatInput.value) {
                                    el.style.height = '';
                                } else {
                                    el.style.height = Math.min(el.scrollHeight, 100) + 'px';
                                }
                            }
                        });

                        const slashList = filteredAdbQuickCommands.value || [];
                        if (!isAdbCommandMode.value || slashList.length === 0) {
                            adbSuggestionIndex.value = -1;
                        } else {
                            if (adbSuggestionIndex.value < 0 || adbSuggestionIndex.value >= slashList.length) {
                                adbSuggestionIndex.value = 0;
                            }
                            ensureActiveAdbSuggestionVisible();
                        }

                        const mentionList = filteredDeviceMentionSuggestions.value || [];
                        if (!isDeviceMentionMode.value || mentionList.length === 0) {
                            deviceMentionSuggestionIndex.value = -1;
                        } else {
                            if (deviceMentionSuggestionIndex.value < 0 || deviceMentionSuggestionIndex.value >= mentionList.length) {
                                deviceMentionSuggestionIndex.value = 0;
                            }
                            ensureActiveDeviceMentionSuggestionVisible();
                        }
                    });

                    watch(filteredAdbQuickCommands, (list) => {
                        const items = list || [];
                        if (!isAdbCommandMode.value || items.length === 0) {
                            adbSuggestionIndex.value = -1;
                            return;
                        }
                        if (adbSuggestionIndex.value < 0 || adbSuggestionIndex.value >= items.length) {
                            adbSuggestionIndex.value = 0;
                        }
                        ensureActiveAdbSuggestionVisible();
                    });

                    watch(filteredDeviceMentionSuggestions, (list) => {
                        const items = list || [];
                        if (!isDeviceMentionMode.value || items.length === 0) {
                            deviceMentionSuggestionIndex.value = -1;
                            return;
                        }
                        if (deviceMentionSuggestionIndex.value < 0 || deviceMentionSuggestionIndex.value >= items.length) {
                            deviceMentionSuggestionIndex.value = 0;
                        }
                        ensureActiveDeviceMentionSuggestionVisible();
                    });

                    function ensureSuggestionVisible(panelSelector, itemSelector) {
                        Vue.nextTick(() => {
                            const panel = document.querySelector(panelSelector);
                            if (!panel) return;
                            const activeItem = panel.querySelector(itemSelector);
                            if (!activeItem) return;

                            const panelTop = panel.scrollTop;
                            const panelBottom = panelTop + panel.clientHeight;
                            const itemTop = activeItem.offsetTop;
                            const itemBottom = itemTop + activeItem.offsetHeight;

                            const padding = 6;
                            if (itemTop < panelTop) {
                                panel.scrollTop = Math.max(0, itemTop - padding);
                            } else if (itemBottom > panelBottom) {
                                panel.scrollTop = Math.max(0, itemBottom - panel.clientHeight + padding);
                            }
                        });
                    }

                    function ensureActiveAdbSuggestionVisible() {
                        ensureSuggestionVisible('.adb-command-suggestions', '.adb-command-item.active');
                    }

                    function ensureActiveDeviceMentionSuggestionVisible() {
                        ensureSuggestionVisible('.device-mention-suggestions', '.device-mention-item.active');
                    }

                    // Retry a previous message
                    function retryMessage(content) {
                        if (chatRunning.value) return;
                        chatInput.value = content;
                        sendChatMessage();
                    }

                    function applyAdbQuickCommand(item) {
                        if (!item || !item.command) return;
                        chatInput.value = item.command;
                        const idx = filteredAdbQuickCommands.value.findIndex(x => x.command === item.command);
                        adbSuggestionIndex.value = idx >= 0 ? idx : -1;
                        Vue.nextTick(() => {
                            const el = document.querySelector('.chat-input');
                            if (el) {
                                el.focus();
                                el.setSelectionRange(el.value.length, el.value.length);
                            }
                        });
                    }

                    function applyDeviceMentionSuggestion(item) {
                        if (!item || !item.id) return;
                        const ctx = mentionContext.value;
                        if (!ctx.active || ctx.start < 0 || ctx.end < 0) return;

                        const text = chatInput.value || '';
                        const before = text.slice(0, ctx.start);
                        const after = text.slice(ctx.end);
                        const mentionToken = item.mentionToken || item.id;
                        const spacer = after.startsWith(' ') || after.length === 0 ? ' ' : ' ';
                        const nextValue = `${before}@${mentionToken}${spacer}${after}`;

                        chatInput.value = nextValue;
                        const nextCursor = (before.length + mentionToken.length + 2); // '@' + trailing space
                        chatCursorPos.value = nextCursor;
                        deviceMentionSuggestionIndex.value = -1;

                        Vue.nextTick(() => {
                            const el = document.querySelector('.chat-input');
                            if (el) {
                                el.focus();
                                el.setSelectionRange(nextCursor, nextCursor);
                            }
                        });
                    }

                    function handleChatInputKeydown(event) {
                        const inputEl = event?.target;
                        if (inputEl && typeof inputEl.selectionStart === 'number') {
                            chatCursorPos.value = inputEl.selectionStart;
                        }

                        const slashCandidates = filteredAdbQuickCommands.value || [];
                        const mentionCandidates = filteredDeviceMentionSuggestions.value || [];
                        const inSlashMode = isAdbCommandMode.value && slashCandidates.length > 0;
                        const inMentionMode = isDeviceMentionMode.value && mentionCandidates.length > 0;

                        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                            if (inSlashMode) {
                                event.preventDefault();
                                if (event.key === 'ArrowDown') {
                                    adbSuggestionIndex.value = (adbSuggestionIndex.value + 1 + slashCandidates.length) % slashCandidates.length;
                                } else {
                                    adbSuggestionIndex.value = adbSuggestionIndex.value <= 0
                                        ? slashCandidates.length - 1
                                        : adbSuggestionIndex.value - 1;
                                }
                                ensureActiveAdbSuggestionVisible();
                                return;
                            }
                            if (inMentionMode) {
                                event.preventDefault();
                                if (event.key === 'ArrowDown') {
                                    deviceMentionSuggestionIndex.value = (deviceMentionSuggestionIndex.value + 1 + mentionCandidates.length) % mentionCandidates.length;
                                } else {
                                    deviceMentionSuggestionIndex.value = deviceMentionSuggestionIndex.value <= 0
                                        ? mentionCandidates.length - 1
                                        : deviceMentionSuggestionIndex.value - 1;
                                }
                                ensureActiveDeviceMentionSuggestionVisible();
                                return;
                            }
                        }

                        if (event.key === 'Tab' && inMentionMode) {
                            event.preventDefault();
                            const idx = deviceMentionSuggestionIndex.value >= 0 ? deviceMentionSuggestionIndex.value : 0;
                            const selected = mentionCandidates[idx];
                            if (selected) {
                                applyDeviceMentionSuggestion(selected);
                            }
                            return;
                        }

                        if (event.key !== 'Enter') {
                            return;
                        }
                        // Shift+Enter keeps newline editing behavior.
                        if (event.shiftKey) {
                            return;
                        }
                        // IME composing state should not trigger send.
                        if (event.isComposing || event.keyCode === 229) {
                            return;
                        }
                        if (inMentionMode) {
                            event.preventDefault();
                            const idx = deviceMentionSuggestionIndex.value >= 0 ? deviceMentionSuggestionIndex.value : 0;
                            const selected = mentionCandidates[idx];
                            if (selected) {
                                applyDeviceMentionSuggestion(selected);
                            }
                            return;
                        }
                        if (inSlashMode && adbSuggestionIndex.value >= 0) {
                            const selected = slashCandidates[adbSuggestionIndex.value];
                            const raw = (chatInput.value || '').trim();
                            // In command-search mode (only prefix, no args yet), Enter applies selected command.
                            if (selected && (raw === '/' || !raw.includes(' '))) {
                                chatInput.value = selected.command;
                            }
                        }
                        event.preventDefault();
                        sendChatMessage();
                    }

                    const isSkipping = ref(false);

                    async function skipSubtask(msg) {
                        if (msg.taskId) await apiCall(`/api/tasks/${msg.taskId}/stop`, {method:'POST',body:'{}'});
                    }

                    // TodoList Confirmation Functions
                    async function confirmTodoList(msg) {
                        if (!msg.todoList || msg.todoList.length === 0) {
                            showToast('任务清单为空', 'error');
                            return;
                        }

                        // Validate all subtasks have content
                        const emptyTask = msg.todoList.find(item => !item.content || !item.content.trim());
                        if (emptyTask) {
                            showToast('请填写所有子任务内容', 'error');
                            return;
                        }

                        // Update message status
                        msg.status = 'running';
                        msg.content = '📋 开始执行任务清单...';
                        awaitingTodoListConfirmation.value = false;
                        chatRunning.value = true;

                        // Save changes
                        saveCurrentSession();
                        scrollChatToBottom();

                        // Continue with task execution
                        try {
                            // Execute the confirmed todoList
                            await executeConfirmedTodoList(msg);
                        } catch (error) {
                            console.error('Task execution error:', error);
                            msg.status = 'error';
                            msg.content = `❌ 执行失败: ${error.message}`;
                            chatRunning.value = false;
                            saveCurrentSession();
                        }
                    }

                    function cancelTodoList(msg) {
                        if (!confirm('确定要取消此任务吗？')) {
                            return;
                        }

                        msg.status = 'cancelled';
                        msg.content = '❌ 任务已取消';
                        awaitingTodoListConfirmation.value = false;
                        chatRunning.value = false;
                        saveCurrentSession();
                        scrollChatToBottom();
                    }

                    // TodoList Management Functions
                    function moveTodoUp(msg, index) {
                        if (index === 0) return;
                        const temp = msg.todoList[index];
                        msg.todoList[index] = msg.todoList[index - 1];
                        msg.todoList[index - 1] = temp;
                        saveCurrentSession();
                    }

                    function moveTodoDown(msg, index) {
                        if (index === msg.todoList.length - 1) return;
                        const temp = msg.todoList[index];
                        msg.todoList[index] = msg.todoList[index + 1];
                        msg.todoList[index + 1] = temp;
                        saveCurrentSession();
                    }

                    function deleteTodo(msg, index) {
                        if (msg.todoList.length <= 1) {
                            showToast('至少需要保留一个子任务', 'error');
                            return;
                        }
                        if (confirm(`确定要删除子任务"${msg.todoList[index].content}"吗？`)) {
                            msg.todoList.splice(index, 1);
                            saveCurrentSession();
                        }
                    }

                    function autoResizeTextarea(event) {
                        const textarea = event.target;
                        textarea.style.height = 'auto';
                        textarea.style.height = textarea.scrollHeight + 'px';
                    }

                    async function submitManagedChat(msg, deviceIds, sessionId, messageId, steps, taskText) {
                        const result = await apiCall('/api/tasks/run', {
                            method: 'POST',
                            body: JSON.stringify({task_content: taskText || msg.content || '任务清单',
                                device_ids: deviceIds, steps, queue: true, acceptance:chatAcceptance.value||null,
                                send_email: chatAutoEmail.value, task_type: 'chat',
                                session_id: sessionId, message_id: messageId})
                        });
                        msg.taskId = result.task_id;
                        msg.status = 'running';
                        msg.content = '任务已加入队列，可在本消息下暂停或接管设备。';
                        chatRunning.value = true;
                        saveCurrentSession();
                    }

                    async function executeConfirmedTodoList(msg) {
                        await submitManagedChat(msg, [chatDeviceId.value], currentSessionId.value, msg.id,
                            msg.todoList.map(item => ({content: item.content, timeout: subtaskTimeoutSeconds.value})),
                            '复杂任务：' + msg.todoList.map(item => item.content).join('；'));
                    }

                    // Tap preview functions (debug mode)
                    function confirmTapPreview() {
                        if (ws && ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({
                                type: 'tap_preview_response',
                                request_id: tapPreviewData.value.requestId,
                                proceed: true,
                                x: tapPreviewAdjustedX.value,
                                y: tapPreviewAdjustedY.value
                            }));
                        }
                        showTapPreview.value = false;
                    }

                    function cancelTapPreview() {
                        if (ws && ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({
                                type: 'tap_preview_response',
                                request_id: tapPreviewData.value.requestId,
                                proceed: false,
                                x: tapPreviewData.value.x,
                                y: tapPreviewData.value.y
                            }));
                        }
                        showTapPreview.value = false;
                    }

                    function handleTapPreviewClick(event) {
                        const rect = event.currentTarget.getBoundingClientRect();
                        const x = event.clientX - rect.left;
                        const y = event.clientY - rect.top;

                        // Convert to device coordinates
                        const scaleX = tapPreviewData.value.width / rect.width;
                        const scaleY = tapPreviewData.value.height / rect.height;

                        tapPreviewAdjustedX.value = Math.round(x * scaleX);
                        tapPreviewAdjustedY.value = Math.round(y * scaleY);
                    }

                    function formatTaskLogPreview(log, maxLen = 220) {
                        const raw = typeof log === 'object'
                            ? (log.content || JSON.stringify(log))
                            : (log || '');
                        const compact = String(raw).replace(/\s+/g, ' ').trim();
                        if (!compact) return '';
                        return compact.length > maxLen ? `${compact.slice(0, maxLen)} ...` : compact;
                    }

                    function formatOutputSummaryPreview(text, maxLen = 180) {
                        const compact = String(text || '').replace(/\s+/g, ' ').trim();
                        if (!compact) return '';
                        return compact.length > maxLen ? `${compact.slice(0, maxLen)} ...` : compact;
                    }

                    function buildSlashHelpText() {
                        const lines = [
                            '📚 Slash 指令帮助（不走模型，直接 ADB）',
                            '',
                            '常用前缀：',
                            '• /shell <cmd...>',
                            '• /tap <x> <y>',
                            '• /swipe <x1> <y1> <x2> <y2> [duration_ms]',
                            '• /text <content>',
                            '• /key <KEYCODE>',
                            '• /am <args...>',
                            '• /settings <get|put|delete ...>',
                            '• /svc <wifi|data ...>',
                            '• /setprop <key> <value>',
                            '• /appops <args...>',
                            '• /broadcast <args...>',
                            '',
                            '查看类示例：',
                        ];
                        const inspection = adbQuickCommands.filter(item =>
                            (item.command.startsWith('/shell ') || item.command.startsWith('/help'))
                            && !item.desc.includes('（修改）')
                        ).slice(0, 14);
                        inspection.forEach(item => {
                            lines.push(`• ${item.command}  ——  ${item.desc}`);
                        });
                        lines.push('');
                        lines.push('修改类示例：');
                        const mutation = adbQuickCommands.filter(item =>
                            item.desc.includes('（修改）') || item.command.startsWith('/settings put ')
                        ).slice(0, 12);
                        mutation.forEach(item => {
                            lines.push(`• ${item.command}  ——  ${item.desc}`);
                        });
                        lines.push('');
                        lines.push('提示：');
                        lines.push('• Enter 发送，Shift+Enter 换行');
                        lines.push('• 长日志可在“完整执行日志”查看');
                        return lines.join('\n');
                    }

                    async function syncSlashCommandResultToServer(sessionId, messageId, msg, logs) {
                        if (!sessionId || !messageId) return;
                        try {
                            await apiCall(`/api/chat/sessions/${sessionId}/messages/${messageId}`, {
                                method: 'PATCH',
                                body: JSON.stringify({
                                    content: msg.content,
                                    status: msg.status,
                                    tokens: 0,
                                }),
                            });

                            const mergedLogs = (logs || []).filter(Boolean).join('\n');
                            if (mergedLogs) {
                                await apiCall(`/api/chat/sessions/${sessionId}/messages/${messageId}/logs`, {
                                    method: 'POST',
                                    body: JSON.stringify({
                                        content: mergedLogs,
                                        log_type: msg.status === 'success' ? 'info' : 'error',
                                    }),
                                });
                            }
                        } catch (e) {
                            console.warn('Failed to sync slash command result to server:', e);
                        }
                    }

                    async function executeSlashAdbCommand(command, deviceId, assistantMsg, sessionId, messageId) {
                        const normalizedInput = (command || '').trim().toLowerCase();
                        if (normalizedInput === '/help' || normalizedInput === '/help adb' || normalizedInput === '/?') {
                            const helpText = buildSlashHelpText();
                            assistantMsg.logs = ['[HELP] Slash command help'];
                            assistantMsg.status = 'success';
                            assistantMsg.content = helpText;
                            assistantMsg.timestamp = new Date().toISOString();
                            await syncSlashCommandResultToServer(sessionId, messageId, assistantMsg, [helpText]);
                            saveCurrentSession();
                            scrollChatToBottom();
                            return;
                        }

                        assistantMsg.content = `⚡ 执行指令中: ${command}`;
                        assistantMsg.logs = [];
                        saveCurrentSession();

                        const result = await apiCall(`/api/devices/${encodeURIComponent(deviceId)}/adb/execute`, {
                            method: 'POST',
                            body: JSON.stringify({
                                command,
                                timeout_seconds: 25,
                            }),
                        });

                        const exitCodeText = result.exit_code === null || result.exit_code === undefined
                            ? 'N/A'
                            : String(result.exit_code);
                        const stdout = result.stdout || '';
                        const stderr = result.stderr || '';
                        const logs = [
                            `[ADB] ${result.normalized_command || command}`,
                            `[Exit] ${exitCodeText} · ${result.duration_ms || 0}ms`,
                        ];
                        if (stdout) logs.push(`[STDOUT]\n${stdout}`);
                        if (stderr) logs.push(`[STDERR]\n${stderr}`);

                        assistantMsg.logs = logs;
                        assistantMsg.status = result.success ? 'success' : 'error';
                        const stdoutPreview = formatOutputSummaryPreview(stdout);
                        const stderrPreview = formatOutputSummaryPreview(stderr);
                        assistantMsg.content = result.success
                            ? `✅ 指令执行完成\n命令: ${result.normalized_command || command}\n退出码: ${exitCodeText}\n耗时: ${result.duration_ms || 0}ms${stdoutPreview ? `\nSTDOUT: ${stdoutPreview}` : ''}${stderrPreview ? `\nSTDERR: ${stderrPreview}` : ''}\n\n📝 完整输出请点击下方执行日志查看`
                            : `❌ 指令执行失败: ${result.message || 'Unknown error'}\n命令: ${result.normalized_command || command}\n退出码: ${exitCodeText}\n耗时: ${result.duration_ms || 0}ms${stdoutPreview ? `\nSTDOUT: ${stdoutPreview}` : ''}${stderrPreview ? `\nSTDERR: ${stderrPreview}` : ''}\n\n📝 完整输出请点击下方执行日志查看`;
                        assistantMsg.timestamp = new Date().toISOString();
                        await syncSlashCommandResultToServer(sessionId, messageId, assistantMsg, logs);
                        saveCurrentSession();
                        scrollChatToBottom();
                    }

                    function findDeviceForMention(mentionToken, deviceIndex) {
                        const cleaned = normalizeMentionToken(mentionToken);
                        const lowered = cleaned.toLowerCase();
                        const compact = compactMentionToken(cleaned);
                        if (!cleaned || !deviceIndex.length) {
                            return { status: 'not_found' };
                        }

                        const exact = deviceIndex.filter(d =>
                            d.idLower === lowered ||
                            d.nameLower === lowered ||
                            d.nameCompact === compact
                        );
                        if (exact.length === 1) return { status: 'ok', device: exact[0] };
                        if (exact.length > 1) return { status: 'ambiguous', devices: exact };

                        const prefix = deviceIndex.filter(d =>
                            d.idLower.startsWith(lowered) ||
                            d.nameLower.startsWith(lowered) ||
                            d.nameCompact.startsWith(compact) ||
                            d.idCompact.startsWith(compact)
                        );
                        if (prefix.length === 1) return { status: 'ok', device: prefix[0] };
                        if (prefix.length > 1) return { status: 'ambiguous', devices: prefix };

                        const contains = deviceIndex.filter(d =>
                            d.idLower.includes(lowered) ||
                            d.nameLower.includes(lowered) ||
                            d.nameCompact.includes(compact) ||
                            d.idCompact.includes(compact)
                        );
                        if (contains.length === 1) return { status: 'ok', device: contains[0] };
                        if (contains.length > 1) return { status: 'ambiguous', devices: contains };

                        return { status: 'not_found' };
                    }

                    function parseAtDeviceTaskSequence(rawContent) {
                        const text = rawContent || '';
                        const mentionRegex = /(^|[\s，,。;；:：])@([^\s@]+)/g;
                        const mentions = [];
                        let match;
                        while ((match = mentionRegex.exec(text)) !== null) {
                            const prefix = match[1] || '';
                            const token = match[2] || '';
                            const atStart = match.index + prefix.length;
                            const atEnd = atStart + 1 + token.length;
                            mentions.push({ token, atStart, atEnd });
                        }

                        if (!mentions.length) {
                            return {
                                hasMentions: false,
                                sequence: [],
                                unresolved: [],
                                ambiguous: [],
                                emptyTasks: [],
                            };
                        }

                        const deviceIndex = (devices.value || []).map(device => ({
                            id: device.id,
                            name: device.name || '',
                            idLower: (device.id || '').toLowerCase(),
                            nameLower: (device.name || '').toLowerCase(),
                            idCompact: compactMentionToken(device.id || ''),
                            nameCompact: compactMentionToken(device.name || ''),
                        }));

                        const sequence = [];
                        const unresolved = [];
                        const ambiguous = [];
                        const emptyTasks = [];

                        for (let i = 0; i < mentions.length; i++) {
                            const current = mentions[i];
                            const next = mentions[i + 1];
                            const segStart = current.atEnd;
                            const segEnd = next ? next.atStart : text.length;
                            const segmentRaw = text.slice(segStart, segEnd);
                            const taskContent = segmentRaw
                                .replace(/^[\s，,。;；:：\-—–]+/g, '')
                                .replace(/[\s，,。;；:：\-—–]+$/g, '')
                                .trim();

                            const resolved = findDeviceForMention(current.token, deviceIndex);
                            if (resolved.status === 'ambiguous') {
                                ambiguous.push(current.token);
                                continue;
                            }
                            if (resolved.status !== 'ok' || !resolved.device) {
                                unresolved.push(current.token);
                                continue;
                            }
                            if (!taskContent) {
                                emptyTasks.push(current.token);
                                continue;
                            }

                            sequence.push({
                                mentionToken: current.token,
                                deviceId: resolved.device.id,
                                deviceName: resolved.device.name || resolved.device.id,
                                taskContent,
                            });
                        }

                        return {
                            hasMentions: true,
                            sequence,
                            unresolved,
                            ambiguous,
                            emptyTasks,
                        };
                    }

                    async function sendChatMessage() {
                        const rawContent = chatInput.value.trim();
                        if (!rawContent || chatRunning.value) return;

                        const isSlashCommand = rawContent.startsWith('/');
                        const mentionSequence = !isSlashCommand ? parseAtDeviceTaskSequence(rawContent) : null;
                        const hasMentionSequence = !!mentionSequence?.hasMentions;

                        if (isSlashCommand && !chatDeviceId.value) {
                            showToast('请先选择要执行命令的设备', 'warning');
                            return;
                        }

                        let taskContent = rawContent;
                        const targetDeviceIds = hasMentionSequence
                            ? mentionSequence.sequence.map(item => item.deviceId)
                            : [chatDeviceId.value].filter(Boolean);
                        const primaryTargetDeviceId = targetDeviceIds[0];

                        // 在首次网络请求前占用发送状态，避免双击造成重复消息。
                        chatRunning.value = true;
                        try {
                            if (!currentSessionId.value) await createNewSession();
                        } catch (error) {
                            chatRunning.value = false;
                            showToast('创建会话失败，请重试；尚未操作设备。', 'error');
                            return;
                        }

                        // 会话已存在于服务器，直接保存消息
                        const serverSessionId = currentSessionId.value;
                        let serverMessageId = null;
                        let userMessageId = null;

                        // 在服务器添加用户和助手消息
                        try {
                            // 在服务器添加用户消息
                            const userMsgResult = await apiCall(`/api/chat/sessions/${serverSessionId}/messages`, {
                                method: 'POST',
                                body: JSON.stringify({
                                    role: 'user',
                                    content: rawContent
                                })
                            });
                            userMessageId = userMsgResult.id;

                            // 在服务器添加助手消息占位符
                            const assistantMsgResult = await apiCall(`/api/chat/sessions/${serverSessionId}/messages`, {
                                method: 'POST',
                                body: JSON.stringify({
                                    role: 'assistant',
                                    content: isSlashCommand ? '执行中...' : '正在理解你的消息…'
                                })
                            });
                            serverMessageId = assistantMsgResult.id;
                        } catch (error) {
                            console.error('Failed to sync messages to server:', error);
                            showToast('消息保存失败，请重试；尚未操作设备。', 'error');
                            chatRunning.value = false;
                            return;
                        }

                        // Add user message to local state
                        chatMessages.value.push({
                            id: userMessageId,
                            role: 'user',
                            content: rawContent,
                            timestamp: new Date().toISOString()
                        });

                        // Clear input
                        chatInput.value = '';
                        chatCursorPos.value = 0;

                        // Get current active model name
                        let currentModelName = null;
                        try {
                            const modelsData = await apiCall('/api/models');
                            const activeModel = modelsData.services?.find(s => s.is_active);
                            if (activeModel) {
                                currentModelName = activeModel.model_name;
                            }
                        } catch (err) {
                            console.warn('Failed to get active model:', err);
                        }

                        // Add assistant message (running state)
                        let assistantMsg = {
                            id: serverMessageId,  // 服务器消息ID，用于绑定截图
                            role: 'assistant',
                            content: '',
                            status: isSlashCommand ? 'running' : 'thinking',
                            logs: [],
                            screenshots: [],  // 使用 screenshots 数组而不是 screenshot
                            timestamp: new Date().toISOString(),
                            todoList: null,  // 复杂任务模式下的todoList
                            tokens: 0,
                            model_name: currentModelName,  // 保存使用的模型名称
                            taskId: null  // 关联的任务ID，用于匹配WebSocket事件
                        };
                        chatMessages.value.push(assistantMsg);
                        assistantMsg = chatMessages.value[chatMessages.value.length - 1];

                        scrollChatToBottom();
                        chatRunning.value = true;
                        const useComplexTaskMode = complexTaskMode.value && targetDeviceIds.length === 1;

                        try {
                            // Slash command mode: direct ADB execution, bypass model/task pipeline
                            if (isSlashCommand) {
                                await executeSlashAdbCommand(
                                    rawContent,
                                    primaryTargetDeviceId,
                                    assistantMsg,
                                    serverSessionId,
                                    serverMessageId,
                                );
                                chatRunning.value = false;
                                saveCurrentSession();
                                return;
                            }

                            contextMonitor.start(serverSessionId);
                            const decision = await apiCall(`/api/chat/sessions/${serverSessionId}/respond`, {
                                method: 'POST', body: JSON.stringify({
                                    user_message_id: userMessageId, assistant_message_id: serverMessageId,
                                    devices: devices.value.map(d => ({id:d.id, name:d.name || d.id}))
                                })
                            });
                            contextMonitor.accept(decision.context, serverSessionId);
                            assistantMsg.tokens = decision.tokens || 0;
                            assistantMsg.model_name = decision.model_name || currentModelName;
                            if (decision.intent !== 'execute') {
                                assistantMsg.content = decision.reply;
                                assistantMsg.status = 'replied';
                                chatRunning.value = false;
                                saveCurrentSession();
                                scrollChatToBottom();
                                return;
                            }
                            taskContent = decision.task;
                            if (hasMentionSequence) {
                                if (mentionSequence.unresolved.length) throw new Error(`未识别设备: ${mentionSequence.unresolved.join(', ')}`);
                                if (mentionSequence.ambiguous.length) throw new Error(`设备匹配不唯一: ${mentionSequence.ambiguous.join(', ')}`);
                                if (mentionSequence.emptyTasks.length) throw new Error('请补充每个 @设备 对应的任务内容');
                            }
                            if (!targetDeviceIds.length) {
                                assistantMsg.content = '可以执行。请先在上方选择目标设备，再发送“开始执行”。';
                                assistantMsg.status = 'replied';
                                chatRunning.value = false;
                                saveCurrentSession();
                                return;
                            }
                            assistantMsg.status = 'running';
                            assistantMsg.content = '正在提交手机任务…';

                            // Submit the whole device sequence; the backend owns all remaining steps.
                            if (hasMentionSequence) {
                                const sequence = mentionSequence.sequence.map(segment=>({device_id:segment.deviceId,content:segment.taskContent}));
                                const result = await apiCall('/api/tasks/run', {method:'POST',body:JSON.stringify({
                                    task_content:taskContent,device_ids:[...new Set(sequence.map(s=>s.device_id))],
                                    sequence,queue:true,acceptance:chatAcceptance.value||null,task_type:'chat',session_id:serverSessionId,
                                    message_id:serverMessageId,send_email:chatAutoEmail.value})});
                                assistantMsg.taskId = result.task_id;
                                assistantMsg.content = '设备分段任务已保存到后端队列。';
                                assistantMsg.status = 'running';
                                saveCurrentSession();
                                return;
                            }

                            // 复杂任务模式：先拆解任务（暂不支持 @ 多设备）
                            if (complexTaskMode.value && targetDeviceIds.length > 1) {
                                showToast('检测到 @ 多设备，已切换为普通顺序执行模式', 'info');
                            }
                            if (useComplexTaskMode) {
                                assistantMsg.content = '正在拆解任务…';
                                const decomposeResult = await apiCall('/api/tasks/decompose', {
                                    method: 'POST', body: JSON.stringify({task_content: taskContent,
                                        session_id:serverSessionId, message_id:serverMessageId})
                                });
                                assistantMsg.todoList = decomposeResult.todoList.map(item => ({content: item.content, status: 'pending', logs: []}));
                                if (debugMode.value) {
                                    assistantMsg.status = 'pending_confirmation';
                                    assistantMsg.content = '任务已拆解，请编辑并确认清单。';
                                    awaitingTodoListConfirmation.value = true;
                                    chatRunning.value = false;
                                    saveCurrentSession();
                                    return;
                                }
                                await submitManagedChat(assistantMsg, targetDeviceIds, serverSessionId, serverMessageId,
                                    assistantMsg.todoList.map(item => ({content:item.content,timeout:subtaskTimeoutSeconds.value})), taskContent);
                            } else {
                                // 普通模式：直接执行任务
                                const runResult = await apiCall('/api/tasks/run', {
                                    method: 'POST',
                                    body: JSON.stringify({
                                        task_content: taskContent,
                                        device_ids: targetDeviceIds,
                                        send_email: chatAutoEmail.value,
                                        queue: true, acceptance:chatAcceptance.value||null,
                                        task_type: "chat",  // 标记为 chat 任务，避免日志出现在 Run Task 页面
                                        session_id: serverSessionId,  // 传递会话ID
                                        message_id: serverMessageId,  // 传递消息ID
                                        debug_mode: debugMode.value,  // 调试模式
                                    }),
                                });
                                // 保存任务ID用于匹配WebSocket事件
                                if (runResult && runResult.task_id) {
                                    assistantMsg.taskId = runResult.task_id;
                                }
                                // Task started, WebSocket will handle updates
                            }
                        } catch (error) {
                            // Update last message to error
                            const lastMsg = assistantMsg;
                            if (lastMsg.role === 'assistant') {
                                lastMsg.status = 'error';
                                let errorMsg = error.message || '未知错误';

                                // 提供更友好的错误提示
                                if (errorMsg.includes('Token error') || errorMsg.includes('limited')) {
                                    errorMsg = '❌ ' + errorMsg + '\n\n💡 提示：模型服务被限流，请稍后再试，或检查模型配置中的API额度。';
                                } else if (errorMsg.includes('Failed to parse todoList')) {
                                    errorMsg = '❌ 任务拆解失败：模型返回的格式不正确。\n\n💡 提示：请尝试将任务描述得更清晰，或切换到普通任务模式执行。';
                                }

                                lastMsg.content = '消息处理失败: ' + errorMsg;
                            }
                            chatRunning.value = false;
                        } finally {
                            contextMonitor.stop();
                            if (!isSlashCommand) void contextMonitor.refresh(serverSessionId);
                        }


                        // Save session after sending message
                        saveCurrentSession();
                    }

                    // Stop chat task
                    async function stopChatTask() {
                        try {
                            const active = [...chatMessages.value].reverse().find(m=>m.taskId && m.status==='running');
                            if (active) await apiCall(`/api/tasks/${active.taskId}/stop`, {method:'POST',body:'{}'});
                            showToast('正在停止任务...');
                            chatSegmentSequenceRunning.value = false;

                            // Update chat message status
                            if (chatMessages.value.length > 0) {
                                const lastMsg = chatMessages.value[chatMessages.value.length - 1];
                                if (lastMsg.role === 'assistant' && lastMsg.status === 'running') {
                                    lastMsg.status = 'error';
                                    lastMsg.content = '任务已停止';
                                }
                            }
                            chatRunning.value = false;
                            saveCurrentSession();
                        } catch (error) {
                            showToast('停止任务失败', 'error');
                        }
                    }

                    // Open task detail modal
                    async function openTaskDetail(msg) {
                        if(msg.taskId){await openIntegratedTask(msg.taskId);return;}

                        // 始终从服务器获取完整的截图和日志列表（WebSocket 可能只推送了部分数据，LocalStorage 可能有旧缓存）
                        let screenshots = [];
                        let logs = [];

                        // 如果存在 session_id 和 message_id，则从服务器获取完整数据
                        if (currentSessionId.value && msg.id) {
                            try {
                                // 获取截图
                                const screenshotData = await apiCall(
                                    `/api/chat/sessions/${currentSessionId.value}/screenshots?message_id=${msg.id}`
                                );
                                if (screenshotData && screenshotData.length > 0) {
                                    screenshots = screenshotData;
                                    // 更新消息对象中的 screenshots
                                    msg.screenshots = screenshots;
                                }
                            } catch (error) {
                                console.error('Failed to load screenshots:', error);
                                // 获取失败时使用本地缓存的数据
                                screenshots = msg.screenshots || [];
                            }

                            try {
                                // 获取日志
                                const logData = await apiCall(
                                    `/api/chat/sessions/${currentSessionId.value}/logs?message_id=${msg.id}`
                                );
                                if (logData && logData.length > 0) {
                                    // 提取日志内容
                                    logs = logData.map(log => log.content || log);
                                    // 更新消息对象中的 logs
                                    msg.logs = logs;
                                }
                            } catch (error) {
                                console.error('Failed to load logs:', error);
                                // 获取失败时使用本地缓存的数据
                                logs = msg.logs || [];
                            }
                        } else {
                            // 没有 session/message id，使用本地数据
                            screenshots = msg.screenshots || [];
                            logs = msg.logs || [];
                        }

                        // Smart log processing for ZhipuAI streaming output
                        // ZhipuAI sends each token as separate array element, causing fragmented display
                        function processLogs(logs) {
                            if (!logs || logs.length === 0) return [];

                            const result = [];
                            let buffer = '';  // Buffer for merging consecutive short tokens

                            for (let i = 0; i < logs.length; i++) {
                                const log = logs[i];

                                // If this is a short token (likely streaming output)
                                if (log.length <= 3) {
                                    buffer += log;
                                } else {
                                    // This is a complete log entry
                                    // First, flush any buffered content
                                    if (buffer.trim().length > 0) {
                                        result.push(buffer);
                                        buffer = '';
                                    }
                                    // Then add this complete entry
                                    result.push(log);
                                }
                            }

                            // Flush any remaining buffered content
                            if (buffer.trim().length > 0) {
                                result.push(buffer);
                            }

                            return result;
                        }

                        // Map database status to frontend status for display
                        // Database uses 'completed'/'failed', frontend uses 'success'/'error'
                        const displayStatus = msg.status === 'completed' ? 'success' :
                            (msg.status === 'failed' ? 'error' : msg.status);

                        taskDetailData.value = {
                            status: displayStatus,
                            logs: processLogs(logs),  // 使用从服务器获取的最新日志
                            screenshots: screenshots  // 使用从服务器获取的最新截图
                        };
                        showTaskDetail.value = true;
                    }

                    // Device functions (original)
                    async function refreshDevices({silent=false}={}) {
                        loading.value = true;
                        try {
                            const data = await apiCall('/api/devices/refresh', { method: 'POST' });
                            devices.value = data;
                            if(!silent)showToast(
                                data.length ? (currentLanguage.value==='zh'?`已找到 ${data.length} 台设备`:`Found ${data.length} device(s)`)
                                    : (currentLanguage.value==='zh'?'未检测到设备，请检查 USB 或无线连接':'No devices detected; check USB or wireless connection'),
                                data.length?'success':'warning');
                        } catch (e) {
                            console.error('Failed to refresh devices:', e);
                        } finally {
                            loading.value = false;
                        }
                    }

                    function toggleDeviceSelection(deviceId) {
                        const index = selectedDevices.value.indexOf(deviceId);
                        if (index === -1) {
                            selectedDevices.value.push(deviceId);
                        } else {
                            selectedDevices.value.splice(index, 1);
                        }
                    }

                    function selectAllDevices() {
                        if (selectedDevices.value.length === devices.value.length) {
                            selectedDevices.value = [];
                        } else {
                            selectedDevices.value = devices.value.map(d => d.id);
                        }
                    }

                    function getDeviceName(id) {
                        const device = devices.value.find(d => d.id === id);
                        return device ? (device.name || device.id.substring(0, 20)) : id.substring(0, 20);
                    }

                    async function unlockDevice(deviceId) {
                        try {
                            const pin = pinInputValues.value[deviceId] || '';
                            await apiCall(`/api/devices/${deviceId}/unlock`, {
                                method: 'POST',
                                body: JSON.stringify({ pin: pin }),
                            });
                            showToast('设备已解锁');
                        } catch (error) {
                            showToast('解锁失败', 'error');
                        }
                    }

                    async function lockDevice(deviceId) {
                        try {
                            await apiCall(`/api/devices/${deviceId}/lock`, {
                                method: 'POST',
                            });
                            showToast('设备已锁定');
                        } catch (error) {
                            showToast('锁定失败', 'error');
                        }
                    }

                    async function startCameraMonitor() {
                        if (!monitorDeviceId.value) {
                            showToast(currentLanguage.value === 'zh' ? '请先选择设备' : 'Please select a device', 'error');
                            return;
                        }
                        monitorStarting.value = true;
                        monitorMessage.value = '';
                        try {
                            const data = await apiCall(`/api/devices/${encodeURIComponent(monitorDeviceId.value)}/camera/start`, { method: 'POST' });
                            monitorSuccess.value = true;
                            monitorMessage.value = data.message || (currentLanguage.value === 'zh' ? '摄像头已启动' : 'Camera started');
                        } catch (error) {
                            monitorSuccess.value = false;
                            monitorMessage.value = error.message || (currentLanguage.value === 'zh' ? '启动失败' : 'Failed to start');
                        } finally {
                            monitorStarting.value = false;
                        }
                    }

                    function openMonitorPreview() {
                        if (!monitorDeviceId.value) return;
                        previewDeviceId.value = monitorDeviceId.value;
                        openIntegratedPreview(previewDeviceId.value);
                    }

                    const ipCamProxyUrl = Vue.computed(() => {
                        const u = ipCamStreamUrl.value && ipCamStreamUrl.value.trim();
                        if (!u) return '';
                        let url = '/api/camera/proxy?url=' + encodeURIComponent(u);
                        try {
                            const c = window._appConfig;
                            if (c && c.auth_enabled && c.token) url += '&api_key=' + encodeURIComponent(c.token);
                        } catch (e) { }
                        return url;
                    });

                    async function suggestIpCamUrl() {
                        if (!monitorDeviceId.value) return;
                        try {
                            const data = await apiCall('/api/devices/' + encodeURIComponent(monitorDeviceId.value) + '/camera/wlan-ip');
                            if (data && data.suggested_url) ipCamStreamUrl.value = data.suggested_url;
                            else if (data && data.ip) ipCamStreamUrl.value = 'http://' + data.ip + ':8080/videofeed';
                        } catch (e) {
                            if (monitorDeviceId.value.indexOf(':') !== -1) {
                                const ip = monitorDeviceId.value.split(':')[0];
                                ipCamStreamUrl.value = 'http://' + ip + ':8080/videofeed';
                            }
                        }
                    }

                    async function launchIpWebcamApp() {
                        if (!monitorDeviceId.value) return;
                        ipWebcamLaunching.value = true;
                        try {
                            const data = await apiCall('/api/devices/' + encodeURIComponent(monitorDeviceId.value) + '/camera/launch-ipwebcam', { method: 'POST' });
                            showToast(data.message || 'IP Webcam 已打开');
                        } catch (e) {
                            showToast(e.message || '启动失败', 'error');
                        } finally {
                            ipWebcamLaunching.value = false;
                        }
                    }

                    async function loadStreamConfig() {
                        try {
                            const data = await apiCall('/api/streams/config');
                            if (data && data.streams && Array.isArray(data.streams)) {
                                const list = data.streams;
                                const next = [];
                                for (let i = 0; i < 4; i++) next.push(list[i] ? { url: list[i].url || '', name: list[i].name || ('摄像头 ' + (i + 1)) } : { url: '', name: '摄像头 ' + (i + 1) });
                                streamConfig.value = next;
                            }
                        } catch (e) {
                            streamConfig.value = [{ url: '', name: '摄像头 1' }, { url: '', name: '摄像头 2' }, { url: '', name: '摄像头 3' }, { url: '', name: '摄像头 4' }];
                        }
                    }

                    async function saveStreamConfig() {
                        try {
                            await apiCall('/api/streams/config', { method: 'POST', body: JSON.stringify({ streams: streamConfig.value }) });
                            showToast(currentLanguage.value === 'zh' ? '已保存' : 'Saved');
                        } catch (e) {
                            showToast(e.message || '保存失败', 'error');
                        }
                    }

                    function streamMjpegUrl(index) {
                        let u = '/api/streams/' + index + '/mjpeg';
                        try {
                            const c = window._appConfig;
                            if (c && c.auth_enabled && c.token) u += '?api_key=' + encodeURIComponent(c.token);
                        } catch (e) { }
                        return u;
                    }

                    const hasAnyGridStream = Vue.computed(() => {
                        const c = streamConfig.value;
                        return c && c.some(s => s && (s.url || '').trim().length > 0);
                    });

                    function setGridImgRef(index, el) {
                        if (index >= 0 && index < 4) gridImgRefs.value[index] = el;
                    }

                    function drawGridToCanvas() {
                        const canvas = gridRecordCanvas.value;
                        if (!canvas || !gridRecording.value) return;
                        const ctx = canvas.getContext('2d');
                        if (!ctx) return;
                        const w = canvas.width;
                        const h = canvas.height;
                        const halfW = w / 2;
                        const halfH = h / 2;
                        ctx.fillStyle = '#111';
                        ctx.fillRect(0, 0, w, h);
                        const imgs = gridImgRefs.value || [];
                        for (let i = 0; i < 4; i++) {
                            const img = imgs[i];
                            if (!img || !img.complete || img.naturalWidth === 0) continue;
                            const sx = (i % 2) * halfW;
                            const sy = Math.floor(i / 2) * halfH;
                            ctx.drawImage(img, sx, sy, halfW, halfH);
                        }
                        gridRecordAnimationId = requestAnimationFrame(drawGridToCanvas);
                    }

                    function startGridRecord() {
                        const canvas = gridRecordCanvas.value;
                        if (!canvas || gridRecording.value) return;
                        const ctx = canvas.getContext('2d');
                        if (!ctx) return;
                        gridRecording.value = true;
                        gridRecordChunks = [];
                        try {
                            const stream = canvas.captureStream(15);
                            const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9') ? 'video/webm;codecs=vp9' : 'video/webm';
                            gridMediaRecorder = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 2500000 });
                            gridMediaRecorder.ondataavailable = (e) => { if (e.data && e.data.size > 0) gridRecordChunks.push(e.data); };
                            gridMediaRecorder.onstop = () => {
                                if (gridRecordChunks.length === 0) return;
                                const blob = new Blob(gridRecordChunks, { type: mime });
                                const url = URL.createObjectURL(blob);
                                const a = document.createElement('a');
                                a.href = url;
                                a.download = 'grid-record-' + new Date().toISOString().slice(0, 19).replace(/:/g, '-') + '.webm';
                                a.click();
                                URL.revokeObjectURL(url);
                            };
                            gridMediaRecorder.start(1000);
                            drawGridToCanvas();
                        } catch (e) {
                            gridRecording.value = false;
                            showToast(e.message || '录制失败', 'error');
                        }
                    }

                    function stopGridRecord() {
                        gridRecording.value = false;
                        if (gridRecordAnimationId != null) {
                            cancelAnimationFrame(gridRecordAnimationId);
                            gridRecordAnimationId = null;
                        }
                        if (gridMediaRecorder && gridMediaRecorder.state !== 'inactive') {
                            gridMediaRecorder.stop();
                            gridMediaRecorder = null;
                        }
                        showToast(currentLanguage.value === 'zh' ? '录制已停止，正在生成文件…' : 'Recording stopped, generating file…');
                    }

                    // Wireless pairing functions
                    async function wirelessPair() {
                        if (!pairAddress.value) {
                            showToast('请输入配对地址', 'error');
                            return;
                        }
                        if (!pairCode.value || pairCode.value.length !== 6) {
                            showToast('请输入6位配对码', 'error');
                            return;
                        }
                        pairingLoading.value = true;
                        deviceLogs.value = [];
                        try {
                            const data = await apiCall('/api/devices/pair', {
                                method: 'POST',
                                body: JSON.stringify({
                                    pair_address: pairAddress.value,
                                    pair_code: pairCode.value,
                                }),
                            });
                            deviceLogs.value = data.logs || [];
                            if (data.success) {
                                showToast(data.message, 'success');
                                pairCode.value = '';
                            } else {
                                showToast(data.message, 'error');
                            }
                        } catch (error) {
                            showToast('配对失败: ' + error.message, 'error');
                        } finally {
                            pairingLoading.value = false;
                        }
                    }

                    async function tcpConnect() {
                        if (!connectAddress.value) {
                            showToast('请输入连接地址', 'error');
                            return;
                        }
                        connectingLoading.value = true;
                        deviceLogs.value = [];
                        try {
                            const data = await apiCall('/api/devices/connect', {
                                method: 'POST',
                                body: JSON.stringify({
                                    connect_address: connectAddress.value,
                                }),
                            });
                            deviceLogs.value = data.logs || [];
                            if (data.success) {
                                showToast(data.message, 'success');
                                await refreshDevices();
                            } else {
                                showToast(data.message, 'error');
                            }
                        } catch (error) {
                            showToast('连接失败: ' + error.message, 'error');
                        } finally {
                            connectingLoading.value = false;
                        }
                    }

                    async function disconnectDevice(deviceId) {
                        try {
                            const data = await apiCall(`/api/devices/disconnect/${deviceId}`, {
                                method: 'POST',
                            });
                            if (data.success) {
                                showToast('设备已断开');
                                await refreshDevices();
                            } else {
                                showToast(data.message, 'error');
                            }
                        } catch (error) {
                            showToast('断开失败', 'error');
                        }
                    }

                    // APK install functions
                    function onApkFileSelect(event) {
                        const file = event.target.files[0];
                        if (file && file.name.toLowerCase().endsWith('.apk')) {
                            apkFile.value = file;
                            apkLogs.value = [];
                        } else {
                            apkFile.value = null;
                            showToast('请选择 APK 文件', 'error');
                        }
                    }

                    async function installApk() {
                        if (!apkTargetDevice.value) {
                            showToast('请选择目标设备', 'error');
                            return;
                        }
                        if (!apkFile.value) {
                            showToast('请选择 APK 文件', 'error');
                            return;
                        }

                        apkInstalling.value = true;
                        apkLogs.value = ['准备上传 APK 文件...'];

                        try {
                            const formData = new FormData();
                            formData.append('file', apkFile.value);

                            apkLogs.value.push(`上传中: ${apkFile.value.name}`);

                            const response = await fetch(`/api/devices/${apkTargetDevice.value}/install-apk`, {
                                method: 'POST',
                                body: formData,
                            });

                            const data = await response.json();
                            apkLogs.value = data.logs || [];

                            if (data.success) {
                                showToast(data.message, 'success');
                                // Clear file input
                                apkFile.value = null;
                                if (apkFileInput.value) {
                                    apkFileInput.value.value = '';
                                }
                            } else {
                                showToast(data.message, 'error');
                            }
                        } catch (error) {
                            apkLogs.value.push(`❌ 安装失败: ${error.message}`);
                            showToast('APK 安装失败', 'error');
                        } finally {
                            apkInstalling.value = false;
                        }
                    }

                    // File manager functions
                    async function loadFiles() {
                        if (!fileDevice.value) return;
                        fileLoading.value = true;
                        try {
                            const data = await apiCall(`/api/devices/${fileDevice.value}/files?path=${encodeURIComponent(filePath.value)}`);
                            fileList.value = data.files || [];
                        } catch (error) {
                            showToast('加载文件列表失败: ' + error.message, 'error');
                            fileList.value = [];
                        } finally {
                            fileLoading.value = false;
                        }
                    }

                    function navigateTo(path) {
                        // Normalize path
                        path = path.replace(/\/+/g, '/');
                        if (path !== '/' && path.endsWith('/')) {
                            path = path.slice(0, -1);
                        }
                        filePath.value = path;
                        loadFiles();
                    }

                    function goUp() {
                        const parts = filePath.value.split('/').filter(p => p);
                        if (parts.length > 0) {
                            parts.pop();
                            filePath.value = '/' + parts.join('/');
                            loadFiles();
                        }
                    }

                    function formatFileSize(size) {
                        const num = parseInt(size);
                        if (isNaN(num)) return size;
                        if (num < 1024) return num + ' B';
                        if (num < 1024 * 1024) return (num / 1024).toFixed(1) + ' KB';
                        if (num < 1024 * 1024 * 1024) return (num / 1024 / 1024).toFixed(1) + ' MB';
                        return (num / 1024 / 1024 / 1024).toFixed(1) + ' GB';
                    }

                    function isImageFile(name) {
                        return /\.(jpg|jpeg|png|gif|bmp|webp)$/i.test(name);
                    }

                    function isVideoFile(name) {
                        return /\.(mp4|mkv|avi|mov|wmv|flv|webm)$/i.test(name);
                    }

                    function isAudioFile(name) {
                        return /\.(mp3|wav|flac|aac|ogg|m4a)$/i.test(name);
                    }

                    async function downloadFile(filename) {
                        const fullPath = filePath.value + '/' + filename;
                        try {
                            const response = await fetch(`/api/devices/${fileDevice.value}/files/download?path=${encodeURIComponent(fullPath)}`);
                            if (!response.ok) {
                                let message = `HTTP ${response.status}`;
                                try {
                                    const data = await response.json();
                                    if (typeof data.detail === 'string' && data.detail.trim()) {
                                        message = data.detail;
                                    }
                                } catch (_) {
                                    // Proxy/server errors may return HTML instead of JSON.
                                }
                                throw new Error(message);
                            }
                            const blob = await response.blob();
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = filename;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                            // Give the browser time to start reading the download.
                            setTimeout(() => URL.revokeObjectURL(url), 60000);
                            showToast('下载成功');
                        } catch (error) {
                            const message = error.message.replace(/^下载失败\s*[:：]\s*/, '');
                            showToast('下载失败: ' + message, 'error');
                        }
                    }

                    function onUploadFileSelect(event) {
                        uploadSelectedFile.value = event.target.files[0] || null;
                    }

                    async function uploadFile() {
                        if (!uploadSelectedFile.value || !fileDevice.value) return;
                        fileUploading.value = true;
                        try {
                            const formData = new FormData();
                            formData.append('file', uploadSelectedFile.value);
                            formData.append('path', filePath.value);

                            const response = await fetch(`/api/devices/${fileDevice.value}/files/upload`, {
                                method: 'POST',
                                body: formData,
                            });
                            const data = await response.json();

                            if (data.success) {
                                showToast('上传成功');
                                uploadSelectedFile.value = null;
                                if (uploadFileInput.value) uploadFileInput.value.value = '';
                                await loadFiles();
                            } else {
                                showToast(data.message, 'error');
                            }
                        } catch (error) {
                            showToast('上传失败: ' + error.message, 'error');
                        } finally {
                            fileUploading.value = false;
                        }
                    }

                    async function deleteFileConfirm(filename, isDir) {
                        const type = isDir ? '文件夹' : '文件';
                        if (!confirm(`确定要删除${type} "${filename}" 吗？`)) return;

                        const fullPath = filePath.value + '/' + filename;
                        try {
                            const data = await apiCall(`/api/devices/${fileDevice.value}/files?path=${encodeURIComponent(fullPath)}`, {
                                method: 'DELETE',
                            });
                            if (data.success) {
                                showToast('删除成功');
                                await loadFiles();
                            } else {
                                showToast(data.message, 'error');
                            }
                        } catch (error) {
                            showToast('删除失败: ' + error.message, 'error');
                        }
                    }

                    // PIN management functions
                    async function loadDevicePins() {
                        try {
                            const data = await apiCall('/api/devices/pins');
                            devicePins.value = data.pins || {};
                            // Load actual PIN values for display
                            for (const deviceId of Object.keys(devicePins.value)) {
                                try {
                                    const pinData = await apiCall(`/api/devices/${deviceId}/pin`);
                                    if (pinData.pin) {
                                        pinInputValues.value[deviceId] = pinData.pin;
                                    }
                                } catch (e) {
                                    // Ignore errors for individual PIN fetch
                                }
                            }
                        } catch (error) {
                            console.error('Failed to load device PINs:', error);
                        }
                    }

                    function updateDevicePin(deviceId, pin) {
                        pinInputValues.value[deviceId] = pin;
                        devicePins.value[deviceId] = pin ? true : false;
                    }

                    function toggleShowPin(deviceId) {
                        if (showPinFor.value === deviceId) {
                            showPinFor.value = '';
                        } else {
                            showPinFor.value = deviceId;
                        }
                    }

                    async function saveDevicePin(deviceId, pin) {
                        if (!pin) return;
                        try {
                            await apiCall(`/api/devices/${deviceId}/pin`, {
                                method: 'PUT',
                                body: JSON.stringify({ pin: pin }),
                            });
                            showToast('PIN saved');
                        } catch (error) {
                            showToast('Failed to save PIN', 'error');
                        }
                    }

                    // Auto-scroll log container
                    function scrollLogsToBottom() {
                        if (logContainer.value) {
                            logContainer.value.scrollTop = logContainer.value.scrollHeight;
                        }
                    }

                    // Task functions
                    async function runTask() {
                        if (!taskContent.value.trim()) {
                            showToast('Please enter a task', 'warning');
                            return;
                        }
                        if (selectedDevices.value.length === 0) {
                            showToast('Please select at least one device', 'warning');
                            return;
                        }

                        taskLogs.value = [];
                        taskProgress.value = 0;
                        taskScreenshot.value = '';

                        try {
                            const result = await apiCall('/api/tasks/run', {
                                method: 'POST',
                                body: JSON.stringify({
                                    task_content: taskContent.value,
                                    device_ids: selectedDevices.value,
                                    parallel: parallelExecution.value, queue:true, acceptance:taskAcceptance.value||null,
                                }),
                            });
                            activeRunTaskId.value=result.task_id;
                            taskRunning.value = true;
                            await automation.refresh();
                            showToast('Task started');
                        } catch (error) {
                            showToast('Failed to start task', 'error');
                        }
                    }

                    async function stopTask() {
                        try {
                            if(activeRunTaskId.value)await apiCall(`/api/tasks/${activeRunTaskId.value}/stop`,{method:'POST',body:'{}'});
                            showToast('Stop signal sent');
                        } catch (error) {
                            showToast('Failed to stop task', 'error');
                        }
                    }

                    // Scheduler functions
                    async function loadScheduledTasks() {
                        try {
                            const data = await apiCall('/api/scheduler/tasks');
                            scheduledTasks.value = data.tasks;
                        } catch (error) {
                            console.error('Failed to load scheduled tasks:', error);
                        }
                    }

                    async function toggleScheduledTask(taskId, enabled) {
                        try {
                            await apiCall(`/api/scheduler/tasks/${taskId}/toggle`, {
                                method: 'PATCH',
                                body: JSON.stringify({ enabled }),
                            });
                            await loadScheduledTasks();
                        } catch (error) {
                            showToast('Failed to toggle task', 'error');
                        }
                    }

                    async function runScheduledTaskNow(taskId) {
                        try {
                            await apiCall(`/api/scheduler/tasks/${taskId}/run`, { method: 'POST' });
                            showToast('Task triggered');
                        } catch (error) {
                            showToast('Failed to run task', 'error');
                        }
                    }

                    async function deleteScheduledTask(taskId) {
                        if (!confirm('Are you sure you want to delete this task?')) return;
                        try {
                            await apiCall(`/api/scheduler/tasks/${taskId}`, { method: 'DELETE' });
                            await loadScheduledTasks();
                            showToast('Task deleted');
                        } catch (error) {
                            showToast('Failed to delete task', 'error');
                        }
                    }

                    // Scheduler form functions
                    function showCreateScheduledTask() {
                        schedulerForm.value = getDefaultSchedulerForm();
                        schedulerFormMode.value = 'create';
                        schedulerForm.value.timezone=automation.settings?.timezone||'';
                        showSchedulerForm.value = true;
                    }

                    function editScheduledTask(task) {
                        schedulerForm.value = {
                            id: task.id,
                            name: task.name,
                            task_content: task.task_content,
                            enabled: task.enabled,
                            schedule_type: task.schedule_type,
                            run_at: task.run_at || '',
                            interval_minutes: task.interval_minutes || 60,
                            daily_time: task.daily_time || '09:00',
                            weekly_days: task.weekly_days || [1],
                            weekly_time: task.weekly_time || '09:00',
                            monthly_day: task.monthly_day || 1,
                            monthly_time: task.monthly_time || '09:00',
                            devices: task.devices || [],
                            recipe_id:task.recipe_id||'',recipe_revision:task.recipe_revision||null,
                            recipe_parameters:JSON.parse(JSON.stringify(task.recipe_parameters||{})),
                            busy_policy:task.busy_policy||'queue',timezone:task.timezone||automation.settings?.timezone||'',
                        };
                        schedulerFormMode.value = 'edit';
                        showSchedulerForm.value = true;
                    }

                    function cancelSchedulerForm() {
                        showSchedulerForm.value = false;
                        schedulerForm.value = getDefaultSchedulerForm();
                    }

                    async function saveScheduledTask() {
                        if (!schedulerForm.value.name.trim()) {
                            showToast('Please enter a task name', 'warning');
                            return;
                        }
                        if (!schedulerForm.value.task_content.trim()) {
                            showToast('Please enter task content', 'warning');
                            return;
                        }

                        loading.value = true;
                        try {
                            if (schedulerFormMode.value === 'create') {
                                await apiCall('/api/scheduler/tasks', {
                                    method: 'POST',
                                    body: JSON.stringify(schedulerForm.value),
                                });
                                showToast('Task created');
                            } else {
                                await apiCall(`/api/scheduler/tasks/${schedulerForm.value.id}`, {
                                    method: 'PUT',
                                    body: JSON.stringify(schedulerForm.value),
                                });
                                showToast('Task updated');
                            }
                            await loadScheduledTasks();
                            cancelSchedulerForm();
                        } catch (error) {
                            showToast('Failed to save task', 'error');
                        } finally {
                            loading.value = false;
                        }
                    }

                    function formatScheduleType(task) {
                        switch (task.schedule_type) {
                            case 'once': return `Once: ${task.run_at}`;
                            case 'interval': return `Every ${task.interval_minutes} min`;
                            case 'daily': return `Daily @ ${task.daily_time}`;
                            case 'weekly': return `Weekly @ ${task.weekly_time}`;
                            case 'monthly': return `Monthly day ${task.monthly_day} @ ${task.monthly_time}`;
                            default: return task.schedule_type;
                        }
                    }

                    // Scheduler logs functions
                    async function loadSchedulerLogs() {
                        try {
                            const data = await apiCall('/api/scheduler/logs?limit=50');
                            schedulerLogs.value = data.logs || [];
                        } catch (error) {
                            console.error('Failed to load scheduler logs:', error);
                        }
                    }

                    async function clearAllSchedulerLogs() {
                        if (!confirm('确定要清空所有定时任务的执行日志吗？')) return;
                        try {
                            await apiCall('/api/scheduler/logs', { method: 'DELETE' });
                            showToast('所有日志已清空');
                            schedulerLogs.value = [];
                        } catch (error) {
                            showToast('清空日志失败: ' + error.message, 'error');
                        }
                    }

                    function formatLogTime(timestamp) {
                        if (!timestamp) return '-';
                        const date = new Date(timestamp);
                        const now = new Date();
                        const isToday = date.toDateString() === now.toDateString();
                        if (isToday) {
                            return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                        }
                        return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
                    }

                    function showLogDetails(log) {
                        // Process details if it's an array (handle ZhipuAI streaming tokens)
                        const processedLog = { ...log };

                        try {
                            if (Array.isArray(log.details)) {
                                // Apply same smart processing as taskDetailData
                                const processLogs = (logs) => {
                                    if (!logs || logs.length === 0) return '';

                                    const result = [];
                                    let buffer = '';

                                    for (let i = 0; i < logs.length; i++) {
                                        const logItem = logs[i];
                                        // Ensure logItem is a string
                                        const itemStr = String(logItem || '');

                                        if (itemStr.length <= 3) {
                                            buffer += itemStr;
                                        } else {
                                            if (buffer.trim().length > 0) {
                                                result.push(buffer);
                                                buffer = '';
                                            }
                                            result.push(itemStr);
                                        }
                                    }

                                    if (buffer.trim().length > 0) {
                                        result.push(buffer);
                                    }

                                    return result.join('\n');
                                };

                                processedLog.details = processLogs(log.details);
                            } else if (typeof log.details === 'string') {
                                // Already a string, use as-is
                                processedLog.details = log.details;
                            } else {
                                // Unexpected type, convert to string
                                processedLog.details = String(log.details || '无详细日志');
                            }
                        } catch (error) {
                            console.error('Error processing log details:', error);
                            // Fallback: use original details or JSON stringify
                            if (Array.isArray(log.details)) {
                                processedLog.details = log.details.join('\n');
                            } else {
                                processedLog.details = String(log.details || '处理日志时出错');
                            }
                        }

                        logDetailData.value = processedLog;
                        showLogDetailModal.value = true;
                    }

                    async function clearTaskLogs(taskId) {
                        if (!confirm('确定要清除该任务的所有日志吗？')) return;
                        try {
                            await apiCall(`/api/scheduler/tasks/${taskId}/logs`, { method: 'DELETE' });
                            showToast('日志已清除');
                            await loadSchedulerLogs();
                        } catch (error) {
                            showToast('清除日志失败', 'error');
                        }
                    }

                    // Model functions
                    async function loadModels() {
                        try {
                            const data = await apiCall('/api/models');
                            modelServices.value = data.services;
                            const active = modelServices.value.find(s => s.is_active);
                            activeModel.value = active || null;
                        } catch (error) {
                            console.error('Failed to load models:', error);
                        }
                    }

                    async function activateModel(serviceId) {
                        try {
                            await apiCall(`/api/models/${serviceId}/activate`, { method: 'POST' });
                            await loadModels();
                            showToast('Model activated');
                        } catch (error) {
                            showToast('Failed to activate model', 'error');
                        }
                    }

                    async function testModel(serviceId) {
                        loading.value = true;
                        try {
                            const data = await apiCall(`/api/models/${serviceId}/test`, { method: 'POST' });
                            showToast(data.message, data.success ? 'success' : 'error');
                        } finally {
                            loading.value = false;
                        }
                    }

                    // Model CRUD functions
                    async function loadModelPresets() {
                        try {
                            const data = await apiCall('/api/models/presets');
                            modelPresets.value = data.presets || [];
                        } catch (error) {
                            console.error('Failed to load model presets:', error);
                        }
                    }

                    function openModelForm(mode, service = null) {
                        modelFormMode.value = mode;
                        if (mode === 'edit' && service) {
                            modelForm.value = { ...service };
                        } else {
                            modelForm.value = getDefaultModelForm();
                        }
                        showModelForm.value = true;
                    }

                    async function saveModel() {
                        if (!modelForm.value.name || !modelForm.value.base_url || !modelForm.value.model_name) {
                            showToast('请填写必填字段（名称、Base URL、模型名称）', 'error');
                            return;
                        }
                        loading.value = true;
                        try {
                            if (modelFormMode.value === 'create') {
                                await apiCall('/api/models', {
                                    method: 'POST',
                                    body: JSON.stringify(modelForm.value),
                                });
                                showToast('模型服务创建成功');
                            } else {
                                await apiCall(`/api/models/${modelForm.value.id}`, {
                                    method: 'PUT',
                                    body: JSON.stringify(modelForm.value),
                                });
                                showToast('模型服务更新成功');
                            }
                            showModelForm.value = false;
                            await loadModels();
                        } catch (error) {
                            showToast('保存失败: ' + error.message, 'error');
                        } finally {
                            loading.value = false;
                        }
                    }

                    async function deleteModel(serviceId, serviceName) {
                        if (!confirm(`确定要删除模型服务 "${serviceName}" 吗？`)) {
                            return;
                        }
                        try {
                            await apiCall(`/api/models/${serviceId}`, { method: 'DELETE' });
                            showToast('模型服务已删除');
                            await loadModels();
                        } catch (error) {
                            showToast('删除失败: ' + error.message, 'error');
                        }
                    }

                    async function testModelConfig() {
                        if (!modelForm.value.base_url || !modelForm.value.model_name) {
                            showToast('请填写 Base URL 和模型名称', 'error');
                            return;
                        }
                        loading.value = true;
                        try {
                            const data = await apiCall('/api/models/test', {
                                method: 'POST',
                                body: JSON.stringify({
                                    base_url: modelForm.value.base_url,
                                    api_key: modelForm.value.api_key,
                                    model_name: modelForm.value.model_name,
                                    protocol: modelForm.value.protocol || 'openai',
                                }),
                            });
                            showToast(data.message, data.success ? 'success' : 'error');
                        } catch (error) {
                            showToast('测试失败: ' + error.message, 'error');
                        } finally {
                            loading.value = false;
                        }
                    }

                    function addFromPreset(preset) {
                        modelForm.value = {
                            ...getDefaultModelForm(),
                            name: preset.name,
                            base_url: preset.base_url,
                            model_name: preset.model_name,
                            description: preset.description || '',
                            max_tokens: preset.max_tokens || 3000,
                            context_window: preset.context_window || 0,
                            temperature: preset.temperature || 0.0,
                            protocol: preset.protocol || 'openai',
                            category: preset.category || '',
                        };
                        modelFormMode.value = 'create';
                        showModelForm.value = true;
                    }

                    // 按分类获取预设模板
                    function getPresetsByCategory(category) {
                        return modelPresets.value.filter(p => p.category === category);
                    }

                    // Settings functions
                    async function loadEmailConfig() {
                        try {
                            emailConfig.value = await apiCall('/api/settings/email');
                        } catch (error) {
                            console.error('Failed to load email config:', error);
                        }
                    }

                    async function saveEmailConfig() {
                        try {
                            await apiCall('/api/settings/email', {
                                method: 'PUT',
                                body: JSON.stringify(emailConfig.value),
                            });
                            showToast('Email settings saved');
                        } catch (error) {
                            showToast('Failed to save email settings', 'error');
                        }
                    }

                    async function testEmail() {
                        loading.value = true;
                        try {
                            const data = await apiCall('/api/settings/email/test', { method: 'POST' });
                            showToast(data.message, data.success ? 'success' : 'error');
                        } finally {
                            loading.value = false;
                        }
                    }

                    // Screenshot configuration
                    async function saveScreenshotConfig() {
                        loading.value = true;
                        try {
                            await apiCall('/api/settings/screenshot', {
                                method: 'PUT',
                                body: JSON.stringify({
                                    max_image_dimension: screenshotConfig.value.max_dimension,
                                    jpeg_quality: screenshotConfig.value.jpeg_quality
                                })
                            });
                            showToast('Screenshot settings saved successfully!', 'success');
                        } catch (error) {
                            console.error('Failed to save screenshot settings:', error);
                            showToast('Failed to save screenshot settings', 'error');
                        } finally {
                            loading.value = false;
                        }
                    }

                    async function loadScreenshotConfig() {
                        try {
                            const data = await apiCall('/api/settings/screenshot');
                            screenshotConfig.value = {
                                max_dimension: data.max_image_dimension,
                                jpeg_quality: data.jpeg_quality
                            };
                        } catch (error) {
                            console.error('Failed to load screenshot settings:', error);
                        }
                    }

                    async function resetScreenshotConfig() {
                        screenshotConfig.value = {
                            max_dimension: 1920,
                            jpeg_quality: 70
                        };
                        showToast('已恢复默认设置');
                    }

                    // Telegram Bot functions
                    async function loadTelegramConfig() {
                        try {
                            const data = await apiCall('/api/telegram/config');
                            telegramConfig.value = {
                                bot_token: data.bot_token || '',
                                enabled: data.enabled || false,
                                allowed_users: data.allowed_users || [],
                                send_screenshots: data.send_screenshots !== undefined ? data.send_screenshots : true,
                                send_logs: data.send_logs !== undefined ? data.send_logs : true,
                                status: data.status || 'stopped'
                            };
                            telegramAllowedUsersStr.value = data.allowed_users.join(', ');
                        } catch (error) {
                            console.error('Failed to load Telegram config:', error);
                        }
                    }

                    async function saveTelegramConfig() {
                        loading.value = true;
                        try {
                            // Parse allowed users
                            const allowedUsers = telegramAllowedUsersStr.value
                                .split(',')
                                .map(s => s.trim())
                                .filter(s => s && !isNaN(s))
                                .map(s => parseInt(s));

                            await apiCall('/api/telegram/config', {
                                method: 'POST',
                                body: JSON.stringify({
                                    bot_token: telegramConfig.value.bot_token,
                                    enabled: telegramConfig.value.enabled,
                                    allowed_users: allowedUsers,
                                    send_screenshots: telegramConfig.value.send_screenshots,
                                    send_logs: telegramConfig.value.send_logs
                                })
                            });

                            await loadTelegramConfig();
                            showToast('Telegram 配置已保存');
                        } catch (error) {
                            showToast('保存失败: ' + error.message, 'error');
                        } finally {
                            loading.value = false;
                        }
                    }

                    async function testTelegramConnection() {
                        loading.value = true;
                        try {
                            const response = await apiCall('/api/telegram/test', {
                                method: 'POST',
                                body: JSON.stringify({
                                    bot_token: telegramConfig.value.bot_token
                                })
                            });

                            telegramBotInfo.value = response.bot_info;
                            showToast('✅ 连接成功！');
                        } catch (error) {
                            showToast('❌ 连接失败: ' + error.message, 'error');
                            telegramBotInfo.value = null;
                        } finally {
                            loading.value = false;
                        }
                    }

                    async function startTelegramBot() {
                        loading.value = true;
                        try {
                            await apiCall('/api/telegram/start', { method: 'POST' });
                            await loadTelegramConfig();
                            showToast('✅ Telegram Bot 已启动');
                        } catch (error) {
                            showToast('❌ 启动失败: ' + error.message, 'error');
                        } finally {
                            loading.value = false;
                        }
                    }

                    async function stopTelegramBot() {
                        loading.value = true;
                        try {
                            await apiCall('/api/telegram/stop', { method: 'POST' });
                            await loadTelegramConfig();
                            showToast('Telegram Bot 已停止');
                        } catch (error) {
                            showToast('❌ 停止失败: ' + error.message, 'error');
                        } finally {
                            loading.value = false;
                        }
                    }

                    // Rules configuration functions
                    async function loadAppMappings() {
                        try {
                            const data = await apiCall('/api/rules/apps');
                            appMappings.value = data.apps || [];
                        } catch (error) {
                            console.error('Failed to load app mappings:', error);
                        }
                    }

                    async function loadTimingConfig() {
                        try {
                            timingConfig.value = await apiCall('/api/rules/timing');
                        } catch (error) {
                            console.error('Failed to load timing config:', error);
                        }
                    }

                    async function loadSystemPrompts() {
                        try {
                            const data = await apiCall('/api/rules/prompts');
                            systemPrompts.value = data.prompts || {};
                        } catch (error) {
                            console.error('Failed to load prompts:', error);
                        }
                    }

                    function formatTimingKey(key) {
                        return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                    }

                    async function updateTiming(category, key, value) {
                        try {
                            await apiCall('/api/rules/timing', {
                                method: 'PUT',
                                body: JSON.stringify({ category, key, value: parseFloat(value) }),
                            });
                            showToast('时间配置已更新');
                        } catch (error) {
                            showToast('更新失败', 'error');
                            loadTimingConfig(); // Reload on error
                        }
                    }

                    function editAppMapping(app) {
                        editingApp.value = app;
                        appForm.value = { app_name: app.app_name, package_name: app.package_name };
                        showAddAppModal.value = true;
                    }

                    async function saveAppMapping() {
                        if (!appForm.value.app_name || !appForm.value.package_name) {
                            showToast('请填写完整信息', 'error');
                            return;
                        }
                        try {
                            if (editingApp.value) {
                                await apiCall(`/api/rules/apps/${encodeURIComponent(editingApp.value.app_name)}`, {
                                    method: 'PUT',
                                    body: JSON.stringify({
                                        new_name: appForm.value.app_name,
                                        package_name: appForm.value.package_name,
                                    }),
                                });
                                showToast('应用映射已更新');
                            } else {
                                await apiCall('/api/rules/apps', {
                                    method: 'POST',
                                    body: JSON.stringify(appForm.value),
                                });
                                showToast('应用映射已添加');
                            }
                            showAddAppModal.value = false;
                            editingApp.value = null;
                            appForm.value = { app_name: '', package_name: '' };
                            await loadAppMappings();
                        } catch (error) {
                            showToast(error.message || '操作失败', 'error');
                        }
                    }

                    async function deleteAppMapping(appName) {
                        if (!confirm(`确定删除应用映射「${appName}」吗？`)) return;
                        try {
                            await apiCall(`/api/rules/apps/${encodeURIComponent(appName)}`, { method: 'DELETE' });
                            showToast('应用映射已删除');
                            await loadAppMappings();
                        } catch (error) {
                            showToast('删除失败', 'error');
                        }
                    }

                    async function savePrompt(key, content) {
                        try {
                            await apiCall(`/api/rules/prompts/${key}`, {
                                method: 'PUT',
                                body: JSON.stringify({ content }),
                            });
                            showToast('提示词已保存');
                        } catch (error) {
                            showToast('保存失败', 'error');
                        }
                    }

                    async function resetPrompt(key) {
                        if (!confirm('确定重置为默认提示词吗？')) return;
                        try {
                            await apiCall(`/api/rules/prompts/${key}/reset`, { method: 'POST' });
                            showToast('提示词已重置');
                            await loadSystemPrompts();
                        } catch (error) {
                            showToast('重置失败', 'error');
                        }
                    }

                    // Action rules functions
                    async function loadActionRules() {
                        try {
                            const data = await apiCall('/api/rules/actions');
                            actionRules.value = data.actions || [];
                        } catch (error) {
                            console.error('Failed to load action rules:', error);
                        }
                    }

                    function toggleActionExpand(actionName) {
                        expandedActions.value[actionName] = !expandedActions.value[actionName];
                    }

                    async function toggleRuleEnabled(actionName, ruleId) {
                        try {
                            await apiCall(`/api/rules/actions/${encodeURIComponent(actionName)}/rules/${ruleId}/toggle`, { method: 'PUT' });
                            await loadActionRules();
                        } catch (error) {
                            showToast('操作失败', 'error');
                        }
                    }

                    function showAddRuleModal(actionName) {
                        editingRuleAction.value = actionName;
                        editingRule.value = null;
                        ruleForm.value = { condition: '', action: '', priority: 0, enabled: true };
                        showRuleModal.value = true;
                    }

                    function editRuleItem(actionName, rule) {
                        editingRuleAction.value = actionName;
                        editingRule.value = rule;
                        ruleForm.value = {
                            condition: rule.condition,
                            action: rule.action,
                            priority: rule.priority || 0,
                            enabled: rule.enabled
                        };
                        showRuleModal.value = true;
                    }

                    async function saveRuleItem() {
                        if (!ruleForm.value.condition || !ruleForm.value.action) {
                            showToast('请填写完整信息', 'error');
                            return;
                        }
                        try {
                            if (editingRule.value) {
                                // Update existing rule
                                await apiCall(`/api/rules/actions/${encodeURIComponent(editingRuleAction.value)}/rules/${editingRule.value.id}`, {
                                    method: 'PUT',
                                    body: JSON.stringify(ruleForm.value),
                                });
                                showToast('规则已更新');
                            } else {
                                // Add new rule
                                await apiCall(`/api/rules/actions/${encodeURIComponent(editingRuleAction.value)}/rules`, {
                                    method: 'POST',
                                    body: JSON.stringify(ruleForm.value),
                                });
                                showToast('规则已添加');
                            }
                            showRuleModal.value = false;
                            await loadActionRules();
                        } catch (error) {
                            showToast(error.message || '操作失败', 'error');
                        }
                    }

                    async function deleteRuleItem(actionName, ruleId) {
                        if (!confirm('确定删除此规则吗？')) return;
                        try {
                            await apiCall(`/api/rules/actions/${encodeURIComponent(actionName)}/rules/${ruleId}`, { method: 'DELETE' });
                            showToast('规则已删除');
                            await loadActionRules();
                        } catch (error) {
                            showToast('删除失败', 'error');
                        }
                    }

                    async function resetActionRules() {
                        if (!confirm('确定重置所有动作规则为默认值吗？')) return;
                        try {
                            await apiCall('/api/rules/actions/reset', { method: 'POST' });
                            showToast('动作规则已重置');
                            await loadActionRules();
                        } catch (error) {
                            showToast('重置失败', 'error');
                        }
                    }

                    // Phone Preview Functions
                    const phonePreviewStyle = Vue.computed(() => ({
                        left: previewPosition.value.x + 'px',
                        top: previewPosition.value.y + 'px',
                        width: previewWidth.value + 'px',
                        height: Math.round(previewWidth.value * previewAspect.value) + 'px',
                    }));

                    const previewToolsOnRight=Vue.computed(()=>previewPosition.value.x<300);
                    const previewIsLandscape = Vue.computed(() => {
                        if(previewMode.value==='replay')return previewAspect.value<1;
                        if (canvasWidth.value > 0 && canvasHeight.value > 0) {
                            return canvasWidth.value > canvasHeight.value;
                        }
                        return (previewAspect.value || (16 / 9)) < 1;
                    });

                    function getPreviewToolbarWidthReserve() {
                        return previewIsLandscape.value ? 0 : PREVIEW_TOOLBAR_WIDTH;
                    }

                    function getPreviewToolbarHeightReserve() {
                        return previewIsLandscape.value ? PREVIEW_TOOLBAR_HEIGHT_LANDSCAPE : 0;
                    }

                    function maybeResizePreviewOnAspectSwitch(nextAspect) {
                        const currentAspect = Math.max(0.2, Number(previewAspect.value) || (16 / 9));
                        const targetAspect = Math.max(0.2, Number(nextAspect) || currentAspect);
                        const currentLandscape = currentAspect < 1;
                        const nextLandscape = targetAspect < 1;
                        if (currentLandscape === nextLandscape) return;

                        const currentW = Math.max(120, Number(previewWidth.value) || 270);
                        const currentH = currentW * currentAspect;
                        let nextW = nextLandscape
                            ? (currentH / targetAspect)   // Landscape: keep visual height, avoid tiny window
                            : currentW;                  // Portrait: keep current width, then clamp to viewport
                        if (!Number.isFinite(nextW) || nextW <= 0) return;
                        const { minAllowed, maxAllowed } = getPreviewWidthRange(
                            previewPosition.value.x,
                            previewPosition.value.y
                        );
                        nextW = Math.max(minAllowed, Math.min(maxAllowed, nextW));
                        previewWidth.value = Math.round(nextW);
                    }

                    function pickDefaultStreamSizeByLongEdge(longEdge) {
                        if (longEdge >= 1080) return 1080;
                        if (longEdge >= 960) return 960;
                        if (longEdge >= 720) return 720;
                        return 540;
                    }

                    function getDeviceById(deviceId) {
                        if (!deviceId) return null;
                        return devices.value.find((d) => d.id === deviceId) || null;
                    }

                    function isEmulatorDevice(deviceId) {
                        const dev = getDeviceById(deviceId);
                        const idText = String(deviceId || '').toLowerCase();
                        const nameText = String(dev?.name || '').toLowerCase();
                        return (
                            idText.startsWith('emulator-')
                            || idText.includes('sdk_gphone')
                            || nameText.includes('sdk_gphone')
                            || nameText.includes('emulator')
                            || nameText.includes('android sdk built for')
                        );
                    }

                    function decodePngBase64Dimensions(imageBase64) {
                        return new Promise((resolve, reject) => {
                            const img = new window.Image();
                            img.onload = () => resolve({ width: img.width, height: img.height });
                            img.onerror = () => reject(new Error('decode screenshot size failed'));
                            img.src = 'data:image/png;base64,' + imageBase64;
                        });
                    }

                    async function refreshPreview(options = {}) {
                        if(previewMode.value==='replay')return;
                        const targetDeviceId = options.deviceId || previewDeviceId.value;
                        if (!targetDeviceId) return null;
                        // Don't set loading state - keep showing old image for smooth transition
                        try {
                            const response = await fetch(`/api/devices/${encodeURIComponent(targetDeviceId)}/screenshot/base64`);
                            if (response.ok) {
                                const data = await response.json();
                                if (previewDeviceId.value !== targetDeviceId) return null;
                                if (data.image) {
                                    previewImage.value = data.image;
                                    try {
                                        const dims = await decodePngBase64Dimensions(data.image);
                                        if (previewDeviceId.value !== targetDeviceId) return null;
                                        if (dims.width > 0 && dims.height > 0) {
                                            previewAspect.value = dims.height / dims.width;
                                            return dims;
                                        }
                                    } catch (e) { }
                                }
                            }
                        } catch (e) {
                            // Silently fail, keep old image
                        }
                        return null;
                    }

                    async function autoTuneStreamSizeFromScreenshot(deviceId) {
                        const dims = await refreshPreview({ deviceId });
                        const emulatorPreferred = isEmulatorDevice(deviceId);
                        if (emulatorPreferred) {
                            streamMaxSize.value = 1080;
                            streamTargetFps.value = 45;
                            streamBitRate.value = 8000000;
                            return;
                        }
                        if (!dims) return;
                        const longEdge = Math.max(dims.width, dims.height);
                        streamMaxSize.value = pickDefaultStreamSizeByLongEdge(longEdge);
                    }

                    async function openPhonePreview() {
                        updatePreviewPosition();
                        showPhonePreview.value = true;
                        Vue.nextTick(() => ensurePreviewInViewport());
                        try {
                            const shown = localStorage.getItem(PREVIEW_FIRST_OPEN_HINT_KEY);
                            if (shown !== '1') {
                                upsertSystemAlert({
                                    id: 'preview-first-open-recovery-hint',
                                    level: 'warning',
                                    title: '预览无响应提示',
                                    message: '首次使用预览时，若设备长时间无响应或点击无反应，请先点击“锁定”再点击“解锁”触发画面显示。',
                                    autoDismiss: 12,
                                });
                                localStorage.setItem(PREVIEW_FIRST_OPEN_HINT_KEY, '1');
                            }
                        } catch (e) { }
                        if (!previewDeviceId.value && devices.value.length) {
                            previewDeviceId.value = devices.value[0].id;
                        }
                        if (previewDeviceId.value && previewMode.value!=='replay') {
                            await autoTuneStreamSizeFromScreenshot(previewDeviceId.value);
                            if (previewDeviceId.value) {
                                connectStream(previewDeviceId.value);
                            }
                        }
                    }

                    async function onPreviewDeviceChange() {
                        for(const demo of automation.demos.filter(d=>d.status==='recording' && d.device_id!==previewDeviceId.value))
                            await pauseActiveRecording(demo.device_id);
                        if(previewMode.value==='replay'){automation.seekReplay(0);return;}
                        const targetDeviceId = previewDeviceId.value;
                        if (targetDeviceId && isEmulatorDevice(targetDeviceId)) {
                            upsertSystemAlert({
                                id: 'emulator-preview-wakeup-hint',
                                level: 'warning',
                                title: '模拟器预览提示',
                                message: '切换设备后若预览黑屏，请手动点击模拟器屏幕唤醒。',
                                autoDismiss: 10,
                            });
                        }
                        disconnectStream();
                        previewImage.value = null;
                        previewAspect.value = 16 / 9;
                        if (targetDeviceId) {
                            await autoTuneStreamSizeFromScreenshot(targetDeviceId);
                            if (previewDeviceId.value === targetDeviceId) {
                                connectStream(targetDeviceId);
                            }
                        }
                    }

                    // --- Scrcpy Streaming Functions ---

                    function getStreamAuthHeaders() {
                        const headers = {};
                        const config = window._appConfig;
                        if (config && config.auth_enabled && config.token) {
                            headers['X-API-Key'] = config.token;
                        }
                        return headers;
                    }

                    function getStreamQueryParams(includeRestart = false) {
                        const params = new URLSearchParams({
                            max_size: String(streamMaxSize.value),
                            frame_rate: String(streamTargetFps.value),
                            bit_rate: String(streamBitRate.value),
                            control: streamUseScrcpyControl.value ? '1' : '0',
                            audio: streamAudioEnabled.value ? '1' : '0',
                        });
                        if (includeRestart) {
                            params.set('restart', 'true');
                        }
                        return params;
                    }

                    function formatBitrateLabel(kbps) {
                        const value = Number(kbps) || 0;
                        if (value <= 0) return '0 kbps';
                        if (value >= 1000) return `${(value / 1000).toFixed(2)} Mbps`;
                        return `${Math.round(value)} kbps`;
                    }

                    const streamTotalBitrateKbps = Vue.computed(
                        () => Math.max(0, (Number(streamVideoBitrateKbps.value) || 0) + (Number(streamAudioBitrateKbps.value) || 0))
                    );
                    const streamVideoBitrateLabel = Vue.computed(() => formatBitrateLabel(streamVideoBitrateKbps.value));
                    const streamAudioBitrateLabel = Vue.computed(() => formatBitrateLabel(streamAudioBitrateKbps.value));
                    const streamTotalBitrateLabel = Vue.computed(() => formatBitrateLabel(streamTotalBitrateKbps.value));

                    function _smoothMetric(refObj, next, alpha = 0.25) {
                        const current = Number(refObj.value) || 0;
                        if (current <= 0) {
                            refObj.value = Math.max(0, Math.round(next));
                            return;
                        }
                        refObj.value = Math.max(0, Math.round(current * (1 - alpha) + next * alpha));
                    }

                    function _updateIntervalJitter(nowMs, lastTs, avg, outRef) {
                        if (lastTs <= 0) return { lastTs: nowMs, avg };
                        const delta = nowMs - lastTs;
                        if (delta <= 0 || delta > 2500) {
                            return { lastTs: nowMs, avg };
                        }
                        let nextAvg = avg;
                        if (nextAvg <= 0) nextAvg = delta;
                        else nextAvg = nextAvg * 0.9 + delta * 0.1;
                        const jitter = Math.abs(delta - nextAvg);
                        _smoothMetric(outRef, jitter, 0.22);
                        return { lastTs: nowMs, avg: nextAvg };
                    }

                    function _recordVideoSample(byteLen) {
                        telemetryVideoBytes += Math.max(0, Number(byteLen) || 0);
                        const next = _updateIntervalJitter(performance.now(), telemetryLastVideoTs, telemetryVideoIntervalAvg, streamFrameJitterMs);
                        telemetryLastVideoTs = next.lastTs;
                        telemetryVideoIntervalAvg = next.avg;
                    }

                    function _recordAudioSample(byteLen) {
                        telemetryAudioBytes += Math.max(0, Number(byteLen) || 0);
                        const next = _updateIntervalJitter(performance.now(), telemetryLastAudioTs, telemetryAudioIntervalAvg, streamAudioJitterMs);
                        telemetryLastAudioTs = next.lastTs;
                        telemetryAudioIntervalAvg = next.avg;
                    }

                    function _resetTelemetry(clearControl = false) {
                        telemetryVideoBytes = 0;
                        telemetryAudioBytes = 0;
                        telemetryLastVideoTs = 0;
                        telemetryLastAudioTs = 0;
                        telemetryVideoIntervalAvg = 0;
                        telemetryAudioIntervalAvg = 0;
                        telemetryRttAvg = 0;
                        telemetryPendingProbeTs.clear();
                        streamVideoBitrateKbps.value = 0;
                        streamAudioBitrateKbps.value = 0;
                        streamLatencyMs.value = 0;
                        streamLatencyJitterMs.value = 0;
                        streamFrameJitterMs.value = 0;
                        streamAudioJitterMs.value = 0;
                        if (clearControl) {
                            streamControlActive.value = false;
                        }
                    }

                    function _stopTelemetryLoops() {
                        if (telemetryTimer) {
                            clearInterval(telemetryTimer);
                            telemetryTimer = null;
                        }
                        if (telemetryProbeTimer) {
                            clearInterval(telemetryProbeTimer);
                            telemetryProbeTimer = null;
                        }
                        telemetryPendingProbeTs.clear();
                    }

                    function _startTelemetryLoops(ws, connectToken) {
                        _stopTelemetryLoops();
                        telemetryTimer = setInterval(() => {
                            if (connectToken !== streamConnectToken || ws !== streamWs) return;
                            streamVideoBitrateKbps.value = Math.max(0, Math.round((telemetryVideoBytes * 8) / 1000));
                            streamAudioBitrateKbps.value = Math.max(0, Math.round((telemetryAudioBytes * 8) / 1000));
                            telemetryVideoBytes = 0;
                            telemetryAudioBytes = 0;
                        }, 1000);

                        telemetryProbeTimer = setInterval(() => {
                            if (connectToken !== streamConnectToken || ws !== streamWs) return;
                            if (!ws || ws.readyState !== WebSocket.OPEN) return;
                            const id = ++telemetryProbeSeq;
                            telemetryPendingProbeTs.set(id, performance.now());
                            try {
                                ws.send(JSON.stringify({ type: 'latency_probe', id }));
                            } catch (e) { }
                        }, 2000);
                    }

                    function _handleLatencyProbeAck(msg) {
                        const id = Number(msg && msg.id);
                        if (!Number.isFinite(id)) return;
                        const sentTs = telemetryPendingProbeTs.get(id);
                        if (!sentTs) return;
                        telemetryPendingProbeTs.delete(id);
                        const rtt = performance.now() - sentTs;
                        if (rtt <= 0 || rtt > 6000) return;
                        _smoothMetric(streamLatencyMs, rtt, 0.28);
                        if (telemetryRttAvg <= 0) telemetryRttAvg = rtt;
                        else telemetryRttAvg = telemetryRttAvg * 0.9 + rtt * 0.1;
                        const jitter = Math.abs(rtt - telemetryRttAvg);
                        _smoothMetric(streamLatencyJitterMs, jitter, 0.24);
                    }

                    async function startStreamWithSettings(deviceId, restart = true) {
                        if(previewMode.value==='replay')return;
                        const params = getStreamQueryParams(restart);
                        try {
                            await fetch(`/api/scrcpy/${encodeURIComponent(deviceId)}/start?${params.toString()}`, {
                                method: 'POST',
                                headers: getStreamAuthHeaders(),
                            });
                        } catch (e) { }
                    }

                    function lowerStreamProfileStep() {
                        const bitRates = [2000000, 4000000, 6000000, 8000000];
                        const fpsLevels = [15, 24, 30, 45, 60];
                        const sizeLevels = [540, 720, 960, 1080, 1440];

                        const brIdx = bitRates.indexOf(streamBitRate.value);
                        if (brIdx > 0) {
                            streamBitRate.value = bitRates[brIdx - 1];
                            return true;
                        }
                        const fpsIdx = fpsLevels.indexOf(streamTargetFps.value);
                        if (fpsIdx > 0) {
                            streamTargetFps.value = fpsLevels[fpsIdx - 1];
                            return true;
                        }
                        const sizeIdx = sizeLevels.indexOf(streamMaxSize.value);
                        if (sizeIdx > 0) {
                            streamMaxSize.value = sizeLevels[sizeIdx - 1];
                            return true;
                        }
                        return false;
                    }

                    function maybeAutoAdaptByFps(measuredFps) {
                        if (!streamAutoAdapt.value || !streamConnected.value || streamConnecting.value || !previewDeviceId.value) {
                            autoAdaptLowFpsStreak = 0;
                            return;
                        }
                        const now = Date.now();
                        if (now < autoAdaptCooldownUntil) return;
                        const target = Math.max(10, streamTargetFps.value);
                        if (measuredFps < target * 0.55) {
                            autoAdaptLowFpsStreak += 1;
                        } else {
                            autoAdaptLowFpsStreak = 0;
                            return;
                        }
                        if (autoAdaptLowFpsStreak < 3) return;
                        autoAdaptLowFpsStreak = 0;
                        if (lowerStreamProfileStep()) {
                            autoAdaptCooldownUntil = now + 12000;
                            showToast(`网络波动，已自动降档: ${streamMaxSize.value}p / ${streamTargetFps.value}fps / ${(streamBitRate.value / 1000000).toFixed(0)}M`, 'warning');
                            applyStreamSettings();
                        }
                    }

                    function closeAudioPipeline() {
                        audioQueue = [];
                        audioQueueOffset = 0;
                        if (audioProcessorNode) {
                            try { audioProcessorNode.disconnect(); } catch (e) { }
                            audioProcessorNode = null;
                        }
                        if (audioContext) {
                            try { audioContext.close(); } catch (e) { }
                            audioContext = null;
                        }
                    }

                    function dequeueAudioFrame() {
                        while (audioQueue.length) {
                            const chunk = audioQueue[0];
                            if (!chunk || !chunk.data || chunk.data.length === 0) {
                                audioQueue.shift();
                                audioQueueOffset = 0;
                                continue;
                            }
                            if (audioQueueOffset >= chunk.data.length) {
                                audioQueue.shift();
                                audioQueueOffset = 0;
                                continue;
                            }
                            if (chunk.channels <= 1) {
                                const sample = chunk.data[audioQueueOffset++];
                                return [sample, sample];
                            }
                            if (audioQueueOffset + chunk.channels > chunk.data.length) {
                                audioQueue.shift();
                                audioQueueOffset = 0;
                                continue;
                            }
                            const left = chunk.data[audioQueueOffset];
                            const right = chunk.channels > 1 ? chunk.data[audioQueueOffset + 1] : left;
                            audioQueueOffset += chunk.channels;
                            return [left, right];
                        }
                        return [0, 0];
                    }

                    function getAudioBufferedMs() {
                        const sampleRate = Math.max(8000, Number(streamAudioSampleRate.value) || 48000);
                        let totalFrames = 0;
                        for (let i = 0; i < audioQueue.length; i++) {
                            const chunk = audioQueue[i];
                            if (!chunk || !chunk.data || chunk.data.length === 0) continue;
                            const channels = Math.max(1, Number(chunk.channels) || 2);
                            const offset = i === 0 ? Math.max(0, audioQueueOffset) : 0;
                            const remainingSamples = Math.max(0, chunk.data.length - offset);
                            totalFrames += Math.floor(remainingSamples / channels);
                        }
                        return (totalFrames * 1000) / sampleRate;
                    }

                    function trimAudioQueueToTarget(targetMs) {
                        const sampleRate = Math.max(8000, Number(streamAudioSampleRate.value) || 48000);
                        let bufferedMs = getAudioBufferedMs();
                        if (bufferedMs <= targetMs) return;

                        let dropFrames = Math.ceil(((bufferedMs - targetMs) / 1000) * sampleRate);
                        while (dropFrames > 0 && audioQueue.length) {
                            const chunk = audioQueue[0];
                            if (!chunk || !chunk.data || chunk.data.length === 0) {
                                audioQueue.shift();
                                audioQueueOffset = 0;
                                continue;
                            }
                            const channels = Math.max(1, Number(chunk.channels) || 2);
                            const offset = Math.max(0, audioQueueOffset);
                            const remainingSamples = Math.max(0, chunk.data.length - offset);
                            const remainingFrames = Math.floor(remainingSamples / channels);
                            if (remainingFrames <= 0) {
                                audioQueue.shift();
                                audioQueueOffset = 0;
                                continue;
                            }
                            if (dropFrames >= remainingFrames) {
                                dropFrames -= remainingFrames;
                                audioQueue.shift();
                                audioQueueOffset = 0;
                                continue;
                            }
                            audioQueueOffset = offset + dropFrames * channels;
                            dropFrames = 0;
                        }
                    }

                    async function ensureAudioPipeline(sampleRate = 48000) {
                        const AudioCtx = window.AudioContext || window.webkitAudioContext;
                        if (!AudioCtx) {
                            showToast('当前浏览器不支持 AudioContext', 'warning');
                            return false;
                        }
                        if (!audioContext || audioContext.sampleRate !== sampleRate) {
                            closeAudioPipeline();
                            audioContext = new AudioCtx({ sampleRate });
                            audioProcessorNode = audioContext.createScriptProcessor(2048, 0, 2);
                            audioProcessorNode.onaudioprocess = (event) => {
                                const outL = event.outputBuffer.getChannelData(0);
                                const outR = event.outputBuffer.getChannelData(1);
                                for (let i = 0; i < outL.length; i++) {
                                    const frame = dequeueAudioFrame();
                                    outL[i] = frame[0];
                                    outR[i] = frame[1];
                                }
                            };
                            audioProcessorNode.connect(audioContext.destination);
                        }
                        try {
                            if (audioContext.state !== 'running') {
                                await audioContext.resume();
                            }
                        } catch (e) { }
                        return true;
                    }

                    function enqueueAudioPcm(arrayBuffer) {
                        if (!arrayBuffer || arrayBuffer.byteLength < 2) return;
                        const view = new DataView(arrayBuffer);
                        const sampleCount = Math.floor(view.byteLength / 2);
                        const pcm = new Float32Array(sampleCount);
                        for (let i = 0; i < sampleCount; i++) {
                            const s = view.getInt16(i * 2, true);
                            pcm[i] = Math.max(-1, Math.min(1, s / 32768));
                        }
                        audioQueue.push({
                            data: pcm,
                            channels: Math.max(1, streamAudioChannels.value || 2),
                        });
                        // Keep a small steady buffer and cut tail latency under network jitter.
                        if (getAudioBufferedMs() > AUDIO_QUEUE_MAX_MS) {
                            trimAudioQueueToTarget(AUDIO_QUEUE_TARGET_MS);
                        }
                        // Cap queue to avoid growing forever under network jitter.
                        if (audioQueue.length > 240) {
                            audioQueue.splice(0, audioQueue.length - 240);
                            audioQueueOffset = 0;
                        }
                    }

                    async function connectAudioStream(deviceId, forceRestart = false) {
                        disconnectAudioStream();
                        if (!streamAudioEnabled.value || !deviceId) return;
                        const ok = await ensureAudioPipeline(streamAudioSampleRate.value || 48000);
                        if (!ok) return;
                        const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
                        const wsParams = getStreamQueryParams(forceRestart);
                        wsParams.set('audio', '1');
                        let wsUrl = `${wsProtocol}//${location.host}/api/scrcpy/audio/ws/${encodeURIComponent(deviceId)}?${wsParams.toString()}`;
                        const config = window._appConfig;
                        if (config && config.auth_enabled && config.token) {
                            wsUrl += `&token=${encodeURIComponent(config.token)}`;
                        }
                        const ws = new WebSocket(wsUrl);
                        ws.binaryType = 'arraybuffer';
                        streamAudioWs = ws;
                        ws.onopen = () => {
                            streamAudioConnected.value = true;
                        };
                        ws.onmessage = async (event) => {
                            if (event.data instanceof ArrayBuffer) {
                                _recordAudioSample(event.data.byteLength);
                                enqueueAudioPcm(event.data);
                                return;
                            }
                            try {
                                const msg = JSON.parse(event.data);
                                if (msg.type === 'audio_info') {
                                    streamAudioCodec.value = msg.codec || 'raw';
                                    streamAudioSampleRate.value = msg.sample_rate || 48000;
                                    streamAudioChannels.value = msg.channels || 2;
                                    await ensureAudioPipeline(streamAudioSampleRate.value);
                                } else if (msg.type === 'ping') {
                                    if (ws.readyState === WebSocket.OPEN) {
                                        ws.send(JSON.stringify({ type: 'pong' }));
                                    }
                                }
                            } catch (e) { }
                        };
                        ws.onclose = () => {
                            streamAudioConnected.value = false;
                            if (streamAudioWs === ws) {
                                streamAudioWs = null;
                            }
                            audioQueue = [];
                            audioQueueOffset = 0;
                        };
                        ws.onerror = () => { };
                    }

                    function disconnectAudioStream() {
                        if (streamAudioWs) {
                            try { streamAudioWs.close(); } catch (e) { }
                            streamAudioWs = null;
                        }
                        streamAudioConnected.value = false;
                        audioQueue = [];
                        audioQueueOffset = 0;
                        closeAudioPipeline();
                    }

                    async function toggleAudioPassthrough() {
                        streamAudioEnabled.value = !streamAudioEnabled.value;
                        showToast(
                            streamAudioEnabled.value
                                ? '已开启音频直通（独立通道）'
                                : '已关闭音频直通'
                        );
                        if (!previewDeviceId.value) {
                            if (!streamAudioEnabled.value) {
                                disconnectAudioStream();
                            }
                            return;
                        }
                        streamReady.value = false;
                        streamLoadingText.value = 'Switching audio...';
                        await connectStream(previewDeviceId.value, true);
                    }

                    async function connectStream(deviceId, forceRestart = false) {
                        if(previewMode.value==='replay')return;
                        disconnectStream();
                        stopPreviewAutoRefresh();
                        if (!deviceId) return;
                        const connectToken = ++streamConnectToken;

                        streamConnecting.value = true;
                        streamReady.value = false;
                        streamLoadingText.value = 'Connecting...';
                        await startStreamWithSettings(deviceId, forceRestart);
                        if (connectToken !== streamConnectToken) return;
                        const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
                        const wsParams = getStreamQueryParams(false);
                        let wsUrl = `${wsProtocol}//${location.host}/api/scrcpy/ws/${encodeURIComponent(deviceId)}?${wsParams.toString()}`;
                        const config = window._appConfig;
                        if (config && config.auth_enabled && config.token) {
                            wsUrl += `&token=${encodeURIComponent(config.token)}`;
                        }

                        const ws = new WebSocket(wsUrl);
                        ws.binaryType = 'arraybuffer';
                        streamWs = ws;
                        if (streamAudioEnabled.value) {
                            connectAudioStream(deviceId, forceRestart);
                        } else {
                            disconnectAudioStream();
                        }

                        // FPS counter
                        fpsCounter = 0;
                        if (fpsTimer) clearInterval(fpsTimer);
                        fpsTimer = setInterval(() => {
                            if (connectToken !== streamConnectToken || ws !== streamWs) return;
                            const measuredFps = fpsCounter;
                            streamFps.value = measuredFps;
                            fpsCounter = 0;
                            maybeAutoAdaptByFps(measuredFps);
                        }, 1000);

                        ws.onopen = () => {
                            if (connectToken !== streamConnectToken || ws !== streamWs) return;
                            streamConnecting.value = false;
                            streamConnected.value = true;
                            streamLoadingText.value = 'Syncing stream metadata...';
                            _resetTelemetry(false);
                            _startTelemetryLoops(ws, connectToken);
                            // Stop polling when stream connects
                            stopPreviewAutoRefresh();
                        };

                        ws.onmessage = (event) => {
                            if (connectToken !== streamConnectToken || ws !== streamWs) return;
                            if (event.data instanceof ArrayBuffer) {
                                // Binary: JPEG frame
                                _recordVideoSample(event.data.byteLength);
                                renderFrame(event.data);
                                fpsCounter++;
                            } else {
                                // Text: JSON control message
                                try {
                                    const msg = JSON.parse(event.data);
                                    handleStreamMessage(msg);
                                } catch (e) { }
                            }
                        };

                        ws.onclose = () => {
                            if (connectToken !== streamConnectToken || ws !== streamWs) return;
                            streamConnected.value = false;
                            streamConnecting.value = false;
                            streamReady.value = false;
                            streamLoadingText.value = 'Connecting...';
                            _finishOrientationSwitchProgress(false);
                            _stopTelemetryLoops();
                            _resetTelemetry(true);
                            streamWs = null;
                            disconnectAudioStream();
                            autoAdaptLowFpsStreak = 0;
                            if (fpsTimer) { clearInterval(fpsTimer); fpsTimer = null; }
                            streamFps.value = 0;
                            // Fallback to polling if preview is still open
                            if (showPhonePreview.value && previewMode.value!=='replay' && previewDeviceId.value === deviceId) {
                                startPreviewAutoRefresh();
                            }
                        };

                        ws.onerror = () => {
                            // onclose will fire after this
                        };
                    }

                    function disconnectStream() {
                        streamConnectToken += 1;
                        _finishOrientationSwitchProgress(false);
                        _stopTelemetryLoops();
                        _resetTelemetry(true);
                        if (streamWs) {
                            try { streamWs.close(); } catch (e) { }
                            streamWs = null;
                        }
                        disconnectAudioStream();
                        streamConnected.value = false;
                        streamConnecting.value = false;
                        streamReady.value = false;
                        streamLoadingText.value = 'Connecting...';
                        autoAdaptLowFpsStreak = 0;
                        if (fpsTimer) { clearInterval(fpsTimer); fpsTimer = null; }
                        streamFps.value = 0;
                        streamDisplayRotation.value = 0;
                        streamSourceWidth.value = 0;
                        streamSourceHeight.value = 0;
                    }

                    function applyStreamSettings() {
                        if (!previewDeviceId.value) {
                            showToast('请先选择设备', 'warning');
                            return;
                        }
                        streamReady.value = false;
                        streamLoadingText.value = 'Reconnecting...';
                        connectStream(previewDeviceId.value, true);
                    }

                    async function toggleScrcpyControlInject() {
                        streamUseScrcpyControl.value = !streamUseScrcpyControl.value;
                        showToast(
                            streamUseScrcpyControl.value
                                ? '已开启 scrcpy 控制注入'
                                : '已关闭 scrcpy 控制注入'
                        );
                        if (!previewDeviceId.value) return;
                        streamReady.value = false;
                        streamLoadingText.value = 'Switching control mode...';
                        await connectStream(previewDeviceId.value, true);
                    }

                    function _stopOrientationSwitchTimer() {
                        if (streamSwitchTimer) {
                            clearInterval(streamSwitchTimer);
                            streamSwitchTimer = null;
                        }
                    }

                    function _startOrientationSwitchProgress(fromRotation, toRotation) {
                        _stopOrientationSwitchTimer();
                        streamOrientationSwitching.value = true;
                        streamSwitchProgress.value = Math.max(8, streamSwitchProgress.value || 0);
                        streamLoadingText.value = `旋转切换中 ${streamSwitchProgress.value}%`;
                        streamSwitchTimer = setInterval(() => {
                            const next = Math.min(94, streamSwitchProgress.value + 4);
                            streamSwitchProgress.value = next;
                            streamLoadingText.value = `旋转切换中 ${next}%`;
                        }, 120);
                    }

                    function _finishOrientationSwitchProgress(ok = true) {
                        _stopOrientationSwitchTimer();
                        if (!streamOrientationSwitching.value && streamSwitchProgress.value <= 0) {
                            return;
                        }
                        if (!ok) {
                            streamOrientationSwitching.value = false;
                            streamSwitchProgress.value = 0;
                            return;
                        }
                        streamSwitchProgress.value = 100;
                        streamLoadingText.value = '旋转切换完成 100%';
                        setTimeout(() => {
                            streamOrientationSwitching.value = false;
                            streamSwitchProgress.value = 0;
                            if (streamConnected.value && streamReady.value) {
                                streamLoadingText.value = '';
                            } else if (streamConnected.value) {
                                streamLoadingText.value = 'Waiting for first frame...';
                            }
                        }, 120);
                    }

                    function _normalizeRotation(rotation) {
                        const value = Number(rotation);
                        if (!Number.isFinite(value)) return 0;
                        if (value === 1 || value === 2 || value === 3) return value;
                        return 0;
                    }

                    function _isQuarterTurn(rotation) {
                        return rotation === 1 || rotation === 3;
                    }

                    function _mapDisplayToSource(x, y, displayW, displayH) {
                        const rotation = _normalizeRotation(streamDisplayRotation.value);
                        const srcW = Math.max(
                            1,
                            streamSourceWidth.value > 0
                                ? streamSourceWidth.value
                                : (_isQuarterTurn(rotation) ? displayH : displayW)
                        );
                        const srcH = Math.max(
                            1,
                            streamSourceHeight.value > 0
                                ? streamSourceHeight.value
                                : (_isQuarterTurn(rotation) ? displayW : displayH)
                        );

                        let sx = x;
                        let sy = y;
                        if (rotation === 1) {
                            sx = y;
                            sy = displayW - x;
                        } else if (rotation === 2) {
                            sx = displayW - x;
                            sy = displayH - y;
                        } else if (rotation === 3) {
                            sx = displayH - y;
                            sy = x;
                        }

                        sx = Math.max(0, Math.min(srcW - 1, sx));
                        sy = Math.max(0, Math.min(srcH - 1, sy));
                        return { x: sx, y: sy, w: srcW, h: srcH };
                    }

                    function renderFrame(arrayBuffer) {
                        const canvas = previewCanvas.value;
                        if (!canvas) return;
                        const ctx = canvas.getContext('2d');
                        if (!ctx) return;

                        const blob = new Blob([arrayBuffer], { type: 'image/jpeg' });
                        const url = URL.createObjectURL(blob);
                        const img = new window.Image();
                        img.onload = () => {
                            if (img.width > 0 && img.height > 0) {
                                streamSourceWidth.value = img.width;
                                streamSourceHeight.value = img.height;
                                const rotation = _normalizeRotation(streamDisplayRotation.value);
                                const displayW = _isQuarterTurn(rotation) ? img.height : img.width;
                                const displayH = _isQuarterTurn(rotation) ? img.width : img.height;
                                const ratio = displayH / displayW;
                                if (Math.abs(ratio - previewAspect.value) > 0.01) {
                                    maybeResizePreviewOnAspectSwitch(ratio);
                                    previewAspect.value = ratio;
                                }
                                if (displayW !== canvasWidth.value || displayH !== canvasHeight.value) {
                                    canvasWidth.value = displayW;
                                    canvasHeight.value = displayH;
                                }
                                if (canvas.width !== displayW || canvas.height !== displayH) {
                                    canvas.width = displayW;
                                    canvas.height = displayH;
                                }
                                ctx.save();
                                ctx.clearRect(0, 0, canvas.width, canvas.height);
                                if (rotation === 1) {
                                    ctx.translate(canvas.width, 0);
                                    ctx.rotate(Math.PI / 2);
                                } else if (rotation === 2) {
                                    ctx.translate(canvas.width, canvas.height);
                                    ctx.rotate(Math.PI);
                                } else if (rotation === 3) {
                                    ctx.translate(0, canvas.height);
                                    ctx.rotate(-Math.PI / 2);
                                }
                                ctx.drawImage(img, 0, 0, img.width, img.height);
                                ctx.restore();
                            }
                            if (!streamReady.value) {
                                streamReady.value = true;
                                streamLoadingText.value = '';
                            }
                            if (streamOrientationSwitching.value) {
                                _finishOrientationSwitchProgress(true);
                            }
                            URL.revokeObjectURL(url);
                        };
                        img.onerror = () => {
                            URL.revokeObjectURL(url);
                        };
                        img.src = url;
                    }

                    function handleStreamMessage(msg) {
                        if (msg.type === 'control_blocked') { showToast(msg.message, 'info'); return; }
                        if (msg.type === 'stream_info') {
                            deviceScreenWidth.value = msg.width || 0;
                            deviceScreenHeight.value = msg.height || 0;
                            streamControlActive.value = !!msg.control;
                            streamAudioCodec.value = msg.audio_codec || streamAudioCodec.value;
                            streamDisplayRotation.value = _normalizeRotation(msg.rotation);
                            streamSourceWidth.value = msg.video_width || streamSourceWidth.value;
                            streamSourceHeight.value = msg.video_height || streamSourceHeight.value;
                            if (msg.width && msg.height) {
                                let ratio = msg.height / msg.width;
                                if (streamSourceWidth.value > 0 && streamSourceHeight.value > 0) {
                                    const displayW = _isQuarterTurn(streamDisplayRotation.value)
                                        ? streamSourceHeight.value
                                        : streamSourceWidth.value;
                                    const displayH = _isQuarterTurn(streamDisplayRotation.value)
                                        ? streamSourceWidth.value
                                        : streamSourceHeight.value;
                                    ratio = displayH / displayW;
                                    canvasWidth.value = displayW;
                                    canvasHeight.value = displayH;
                                } else {
                                    canvasWidth.value = msg.width;
                                    canvasHeight.value = msg.height;
                                }
                                if (Math.abs(ratio - previewAspect.value) > 0.01) {
                                    maybeResizePreviewOnAspectSwitch(ratio);
                                }
                                previewAspect.value = ratio;
                                if (!streamOrientationSwitching.value) {
                                    streamLoadingText.value = 'Waiting for first frame...';
                                }
                            }
                        } else if (msg.type === 'rotation_switching') {
                            _startOrientationSwitchProgress(msg.from, msg.to);
                        } else if (msg.type === 'rotation_recovery_done') {
                            if (streamOrientationSwitching.value) {
                                streamSwitchProgress.value = Math.max(95, streamSwitchProgress.value);
                                streamLoadingText.value = `旋转切换中 ${streamSwitchProgress.value}%`;
                            }
                        } else if (msg.type === 'rotation_recovery_failed') {
                            _finishOrientationSwitchProgress(false);
                            showToast('旋转重连失败，请手动重连', 'warning');
                        } else if (msg.type === 'latency_probe_ack') {
                            _handleLatencyProbeAck(msg);
                        } else if (msg.type === 'ping') {
                            if (streamWs && streamWs.readyState === WebSocket.OPEN) {
                                streamWs.send(JSON.stringify({ type: 'pong' }));
                            }
                        }
                    }

                    // --- Touch / Mouse Interaction ---

                    function _getCanvasCoords(event) {
                        const canvas = previewCanvas.value;
                        if (!canvas) return null;
                        const rect = canvas.getBoundingClientRect();
                        if (!rect.width || !rect.height || event.clientX < rect.left || event.clientX > rect.right ||
                            event.clientY < rect.top || event.clientY > rect.bottom) return null;
                        const scaleX = canvas.width / rect.width;
                        const scaleY = canvas.height / rect.height;
                        const displayX = (event.clientX - rect.left) * scaleX;
                        const displayY = (event.clientY - rect.top) * scaleY;
                        const mapped = _mapDisplayToSource(displayX, displayY, canvas.width, canvas.height);
                        return {
                            x: mapped.x,
                            y: mapped.y,
                            w: mapped.w,
                            h: mapped.h,
                        };
                    }

                    function _sendTouch(action, x, y, w, h) {
                        if(previewMode.value==='replay')return;
                        if (streamWs && streamWs.readyState === WebSocket.OPEN) {
                            streamWs.send(JSON.stringify({
                                type: 'touch',
                                action: action,
                                x: Math.round(x),
                                y: Math.round(y),
                                width: w,
                                height: h,
                            }));
                        }
                    }

                    function _sendScroll(x, y, w, h, deltaY) {
                        if(previewMode.value==='replay')return;
                        if (streamWs && streamWs.readyState === WebSocket.OPEN) {
                            streamWs.send(JSON.stringify({
                                type: 'scroll',
                                x: Math.round(x),
                                y: Math.round(y),
                                width: w,
                                height: h,
                                deltaY: deltaY,
                            }));
                        }
                    }

                    function onCanvasMouseDown(e) {
                        if (previewMode.value === 'replay' || !streamConnected.value || e.button !== 0 || e.currentTarget !== previewCanvas.value) return;
                        const canvas = previewCanvas.value;
                        if (canvas) {
                            try { canvas.focus({ preventScroll: true }); } catch (err) { }
                        }
                        const coords = _getCanvasCoords(e);
                        if (!coords) return;
                        touchState.isDown = true;
                        touchState.startX = coords.x;
                        touchState.startY = coords.y;
                        touchState.lastX = coords.x;
                        touchState.lastY = coords.y;
                        touchState.lastW = coords.w;
                        touchState.lastH = coords.h;
                        touchState.startTime = Date.now();
                        touchState.hasMoved = false;
                        _sendTouch('down', coords.x, coords.y, coords.w, coords.h);
                    }

                    function onCanvasMouseMove(e) {
                        if (!touchState.isDown || !streamConnected.value) return;
                        const coords = _getCanvasCoords(e);
                        if (!coords) return;
                        const dx = coords.x - touchState.startX;
                        const dy = coords.y - touchState.startY;
                        if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
                            touchState.hasMoved = true;
                        }
                        touchState.lastX = coords.x;
                        touchState.lastY = coords.y;
                        touchState.lastW = coords.w;
                        touchState.lastH = coords.h;
                        _sendTouch('move', coords.x, coords.y, coords.w, coords.h);
                    }

                    function onCanvasMouseUp(e) {
                        if (!touchState.isDown) return;
                        touchState.isDown = false;
                        if (!streamConnected.value) return;
                        const coords = _getCanvasCoords(e);
                        if (coords) {
                            _sendTouch('up', coords.x, coords.y, coords.w, coords.h);
                        } else {
                            // Mouse left canvas - use last known position
                            const canvas = previewCanvas.value;
                            if (canvas) {
                                _sendTouch(
                                    'up',
                                    touchState.lastX,
                                    touchState.lastY,
                                    touchState.lastW || canvas.width,
                                    touchState.lastH || canvas.height
                                );
                            }
                        }
                    }

                    function onCanvasTouchStart(e) {
                        if (previewMode.value === 'replay' || !streamConnected.value || !e.touches.length || e.currentTarget !== previewCanvas.value) return;
                        const canvasFocus = previewCanvas.value;
                        if (canvasFocus) {
                            try { canvasFocus.focus({ preventScroll: true }); } catch (err) { }
                        }
                        const touch = e.touches[0];
                        const canvas = previewCanvas.value;
                        if (!canvas) return;
                        const rect = canvas.getBoundingClientRect();
                        const scaleX = canvas.width / rect.width;
                        const scaleY = canvas.height / rect.height;
                        const displayX = (touch.clientX - rect.left) * scaleX;
                        const displayY = (touch.clientY - rect.top) * scaleY;
                        const mapped = _mapDisplayToSource(displayX, displayY, canvas.width, canvas.height);
                        const x = mapped.x;
                        const y = mapped.y;
                        touchState.isDown = true;
                        touchState.startX = x;
                        touchState.startY = y;
                        touchState.lastX = x;
                        touchState.lastY = y;
                        touchState.lastW = mapped.w;
                        touchState.lastH = mapped.h;
                        touchState.hasMoved = false;
                        _sendTouch('down', x, y, mapped.w, mapped.h);
                    }

                    function onCanvasTouchMove(e) {
                        if (!touchState.isDown || !streamConnected.value || !e.touches.length) return;
                        const touch = e.touches[0];
                        const canvas = previewCanvas.value;
                        if (!canvas) return;
                        const rect = canvas.getBoundingClientRect();
                        const scaleX = canvas.width / rect.width;
                        const scaleY = canvas.height / rect.height;
                        const displayX = (touch.clientX - rect.left) * scaleX;
                        const displayY = (touch.clientY - rect.top) * scaleY;
                        const mapped = _mapDisplayToSource(displayX, displayY, canvas.width, canvas.height);
                        const x = mapped.x;
                        const y = mapped.y;
                        touchState.lastX = x;
                        touchState.lastY = y;
                        touchState.lastW = mapped.w;
                        touchState.lastH = mapped.h;
                        touchState.hasMoved = true;
                        _sendTouch('move', x, y, mapped.w, mapped.h);
                    }

                    function onCanvasTouchEnd(e) {
                        if (!touchState.isDown) return;
                        touchState.isDown = false;
                        if (!streamConnected.value) return;
                        const canvas = previewCanvas.value;
                        if (canvas) {
                            _sendTouch(
                                'up',
                                touchState.lastX,
                                touchState.lastY,
                                touchState.lastW || canvas.width,
                                touchState.lastH || canvas.height
                            );
                        }
                    }

                    function onCanvasWheel(e) {
                        if (!streamConnected.value) return;
                        const coords = _getCanvasCoords(e);
                        if (!coords) return;
                        wheelDeltaAccum += e.deltaY;
                        if (wheelTimer) return;
                        wheelTimer = setTimeout(() => {
                            _sendScroll(coords.x, coords.y, coords.w, coords.h, wheelDeltaAccum);
                            wheelDeltaAccum = 0;
                            wheelTimer = null;
                        }, 80);
                    }

                    function sendKey(keycode) {
                        if(previewMode.value==='replay')return;
                        if (streamWs && streamWs.readyState === WebSocket.OPEN) {
                            streamWs.send(JSON.stringify({ type: 'key', keycode: keycode }));
                        } else if (previewDeviceId.value) {
                            // Fallback via REST (not ideal but works)
                            startStreamWithSettings(previewDeviceId.value, false);
                        }
                    }

                    function mapBrowserKeyToAndroidKeycode(event) {
                        const code = event.code || '';
                        const directMap = {
                            Backspace: 67,
                            Enter: 66,
                            NumpadEnter: 66,
                            Tab: 61,
                            Escape: 111,
                            Space: 62,
                            ArrowUp: 19,
                            ArrowDown: 20,
                            ArrowLeft: 21,
                            ArrowRight: 22,
                            Delete: 112,
                            Home: 122,
                            End: 123,
                            PageUp: 92,
                            PageDown: 93,
                            Insert: 124,
                            Minus: 69,
                            Equal: 70,
                            BracketLeft: 71,
                            BracketRight: 72,
                            Backslash: 73,
                            Semicolon: 74,
                            Quote: 75,
                            Slash: 76,
                            Comma: 55,
                            Period: 56,
                            Backquote: 68,
                        };
                        if (Object.prototype.hasOwnProperty.call(directMap, code)) {
                            return directMap[code];
                        }
                        if (code.startsWith('Key') && code.length === 4) {
                            const ch = code.charCodeAt(3);
                            if (ch >= 65 && ch <= 90) {
                                return 29 + (ch - 65); // KEYCODE_A ... KEYCODE_Z
                            }
                        }
                        if (code.startsWith('Digit') && code.length === 6) {
                            const digit = Number(code[5]);
                            if (Number.isInteger(digit) && digit >= 0 && digit <= 9) {
                                return 7 + digit; // KEYCODE_0 ... KEYCODE_9
                            }
                        }
                        if (code.startsWith('Numpad') && code.length === 7) {
                            const digit = Number(code[6]);
                            if (Number.isInteger(digit) && digit >= 0 && digit <= 9) {
                                return 7 + digit;
                            }
                        }
                        return null;
                    }

                    function handlePreviewKeyboard(event) {
                        if (
                            !showPhonePreview.value
                            || previewMode.value==='replay'
                            || !streamConnected.value
                            || !previewDeviceId.value
                            || !previewCanvas.value
                        ) {
                            return;
                        }
                        if (document.activeElement !== previewCanvas.value) {
                            return;
                        }
                        if (event.isComposing || event.ctrlKey || event.metaKey || event.altKey) {
                            return;
                        }
                        const keycode = mapBrowserKeyToAndroidKeycode(event);
                        if (keycode === null) return;
                        event.preventDefault();
                        event.stopPropagation();
                        sendKey(keycode);
                    }

                    function startDragPreview(e) {
                        const interactive = e.target.closest(
                            'button, select, input, textarea, a, label, [data-no-preview-drag="1"]'
                        );
                        if (
                            interactive
                            || e.target.closest('.phone-preview-body')
                            || e.target.closest('.phone-preview-resize')
                            || e.target.closest('.phone-preview-resize-side')
                        ) return;
                        e.preventDefault();
                        isDragging = true;
                        dragOffset.x = e.clientX - previewPosition.value.x;
                        dragOffset.y = e.clientY - previewPosition.value.y;
                        document.body.classList.add('preview-dragging');
                        document.addEventListener('mousemove', onDragPreview);
                        document.addEventListener('mouseup', stopDragPreview);
                    }

                    function onDragPreview(e) {
                        if (!isDragging) return;
                        const bounds = getPreviewViewportBounds();
                        previewPosition.value.x = Math.max(bounds.minX, Math.min(bounds.maxX, e.clientX - dragOffset.x));
                        previewPosition.value.y = Math.max(bounds.minY, Math.min(bounds.maxY, e.clientY - dragOffset.y));
                    }

                    function stopDragPreview() {
                        isDragging = false;
                        document.body.classList.remove('preview-dragging');
                        document.removeEventListener('mousemove', onDragPreview);
                        document.removeEventListener('mouseup', stopDragPreview);
                    }

                    function startResizePreview(e, edge = 'right') {
                        isResizing = true;
                        resizeStart.x = e.clientX;
                        resizeStart.w = previewWidth.value;
                        resizeStart.left = previewPosition.value.x;
                        resizeStart.top = previewPosition.value.y;
                        resizeStart.edge = edge;
                        document.addEventListener('mousemove', onResizePreview);
                        document.addEventListener('mouseup', stopResizePreview);
                    }

                    function onResizePreview(e) {
                        if (!isResizing) return;
                        const top = resizeStart.top;
                        const safeLeft = PREVIEW_SAFE_MARGIN;

                        if (resizeStart.edge === 'left') {
                            const rightAnchor = resizeStart.left + resizeStart.w;
                            const candidateLeft = Math.max(safeLeft, resizeStart.left + (e.clientX - resizeStart.x));
                            let newW = rightAnchor - candidateLeft;
                            let newLeft = candidateLeft;
                            let { minAllowed, maxAllowed } = getPreviewWidthRange(newLeft, top);
                            newW = Math.max(minAllowed, Math.min(maxAllowed, newW));
                            newLeft = rightAnchor - newW;
                            if (newLeft < safeLeft) {
                                newLeft = safeLeft;
                                ({ minAllowed, maxAllowed } = getPreviewWidthRange(newLeft, top));
                                newW = Math.max(minAllowed, Math.min(maxAllowed, rightAnchor - newLeft));
                                newLeft = rightAnchor - newW;
                            }
                            previewPosition.value.x = newLeft;
                            previewWidth.value = newW;
                        } else {
                            const { minAllowed, maxAllowed } = getPreviewWidthRange(resizeStart.left, top);
                            let newW = resizeStart.w + (e.clientX - resizeStart.x);
                            newW = Math.max(minAllowed, Math.min(maxAllowed, newW));
                            previewWidth.value = newW;
                        }

                        ensurePreviewInViewport();
                    }

                    function stopResizePreview() {
                        isResizing = false;
                        document.removeEventListener('mousemove', onResizePreview);
                        document.removeEventListener('mouseup', stopResizePreview);
                    }

                    function startPreviewAutoRefresh() {
                        stopPreviewAutoRefresh();
                        previewInterval = setInterval(() => {
                            if (
                                showPhonePreview.value
                                && previewMode.value!=='replay'
                                && previewDeviceId.value
                                && !streamConnected.value
                                && !streamConnecting.value
                            ) {
                                refreshPreview();
                            }
                        }, 2000); // Refresh every 2 seconds
                    }

                    function stopPreviewAutoRefresh() {
                        if (previewInterval) {
                            clearInterval(previewInterval);
                            previewInterval = null;
                        }
                    }

                    function handleWindowResize() {
                        if (showPhonePreview.value) {
                            ensurePreviewInViewport();
                        }
                    }

                    // Watch showPhonePreview to start/stop auto refresh
                    watch(showPhonePreview, (show) => {
                        document.body.classList.toggle('preview-open', show);
                        if (show) {
                            // openPhonePreview/onclose will decide whether to start fallback polling.
                            Vue.nextTick(() => ensurePreviewInViewport());
                        } else {
                            automation.stopPlayback();
                            if(isAuthenticated.value)pauseActiveRecording().catch(()=>{});
                            disconnectStream();
                            stopPreviewAutoRefresh();
                        }
                    });

                    watch([previewWidth, previewAspect], () => {
                        if (showPhonePreview.value && !isDragging && !isResizing) {
                            ensurePreviewInViewport();
                        }
                    });

                    watch(previewIsLandscape, () => {
                        if (showPhonePreview.value && !isDragging && !isResizing) {
                            Vue.nextTick(() => ensurePreviewInViewport());
                        }
                    });

                    // ===== Database Management =====
                    const dbTables = ref([]);
                    const dbCurrentTable = ref('');
                    const dbColumns = ref([]);
                    const dbRows = ref([]);
                    const dbSearch = ref('');
                    const dbSortBy = ref('');
                    const dbSortOrder = ref('asc');
                    const dbPagination = ref({ page: 1, page_size: 50, total: 0, total_pages: 1 });
                    const dbShowFormModal = ref(false);
                    const dbFormMode = ref('add'); // 'add' or 'edit'
                    const dbFormData = ref({});
                    const dbShowDeleteConfirm = ref(false);
                    const dbDeleteTarget = ref(null);
                    let dbSearchTimer = null;

                    const dbVisibleColumns = computed(() => {
                        // Hide image_data BLOB columns from the table view
                        return dbColumns.value.filter(c => !['image_data'].includes(c.name));
                    });

                    const dbPageRange = computed(() => {
                        const p = dbPagination.value;
                        const total = p.total_pages;
                        const current = p.page;
                        const range = [];
                        let start = Math.max(1, current - 2);
                        let end = Math.min(total, current + 2);
                        if (end - start < 4) {
                            if (start === 1) end = Math.min(total, start + 4);
                            else start = Math.max(1, end - 4);
                        }
                        for (let i = start; i <= end; i++) range.push(i);
                        return range;
                    });

                    async function loadDbTables() {
                        try {
                            const res = await fetch('/api/database/tables');
                            const data = await res.json();
                            dbTables.value = data.tables || [];
                        } catch (e) {
                            console.error('Failed to load tables:', e);
                            showToast('Failed to load tables', 'error');
                        }
                    }

                    async function selectDbTable(name) {
                        dbCurrentTable.value = name;
                        dbSearch.value = '';
                        dbSortBy.value = '';
                        dbSortOrder.value = 'asc';
                        dbPagination.value.page = 1;
                        await loadDbSchema();
                        await loadDbRows();
                    }

                    async function loadDbSchema() {
                        if (!dbCurrentTable.value) return;
                        try {
                            const res = await fetch(`/api/database/tables/${encodeURIComponent(dbCurrentTable.value)}/schema`);
                            const data = await res.json();
                            dbColumns.value = data.columns || [];
                        } catch (e) {
                            console.error('Failed to load schema:', e);
                        }
                    }

                    async function loadDbRows() {
                        if (!dbCurrentTable.value) return;
                        try {
                            const params = new URLSearchParams({
                                page: dbPagination.value.page,
                                page_size: dbPagination.value.page_size,
                            });
                            if (dbSearch.value) params.set('search', dbSearch.value);
                            if (dbSortBy.value) {
                                params.set('sort_by', dbSortBy.value);
                                params.set('sort_order', dbSortOrder.value);
                            }
                            const res = await fetch(`/api/database/tables/${encodeURIComponent(dbCurrentTable.value)}/rows?${params}`);
                            const data = await res.json();
                            dbRows.value = data.rows || [];
                            dbPagination.value = {
                                page: data.page,
                                page_size: data.page_size,
                                total: data.total,
                                total_pages: data.total_pages,
                            };
                        } catch (e) {
                            console.error('Failed to load rows:', e);
                            showToast('Failed to load data', 'error');
                        }
                    }

                    function dbSearchDebounce() {
                        clearTimeout(dbSearchTimer);
                        dbSearchTimer = setTimeout(() => {
                            dbPagination.value.page = 1;
                            loadDbRows();
                        }, 350);
                    }

                    function toggleDbSort(colName) {
                        if (dbSortBy.value === colName) {
                            dbSortOrder.value = dbSortOrder.value === 'asc' ? 'desc' : 'asc';
                        } else {
                            dbSortBy.value = colName;
                            dbSortOrder.value = 'asc';
                        }
                        loadDbRows();
                    }

                    function dbGoToPage(page) {
                        if (page < 1 || page > dbPagination.value.total_pages) return;
                        dbPagination.value.page = page;
                        loadDbRows();
                    }

                    function truncateCell(value) {
                        const s = String(value);
                        return s.length > 100 ? s.substring(0, 100) + '…' : s;
                    }

                    function isLongField(colName) {
                        const longNames = ['content', 'task_content', 'value', 'details', 'message', 'description', 'todo_list'];
                        return longNames.some(n => colName.toLowerCase().includes(n));
                    }

                    function getPrimaryKey(row) {
                        const pkCols = dbColumns.value.filter(c => c.pk);
                        if (pkCols.length === 0) return null;
                        const pk = {};
                        pkCols.forEach(c => { pk[c.name] = row[c.name]; });
                        return pk;
                    }

                    function openDbAddModal() {
                        dbFormMode.value = 'add';
                        const formData = {};
                        dbColumns.value.forEach(col => {
                            formData[col.name] = '';
                        });
                        dbFormData.value = formData;
                        dbShowFormModal.value = true;
                    }

                    function openDbEditModal(row) {
                        dbFormMode.value = 'edit';
                        const formData = {};
                        dbColumns.value.forEach(col => {
                            let val = row[col.name];
                            // Don't allow editing BLOB placeholders
                            if (typeof val === 'string' && val.startsWith('[BLOB:')) val = '';
                            formData[col.name] = val !== null && val !== undefined ? String(val) : '';
                        });
                        dbFormData.value = formData;
                        dbShowFormModal.value = true;
                    }

                    function openDbDeleteConfirm(row) {
                        dbDeleteTarget.value = row;
                        dbShowDeleteConfirm.value = true;
                    }

                    async function saveDbRow() {
                        const table = dbCurrentTable.value;
                        if (!table) return;

                        // Build data, skipping empty fields for add mode
                        const data = {};
                        for (const col of dbColumns.value) {
                            const val = dbFormData.value[col.name];
                            if (val !== '' && val !== undefined) {
                                // Try to parse numbers for numeric columns
                                if (col.type && col.type.toUpperCase().includes('INT') && !isNaN(val)) {
                                    data[col.name] = parseInt(val);
                                } else if (col.type && col.type.toUpperCase().includes('REAL') && !isNaN(val)) {
                                    data[col.name] = parseFloat(val);
                                } else {
                                    data[col.name] = val;
                                }
                            }
                        }

                        try {
                            let res;
                            if (dbFormMode.value === 'add') {
                                res = await fetch(`/api/database/tables/${encodeURIComponent(table)}/rows`, {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ data }),
                                });
                            } else {
                                const pk = getPrimaryKey(dbFormData.value);
                                // For edit, use original PK values from the row being edited
                                const originalPk = {};
                                const pkCols = dbColumns.value.filter(c => c.pk);
                                pkCols.forEach(c => { originalPk[c.name] = dbFormData.value[c.name]; });

                                res = await fetch(`/api/database/tables/${encodeURIComponent(table)}/rows`, {
                                    method: 'PUT',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ data, primary_key: originalPk }),
                                });
                            }

                            const result = await res.json();
                            if (res.ok && result.success) {
                                showToast(result.message, 'success');
                                dbShowFormModal.value = false;
                                await loadDbRows();
                                await loadDbTables(); // Refresh row counts
                            } else {
                                showToast(result.detail || result.message || 'Operation failed', 'error');
                            }
                        } catch (e) {
                            console.error('Save failed:', e);
                            showToast('Save failed: ' + e.message, 'error');
                        }
                    }

                    async function confirmDeleteDbRow() {
                        const table = dbCurrentTable.value;
                        const row = dbDeleteTarget.value;
                        if (!table || !row) return;

                        const pk = getPrimaryKey(row);
                        if (!pk) {
                            showToast('Cannot determine primary key for this row', 'error');
                            return;
                        }

                        try {
                            const res = await fetch(`/api/database/tables/${encodeURIComponent(table)}/rows`, {
                                method: 'DELETE',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ data: {}, primary_key: pk }),
                            });
                            const result = await res.json();
                            if (res.ok && result.success) {
                                showToast(result.message, 'success');
                                dbShowDeleteConfirm.value = false;
                                dbDeleteTarget.value = null;
                                await loadDbRows();
                                await loadDbTables(); // Refresh row counts
                            } else {
                                showToast(result.detail || 'Delete failed', 'error');
                            }
                        } catch (e) {
                            console.error('Delete failed:', e);
                            showToast('Delete failed: ' + e.message, 'error');
                        }
                    }

                    const automation = Vue.reactive(useAutomation({
                        active:isAuthenticated,devices,previewDevice:previewDeviceId,
                        onUnauthorized(){clearAuthenticatedConnections();isAuthenticated.value=false;loginError.value='登录已失效，请重新登录';},
                        notify:showToast,openPreview:openIntegratedPreview,openTask:openIntegratedTask,
                        navigate(page){
                            showTaskDetail.value=false;
                            if(['recipes','triggers'].includes(page)){currentPage.value='scheduler';schedulerTab.value=page;}
                            else if(page==='settings')currentPage.value='settings';
                            else currentPage.value='tasks';
                        }
                    }));
                    Vue.provide('automation',automation);
                    watch(devices,list=>{if(!automation.recipeDevice && list.length)automation.recipeDevice=list[0].id;});
                    watch(()=>automation.taskIndex[activeRunTaskId.value],task=>{
                        if(task){taskRunning.value=!isTerminal(task.status);taskProgress.value=task.progress;}
                    });
                    watch(()=>[schedulerForm.value.recipe_id,schedulerForm.value.recipe_revision],async([id,revision])=>{
                        schedulerRecipeDefinition.value=null;
                        if(!id || !isAuthenticated.value)return;
                        try{
                            let recipe=automation.recipes.find(r=>r.id===id);
                            if(!recipe)recipe=await apiCall(`/api/recipes/${id}`);
                            if(revision && recipe.revision!==revision){
                                const versions=await apiCall(`/api/recipes/${id}/revisions`);
                                recipe=versions.revisions.find(r=>r.revision===revision);
                            }
                            if(schedulerForm.value.recipe_id===id && schedulerForm.value.recipe_revision===revision)
                                schedulerRecipeDefinition.value=recipe;
                        }catch(error){showToast(error.message,'error');}
                    });
                    function openRecipeLibrary(){currentPage.value='scheduler';schedulerTab.value='recipes';showTaskDetail.value=false;}
                    async function openIntegratedTask(id){
                        await automation.attempt(async()=>{
                            const task=await automation.ensureTask(id);
                            if(!task)return;
                            activeRunTaskId.value=id;
                            await automation.openTask(task);
                            const lastScreen=[...automation.events].reverse().find(e=>e.kind==='screen'&&e.data?.image_id);
                            if(lastScreen)taskScreenshot.value='/api/automation/images/'+lastScreen.data.image_id;
                            taskDetailData.value={taskId:id,status:task.status,logs:[],screenshots:[]};
                            showTaskDetail.value=true;
                        });
                    }
                    async function openIntegratedPreview(deviceId,demonstrate=false){
                        showTaskDetail.value=false;
                        if(deviceId && deviceId!==previewDeviceId.value)await pauseActiveRecording();
                        if(deviceId)previewDeviceId.value=deviceId;
                        await setPreviewMode(demonstrate?'record':'live',false);
                        await openPhonePreview();
                    }
                    async function pauseActiveRecording(device=previewDeviceId.value){
                        const demo=automation.demos.find(d=>d.device_id===device && d.status==='recording');
                        if(demo){
                            await apiCall(`/api/demonstrations/${demo.id}/pause`,{method:'POST',body:'{}'});
                            await automation.refresh();
                            showToast('示教录制已暂停，可点“录”继续或结束','info');
                        }
                    }
                    function cancelPreviewGesture(){
                        if(touchState.isDown){
                            _sendTouch('cancel',touchState.lastX,touchState.lastY,touchState.lastW,touchState.lastH);
                            touchState.isDown=false;
                        }
                        if(document.activeElement === previewCanvas.value) previewCanvas.value?.blur();
                    }
                    async function setPreviewMode(mode,reconnect=true){
                        if(mode===previewMode.value)return;
                        cancelPreviewGesture();
                        if(mode==='replay'){await openPreviewReplay();return;}
                        if(mode!=='record')await pauseActiveRecording();
                        const wasReplay=previewMode.value==='replay';
                        automation.stopPlayback();previewMode.value=mode;
                        if(wasReplay && reconnect && showPhonePreview.value && previewDeviceId.value)
                            await openPhonePreview();
                    }
                    function showReplaySurface(){
                        cancelPreviewGesture();
                        showTaskDetail.value=false;
                        previewMode.value='replay';
                        disconnectStream();stopPreviewAutoRefresh();
                        updatePreviewPosition();showPhonePreview.value=true;
                        Vue.nextTick(()=>ensurePreviewInViewport());
                    }
                    async function openPreviewReplay(id){
                        await automation.attempt(async()=>{
                            await pauseActiveRecording();
                            automation.stopPlayback();
                            const candidates=automation.tasks.filter(task=>!previewDeviceId.value||task.device_ids.includes(previewDeviceId.value));
                            const task=id?await automation.ensureTask(id):(candidates.find(t=>isTerminal(t.status))||candidates[0]);
                            showReplaySurface();
                            if(task){
                                if(!task.device_ids.includes(previewDeviceId.value))previewDeviceId.value=task.device_ids[0];
                                await automation.selectReplayTask(task.id);
                            }else{
                                const demo=automation.demos.find(d=>d.device_id===previewDeviceId.value && d.status==='finished');
                                if(demo)await automation.selectReplayDemo(demo.id);
                                else{automation.replaySource='task';automation.selectedTask=null;automation.events=[];}
                            }
                        });
                    }
                    async function openDemoReplay(id){
                        await automation.attempt(async()=>{
                            await pauseActiveRecording();
                            automation.stopPlayback();
                            await automation.selectReplayDemo(id);
                            previewDeviceId.value=automation.replayDemo.device_id;
                            showReplaySurface();
                        });
                    }
                    function onReplayImageLoad(event){
                        if(event.target.naturalWidth && event.target.naturalHeight)
                            previewAspect.value=event.target.naturalHeight/event.target.naturalWidth;
                    }
                    watch(()=>automation.currentFrame,frame=>{
                        replayImageUnavailable.value=false;
                        if(previewMode.value==='replay' && frame?.width && frame?.height)
                            previewAspect.value=frame.height/frame.width;
                    });
                    function selectSchedulerRecipe(){
                        const recipe=automation.recipes.find(r=>r.id===schedulerForm.value.recipe_id);
                        schedulerForm.value.recipe_revision=recipe?.revision||null;
                        schedulerForm.value.recipe_parameters={};
                        if(recipe){
                            schedulerForm.value.task_content=recipe.name;
                            if(!schedulerForm.value.name)schedulerForm.value.name=recipe.name;
                            for(const p of recipe.parameters||[])if(p.default!==undefined)
                                schedulerForm.value.recipe_parameters[p.name]=p.default;
                        }
                    }
                    function scheduleRecipe(recipe){
                        showCreateScheduledTask();
                        schedulerForm.value.recipe_id=recipe.id;
                        selectSchedulerRecipe();
                        if(automation.editingRecipe?.id===recipe.id)
                            Object.assign(schedulerForm.value.recipe_parameters,automation.parameterValues);
                        currentPage.value='scheduler';schedulerTab.value='schedule';
                    }

                    // Lifecycle
                    onMounted(async () => {
                        console.log('App mounted, initializing...');

                        // Initialize dark mode
                        const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                        const savedTheme = localStorage.getItem('theme');
                        const initialTheme = savedTheme || (systemPrefersDark ? 'dark' : 'light');
                        darkMode.value = initialTheme === 'dark';
                        applyTheme(initialTheme);

                        // Initialize language from localStorage
                        const savedLanguage = localStorage.getItem('language');
                        currentLanguage.value = savedLanguage || 'zh';
                        window.addEventListener('resize', handleWindowResize);
                        document.addEventListener('keydown', handlePreviewKeyboard, true);

                        // Listen for system theme changes
                        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
                            if (!localStorage.getItem('theme')) {
                                darkMode.value = e.matches;
                                applyTheme(e.matches ? 'dark' : 'light');
                            }
                        });

                        await checkAuth();
                        initializeAuthenticatedApp();
                    });

                    onUnmounted(() => {
                        contextMonitor.stop();
                        if (ws) ws.close();
                        if (reconnectTimer) clearTimeout(reconnectTimer);
                        disconnectAudioStream();
                        document.body.classList.remove('preview-open', 'preview-dragging');
                        window.removeEventListener('resize', handleWindowResize);
                        document.removeEventListener('keydown', handlePreviewKeyboard, true);
                    });

                    // Watch page changes to load data
                    watch(currentPage, (page, oldPage) => {
                        if (!isAuthenticated.value) return;
                        // 离开 Chat 页面时保存滚动位置
                        if (oldPage === 'chat' && chatMessagesRef.value) {
                            chatScrollPosition = chatMessagesRef.value.scrollTop;
                        }

                        // 进入 Chat 页面时恢复滚动位置
                        if (page === 'chat') {
                            Vue.nextTick(() => {
                                if (chatMessagesRef.value && chatScrollPosition > 0) {
                                    chatMessagesRef.value.scrollTop = chatScrollPosition;
                                }
                            });
                        }

                        if (page === 'scheduler') {
                            loadScheduledTasks();
                            loadSchedulerLogs();
                        }
                        if (page === 'models') {
                            loadModels();
                            loadModelPresets();
                        }
                        if (page === 'settings') {
                            loadCredentials();
                            loadEmailConfig();
                            loadScreenshotConfig();
                            loadTelegramConfig();
                        }
                        if (page === 'rules') {
                            loadAppMappings();
                            loadTimingConfig();
                            loadActionRules();
                            loadSystemPrompts();
                        }
                        if (page === 'database') {
                            loadDbTables();
                        }
                    });

                    // Watch taskLogs for auto-scroll
                    watch(taskLogs, () => {
                        // Use nextTick equivalent with setTimeout
                        setTimeout(scrollLogsToBottom, 50);
                    }, { deep: true });

                    return {
                        cancelPreviewGesture,
                        chatContext,
                        automation,schedulerTab,activeRunTaskId,taskAcceptance,chatAcceptance,previewMode,previewToolsOnRight,replayImageUnavailable,openPreviewReplay,openDemoReplay,setPreviewMode,onReplayImageLoad,
                        schedulerRecipeDefinition,selectSchedulerRecipe,scheduleRecipe,openRecipeLibrary,openIntegratedTask,openIntegratedPreview,
                        currentPage,
                        authChecking,
                        isAuthenticated,
                        currentUsername,
                        defaultCredentials,
                        loginLoading,
                        loginError,
                        loginForm,
                        login,
                        logout,
                        credentialsForm,
                        credentialsSaving,
                        saveCredentials,
                        devices,
                        selectedDevices,
                        taskContent,
                        taskRunning,
                        taskProgress,
                        taskLogs,
                        taskScreenshot,
                        parallelExecution,
                        scheduledTasks,
                        modelServices,
                        activeModel,
                        modelPresets,
                        showModelForm,
                        modelFormMode,
                        modelForm,
                        openModelForm,
                        saveModel,
                        deleteModel,
                        testModelConfig,
                        onModelProtocolChange,
                        addFromPreset,
                        loadModelPresets,
                        getPresetsByCategory,
                        emailConfig,
                        // Rules configuration
                        appMappings,
                        timingConfig,
                        systemPrompts,
                        showAddAppModal,
                        editingApp,
                        appForm,
                        formatTimingKey,
                        updateTiming,
                        editAppMapping,
                        saveAppMapping,
                        deleteAppMapping,
                        savePrompt,
                        resetPrompt,
                        // Action rules
                        actionRules,
                        expandedActions,
                        showRuleModal,
                        editingRuleAction,
                        editingRule,
                        ruleForm,
                        toggleActionExpand,
                        toggleRuleEnabled,
                        showAddRuleModal,
                        editRuleItem,
                        saveRuleItem,
                        deleteRuleItem,
                        resetActionRules,
                        wsConnected,
                        loading,
                        toasts,
                        devicePins,
                        logContainer,
                        showSchedulerForm,
                        schedulerFormMode,
                        schedulerForm,
                        // Scheduler logs
                        schedulerLogs,
                        showLogDetailModal,
                        logDetailData,
                        loadSchedulerLogs,
                        clearAllSchedulerLogs,
                        formatLogTime,
                        showLogDetails,
                        clearTaskLogs,
                        // Chat
                        chatMessages,
                        chatInput,
                        chatDeviceId,
                        chatRunning,
                        chatMessagesRef,
                        canSendChatMessage,
                        isAdbCommandMode,
                        isDeviceMentionMode,
                        filteredAdbQuickCommands,
                        filteredDeviceMentionSuggestions,
                        activeAdbSuggestionCommand,
                        activeDeviceMentionSuggestionId,
                        applyAdbQuickCommand,
                        applyDeviceMentionSuggestion,
                        handleChatInputKeydown,
                        syncChatCursor,
                        chatAutoEmail,
                        complexTaskMode,
                        debugMode,
                        darkMode,
                        toggleDarkMode,
                        // Cloudflare Tunnel
                        tunnelStatus,
                        tunnelUrl,
                        tunnelError,
                        toggleTunnel,
                        copyTunnelUrl,
                        currentLanguage,
                        toggleLanguage,
                        t,
                        subtaskTimeoutSeconds,
                        subtaskCountdown,
                        formatTaskLogPreview,
                        sendChatMessage,
                        retryMessage,
                        skipSubtask,
                        // TodoList confirmation functions
                        confirmTodoList,
                        cancelTodoList,
                        moveTodoUp,
                        moveTodoDown,
                        deleteTodo,
                        autoResizeTextarea,
                        stopChatTask,
                        // Tap preview (debug mode)
                        showTapPreview,
                        tapPreviewData,
                        tapPreviewAdjustedX,
                        tapPreviewAdjustedY,
                        confirmTapPreview,
                        cancelTapPreview,
                        handleTapPreviewClick,
                        onChatDeviceChange,
                        adjustChatInputHeight,
                        openTaskDetail,
                        showTaskDetail,
                        taskDetailData,
                        // Chat sessions
                        chatSessions,
                        currentSessionId,
                        sessionSearchQuery,
                        filteredSessions,
                        createNewSession,
                        switchSession,
                        deleteSession,
                        clearAllSessions,
                        formatSessionTime,
                        formatMsgTime,
                        // Phone preview
                        showPhonePreview,
                        previewDeviceId,
                        previewImage,
                        previewLoading,
                        previewIsLandscape,
                        phonePreviewStyle,
                        refreshPreview,
                        openPhonePreview,
                        onPreviewDeviceChange,
                        startDragPreview,
                        startResizePreview,
                        // Scrcpy stream
                        streamConnected,
                        streamConnecting,
                        streamReady,
                        streamLoadingText,
                        streamOrientationSwitching,
                        streamSwitchProgress,
                        streamFps,
                        streamMaxSize,
                        streamTargetFps,
                        streamBitRate,
                        streamAutoAdapt,
                        streamUseScrcpyControl,
                        streamControlActive,
                        streamAudioEnabled,
                        streamAudioConnected,
                        streamVideoBitrateLabel,
                        streamAudioBitrateLabel,
                        streamTotalBitrateLabel,
                        streamLatencyMs,
                        streamLatencyJitterMs,
                        streamFrameJitterMs,
                        streamAudioJitterMs,
                        canvasWidth,
                        canvasHeight,
                        previewCanvas,
                        connectStream,
                        disconnectStream,
                        applyStreamSettings,
                        toggleScrcpyControlInject,
                        toggleAudioPassthrough,
                        onCanvasMouseDown,
                        onCanvasMouseMove,
                        onCanvasMouseUp,
                        onCanvasWheel,
                        onCanvasTouchStart,
                        onCanvasTouchMove,
                        onCanvasTouchEnd,
                        sendKey,
                        // Functions
                        showToast,
                        systemAlerts,
                        dismissSystemAlert,
                        refreshDevices,
                        toggleDeviceSelection,
                        selectAllDevices,
                        getDeviceName,
                        unlockDevice,
                        lockDevice,
                        updateDevicePin,
                        saveDevicePin,
                        loadDevicePins,
                        pinInputValues,
                        showPinFor,
                        toggleShowPin,
                        // Wireless pairing
                        pairAddress,
                        pairCode,
                        connectAddress,
                        pairingLoading,
                        connectingLoading,
                        deviceLogs,
                        wirelessPair,
                        tcpConnect,
                        disconnectDevice,
                        // APK install
                        apkTargetDevice,
                        apkFile,
                        apkInstalling,
                        apkLogs,
                        apkFileInput,
                        onApkFileSelect,
                        installApk,
                        // Monitor (remote camera)
                        monitorDeviceId,
                        monitorStarting,
                        monitorMessage,
                        monitorSuccess,
                        startCameraMonitor,
                        openMonitorPreview,
                        ipCamStreamUrl,
                        ipCamImgError,
                        ipWebcamLaunching,
                        ipCamProxyUrl,
                        suggestIpCamUrl,
                        launchIpWebcamApp,
                        streamConfig,
                        gridConfigExpanded,
                        streamErrors,
                        loadStreamConfig,
                        saveStreamConfig,
                        streamMjpegUrl,
                        gridImgRefs,
                        gridRecordCanvas,
                        gridRecording,
                        hasAnyGridStream,
                        setGridImgRef,
                        startGridRecord,
                        stopGridRecord,
                        // File manager
                        fileDevice,
                        filePath,
                        fileList,
                        fileLoading,
                        uploadSelectedFile,
                        fileUploading,
                        uploadFileInput,
                        loadFiles,
                        navigateTo,
                        goUp,
                        formatFileSize,
                        isImageFile,
                        isVideoFile,
                        isAudioFile,
                        downloadFile,
                        onUploadFileSelect,
                        uploadFile,
                        deleteFileConfirm,
                        runTask,
                        stopTask,
                        loadScheduledTasks,
                        toggleScheduledTask,
                        runScheduledTaskNow,
                        deleteScheduledTask,
                        showCreateScheduledTask,
                        editScheduledTask,
                        cancelSchedulerForm,
                        saveScheduledTask,
                        formatScheduleType,
                        loadModels,
                        activateModel,
                        testModel,
                        loadEmailConfig,
                        saveEmailConfig,
                        testEmail,
                        // Screenshot config
                        screenshotConfig,
                        loadScreenshotConfig,
                        saveScreenshotConfig,
                        resetScreenshotConfig,
                        // Telegram Bot config
                        telegramConfig,
                        telegramAllowedUsersStr,
                        telegramBotInfo,
                        loadTelegramConfig,
                        saveTelegramConfig,
                        testTelegramConnection,
                        startTelegramBot,
                        stopTelegramBot,
                        // Database Management
                        dbTables,
                        dbCurrentTable,
                        dbColumns,
                        dbRows,
                        dbSearch,
                        dbSortBy,
                        dbSortOrder,
                        dbPagination,
                        dbShowFormModal,
                        dbFormMode,
                        dbFormData,
                        dbShowDeleteConfirm,
                        dbVisibleColumns,
                        dbPageRange,
                        loadDbTables,
                        selectDbTable,
                        loadDbRows,
                        dbSearchDebounce,
                        toggleDbSort,
                        dbGoToPage,
                        truncateCell,
                        isLongField,
                        openDbAddModal,
                        openDbEditModal,
                        openDbDeleteConfirm,
                        saveDbRow,
                        confirmDeleteDbRow,
                    };
                },
            });

            app.mount('#app');
            console.log('Vue app mounted successfully');
        }

        // Initialize after page load
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                setTimeout(initApp, 100);
            });
        } else {
            setTimeout(initApp, 100);
        }
