// Share one persistent compaction journal between live messages and restored history.
export function mergeContextEvents(messages, events) {
    const existing = new Map(messages.filter(m => m.source === 'context_compaction').map(m => [m.id,m]));
    const merged = messages.filter(m => m.source !== 'context_compaction');
    for (const event of events) {
        const entry = existing.get(event.id) || {};
        Object.assign(entry,event,{timestamp:event.created_at});
        const anchor = merged.findIndex(m => m.id === event.context_event?.request_message_id);
        merged.splice(anchor < 0 ? merged.length : anchor, 0, entry);
    }
    return merged;
}

export function createContextMonitor({apiCall, sessionId, messages, state}) {
    let timer, ticket = 0, applied = 0;
    function stop() { clearInterval(timer); timer = undefined; }
    function accept(data, id) {
        applied = ++ticket;
        apply(data,id);
    }
    function apply(data, id) {
        if (!data || sessionId.value !== id) return;
        state.value = data;
        messages.value = mergeContextEvents(messages.value, data.events || []);
    }
    async function refresh(id = sessionId.value) {
        if (!id) { state.value = null; return; }
        const current = ++ticket;
        try {
            const data = await apiCall(`/api/chat/sessions/${id}/context`);
            if (current < applied || sessionId.value !== id) return;
            applied = current;
            apply(data,id);
        } catch (_) { stop(); }
    }
    function start(id) {
        stop();
        void refresh(id);
        timer = setInterval(() => { void refresh(id); }, 1000);
    }
    return {refresh,start,stop,accept};
}
