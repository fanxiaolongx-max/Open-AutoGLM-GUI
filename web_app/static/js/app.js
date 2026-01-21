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
        const scheduledTasks = ref([]);
        const modelServices = ref([]);
        const activeModel = ref(null);
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
                        if (data.task_status.task) {
                            taskProgress.value = data.task_status.task.progress || 0;
                        }
                    }
                    break;
                case 'task_log':
                    taskLogs.value.push({
                        time: new Date().toLocaleTimeString(),
                        message: data.message,
                    });
                    break;
                case 'task_progress':
                    taskProgress.value = data.progress;
                    break;
                case 'task_finished':
                    taskRunning.value = false;
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
            if (page === 'scheduler') loadScheduledTasks();
            if (page === 'models') loadModels();
            if (page === 'settings') loadEmailConfig();
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
            scheduledTasks,
            modelServices,
            activeModel,
            emailConfig,
            wsConnected,
            loading,
            toasts,

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
            loadModels,
            activateModel,
            testModel,
            loadEmailConfig,
            saveEmailConfig,
            testEmail,
        };
    },
});

app.mount('#app');
