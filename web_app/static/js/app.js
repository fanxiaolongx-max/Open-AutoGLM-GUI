/**
 * AutoGLM Web Interface - Main Application
 * Vue.js based frontend for the web server
 */

const { createApp, ref, reactive, computed, onMounted, onUnmounted, watch } = Vue;

const app = createApp({
    setup() {
        // State
        const currentPage = ref('devices');
        const devices = ref([]);
        const selectedDevices = ref([]);
        const taskContent = ref('');
        const taskRunning = ref(false);
        const taskProgress = ref(0);
        const taskLogs = ref([]);
        const schedulerLogs = ref([]);
        const scheduledTasks = ref([]);
        const modelServices = ref([]);
        const activeModel = ref(null);

        // Chat State
        const chatMessages = ref([]);
        const chatSessions = ref([]);
        const currentSessionId = ref(null);
        const chatInput = ref('');
        const chatLoading = ref(false);
        const chatDeviceId = ref('');
        const complexTaskMode = ref(false);
        const chatAutoEmail = ref(false);
        const chatRunning = ref(false);

        const emailConfig = ref({});
        const wsConnected = ref(false);
        const loading = ref(false);

        // WebSocket
        let ws = null;
        let reconnectTimer = null;

        // Toast notifications
        const toasts = ref([]);

        function showToast(message, type = 'success') {
            const id = Date.now();
            toasts.value.push({ id, message, type });
            setTimeout(() => {
                toasts.value = toasts.value.filter(t => t.id !== id);
            }, 3000);
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
                    throw new Error(data.detail || 'API Error');
                }
                return data;
            } catch (error) {
                showToast(error.message, 'error');
                throw error;
            }
        }

        // WebSocket connection
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;

            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                wsConnected.value = true;
                console.log('WebSocket connected');
            };

            ws.onclose = () => {
                wsConnected.value = false;
                console.log('WebSocket disconnected');
                // Reconnect after 3 seconds
                reconnectTimer = setTimeout(connectWebSocket, 3000);
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
        }

        function handleWebSocketMessage(data) {
            switch (data.type) {
                case 'init':
                    if (data.task_status) {
                        taskRunning.value = data.task_status.running;
                        chatRunning.value = data.task_status.running && data.task_status.task?.task_type === 'chat';
                        if (data.task_status.task) {
                            taskProgress.value = data.task_status.task.progress || 0;
                        }
                    }
                    break;
                case 'task_log':
                    // For chat tasks, update the last assistant message
                    if (data.task_type === 'chat') {
                        const lastMsg = chatMessages.value[chatMessages.value.length - 1];
                        if (lastMsg && lastMsg.role === 'assistant') {
                            if (!lastMsg.logs) lastMsg.logs = [];
                            lastMsg.logs.push(data.message);
                            // Auto-scroll
                            setTimeout(() => {
                                const el = document.querySelector('.chat-messages');
                                if (el) el.scrollTop = el.scrollHeight;
                            }, 50);
                        }
                    } else if (data.task_type !== 'scheduled') {
                        // Regular task logs
                        taskLogs.value.push({
                            time: new Date().toLocaleTimeString(),
                            message: data.message,
                        });
                    }
                    break;
                case 'task_progress':
                    taskProgress.value = data.progress;
                    break;
                case 'task_finished':
                    taskRunning.value = false;
                    chatRunning.value = false;
                    // Update last assistant message status
                    const lastMsg = chatMessages.value[chatMessages.value.length - 1];
                    if (lastMsg && lastMsg.role === 'assistant' && lastMsg.status === 'running') {
                        lastMsg.status = data.success ? 'success' : 'error';
                        lastMsg.content = data.success ? '任务完成' : '任务失败';
                        // Add screenshot if available
                        if (data.screenshot_id) {
                            // Use the saved screenshot URL
                            lastMsg.screenshots = [{
                                image_url: `/api/chat/screenshots/${data.screenshot_id}`
                            }];
                        } else if (data.screenshot) {
                            // Fallback to base64 (legacy)
                            lastMsg.screenshots = [{
                                image_url: `data:image/png;base64,${data.screenshot}`
                            }];
                        }
                    }
                    // Reload sessions to get updated data
                    loadChatSessions();
                    showToast(data.message, data.success ? 'success' : 'error');
                    break;
                case 'devices':
                    devices.value = data.devices;
                    break;
                case 'ping':
                    ws.send(JSON.stringify({ type: 'pong' }));
                    break;
            }
        }

        // Device functions
        async function refreshDevices() {
            loading.value = true;
            try {
                const data = await apiCall('/api/devices/refresh', { method: 'POST' });
                devices.value = data;
                showToast(`Found ${data.length} device(s)`);
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

        async function getScreenshot(deviceId) {
            try {
                const data = await apiCall(`/api/devices/${deviceId}/screenshot/base64`);
                return `data:image/png;base64,${data.image}`;
            } catch {
                return null;
            }
        }

        async function unlockDevice(deviceId) {
            try {
                await apiCall(`/api/devices/${deviceId}/unlock`, { method: 'POST' });
                showToast('Device unlocked');
            } catch (error) {
                showToast('Failed to unlock device', 'error');
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

            try {
                await apiCall('/api/tasks/run', {
                    method: 'POST',
                    body: JSON.stringify({
                        task_content: taskContent.value,
                        device_ids: selectedDevices.value,
                    }),
                });
                taskRunning.value = true;
                showToast('Task started');
            } catch (error) {
                showToast('Failed to start task', 'error');
            }
        }

        async function stopTask() {
            try {
                await apiCall('/api/tasks/stop', { method: 'POST' });
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

        async function clearAllSchedulerLogs() {
            if (!confirm('Are you sure you want to clear all scheduler logs?')) return;
            try {
                await apiCall('/api/scheduler/logs', { method: 'DELETE' });
                schedulerLogs.value = [];
                showToast('Logs cleared');
            } catch (error) {
                showToast('Failed to clear logs', 'error');
            }
        }

        async function loadSchedulerLogs() {
            try {
                const data = await apiCall('/api/scheduler/logs?limit=50');
                schedulerLogs.value = data.logs;
            } catch (error) {
                console.error('Failed to load scheduler logs:', error);
            }
        }

        // Chat functions
        async function loadChatSessions() {
            try {
                const data = await apiCall('/api/chat/sessions?limit=50');
                chatSessions.value = data.map(s => ({
                    id: s.id,
                    title: s.title || '新会话',
                    deviceId: s.device_id,
                    status: s.status,
                    updatedAt: s.updated_at,
                    totalTokens: s.total_tokens || 0
                }));
            } catch (error) {
                console.error('Failed to load chat sessions:', error);
            }
        }

        async function loadSessionMessages(sessionId) {
            try {
                const data = await apiCall(`/api/chat/sessions/${sessionId}/detail`);
                if (data && data.messages) {
                    chatMessages.value = data.messages.map(msg => ({
                        id: msg.id,
                        role: msg.role,
                        content: msg.content,
                        timestamp: msg.created_at,
                        logs: msg.logs ? msg.logs.map(l => l.content) : [],
                        screenshots: msg.screenshots || [],
                        status: msg.role === 'assistant' ? 'success' : null
                    }));
                    // Scroll to bottom
                    setTimeout(() => {
                        const el = document.querySelector('.chat-messages');
                        if (el) el.scrollTop = el.scrollHeight;
                    }, 100);
                }
            } catch (error) {
                console.error('Failed to load session messages:', error);
            }
        }

        async function switchSession(sessionId) {
            currentSessionId.value = sessionId;
            await loadSessionMessages(sessionId);
        }

        async function createNewSession() {
            // Clear current session - will create new one on first message
            currentSessionId.value = null;
            chatMessages.value = [];
        }

        async function deleteSession(sessionId) {
            if (!confirm('确定删除此会话？')) return;
            try {
                await apiCall(`/api/chat/sessions/${sessionId}`, { method: 'DELETE' });
                await loadChatSessions();
                if (currentSessionId.value === sessionId) {
                    currentSessionId.value = null;
                    chatMessages.value = [];
                }
                showToast('会话已删除');
            } catch (error) {
                showToast('删除失败', 'error');
            }
        }

        function formatSessionTime(timestamp) {
            if (!timestamp) return '';
            const date = new Date(timestamp);
            const now = new Date();
            const diff = now - date;
            if (diff < 86400000) { // Less than 24 hours
                return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
            } else if (diff < 604800000) { // Less than 7 days
                const days = Math.floor(diff / 86400000);
                return `${days}天前`;
            } else {
                return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
            }
        }

        async function loadChatHistory() {
            // Load sessions list
            await loadChatSessions();
            // If there's a current session, load its messages
            if (currentSessionId.value) {
                await loadSessionMessages(currentSessionId.value);
            } else if (chatSessions.value.length > 0) {
                // Auto-select the most recent session
                currentSessionId.value = chatSessions.value[0].id;
                await loadSessionMessages(currentSessionId.value);
            }
        }

        async function sendChatMessage() {
            if (!chatInput.value.trim() || chatRunning.value) return;

            const content = chatInput.value;
            chatInput.value = '';
            chatRunning.value = true;

            try {
                // 1. Add user message immediately to UI
                const userMsg = {
                    role: 'user',
                    content: content,
                    timestamp: new Date().toISOString()
                };
                chatMessages.value.push(userMsg);

                // Add placeholder for assistant response
                const assistantMsg = {
                    role: 'assistant',
                    content: '',
                    status: 'running',
                    logs: [],
                    screenshots: [],
                    timestamp: new Date().toISOString()
                };
                chatMessages.value.push(assistantMsg);

                // Scroll
                setTimeout(() => {
                    const el = document.querySelector('.chat-messages');
                    if (el) el.scrollTop = el.scrollHeight;
                }, 100);

                // 2. Run Task (Chat Mode) - backend will create session automatically
                let targetDevice = chatDeviceId.value;
                if (!targetDevice && selectedDevices.value.length > 0) {
                    targetDevice = selectedDevices.value[0];
                }
                if (!targetDevice && devices.value.length > 0) {
                    targetDevice = devices.value[0].id;
                }

                if (targetDevice) {
                    await apiCall('/api/tasks/run', {
                        method: 'POST',
                        body: JSON.stringify({
                            task_content: content,
                            device_ids: [targetDevice],
                            task_type: 'chat',
                            send_email: chatAutoEmail.value,
                            no_auto_lock: complexTaskMode.value
                        }),
                    });
                } else {
                    showToast('请先选择设备', 'warning');
                    chatRunning.value = false;
                    // Remove placeholder
                    chatMessages.value.pop();
                }

            } catch (error) {
                showToast('发送失败', 'error');
                chatRunning.value = false;
                // Remove placeholder on error
                if (chatMessages.value.length > 0 && chatMessages.value[chatMessages.value.length - 1].status === 'running') {
                    chatMessages.value.pop();
                }
            }
        }

        async function stopChatTask() {
            try {
                await apiCall('/api/tasks/stop', { method: 'POST' });
                showToast('已发送停止信号');
            } catch (error) {
                showToast('停止失败', 'error');
            }
        }

        function openTaskDetail(msg) {
            // Open modal with full logs and screenshots
            const modal = document.createElement('div');
            modal.className = 'task-detail-modal';
            modal.innerHTML = `
                <div class="task-detail-content">
                    <div class="task-detail-header">
                        <h3>📋 执行详情</h3>
                        <button class="close-btn" onclick="this.closest('.task-detail-modal').remove()">✕</button>
                    </div>
                    <div class="task-detail-body">
                        <div class="task-detail-logs">
                            <h4>执行日志</h4>
                            <div class="logs-container">
                                ${(msg.logs || []).map(log => `<div class="log-line">${log}</div>`).join('')}
                            </div>
                        </div>
                        ${msg.screenshots && msg.screenshots.length > 0 ? `
                            <div class="task-detail-screenshots">
                                <h4>📸 截图</h4>
                                <div class="screenshots-grid">
                                    ${msg.screenshots.map(s => `
                                        <img src="${s.image_url}" alt="Screenshot" class="screenshot-img"
                                             onclick="window.open('${s.image_url}', '_blank')">
                                    `).join('')}
                                </div>
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
            modal.addEventListener('click', (e) => {
                if (e.target === modal) modal.remove();
            });
        }

        function formatMsgTime(timestamp) {
            if (!timestamp) return '';
            const date = new Date(timestamp);
            return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        }

        function adjustChatInputHeight(event) {
            const textarea = event.target;
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
        }

        async function clearChatHistory() {
            if (!confirm('Clear chat history?')) return;
            try {
                await apiCall('/api/chat/history', { method: 'DELETE' });
                chatMessages.value = [];
                showToast('Chat history cleared');
            } catch (error) {
                showToast('Failed to clear history', 'error');
            }
        }

        function onChatDeviceChange() {
            // handle device change if needed
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

        // Lifecycle
        onMounted(() => {
            connectWebSocket();
            refreshDevices();
            loadModels();
        });

        onUnmounted(() => {
            if (ws) ws.close();
            if (reconnectTimer) clearTimeout(reconnectTimer);
        });

        // Watch page changes to load data
        watch(currentPage, (page) => {
            if (page === 'scheduler') {
                loadScheduledTasks();
                loadSchedulerLogs();
            }
            if (page === 'models') loadModels();
            if (page === 'settings') loadEmailConfig();
            if (page === 'chat') loadChatHistory();
        });

        return {
            // State
            currentPage,
            devices,
            selectedDevices,
            taskContent,
            taskRunning,
            taskProgress,
            taskLogs,
            schedulerLogs,
            scheduledTasks,
            modelServices,
            activeModel,
            emailConfig,
            wsConnected,
            loading,
            toasts,

            // Chat State
            chatMessages,
            chatSessions,
            chatInput,
            chatLoading,
            chatDeviceId,
            complexTaskMode,
            chatAutoEmail,

            // Methods
            showToast,
            refreshDevices,
            toggleDeviceSelection,
            selectAllDevices,
            getScreenshot,
            unlockDevice,
            runTask,
            stopTask,
            loadScheduledTasks,
            toggleScheduledTask,
            runScheduledTaskNow,
            deleteScheduledTask,
            clearAllSchedulerLogs,
            loadModels,
            activateModel,
            testModel,
            loadEmailConfig,
            saveEmailConfig,
            testEmail,
            sendChatMessage,
            clearChatHistory,
            onChatDeviceChange,
        };
    },
});

app.mount('#app');
