/**
 * Shared state, persistence, width clamping, and smooth rAF drag-resize
 * controller for both the main navigation sidebar and chat sessions sidebar.
 */

export const SIDEBAR_CONFIG = {
    nav: {
        defaultWidth: 240,
        collapsedWidth: 68,
        minWidth: 196,
        maxWidth: 400,
        minRemainingViewport: 440,
        cssVar: '--nav-sidebar-width',
        widthStorageKey: 'autoglm_nav_sidebar_width',
        collapsedStorageKey: 'autoglm_nav_sidebar_collapsed',
    },
    chat: {
        defaultWidth: 220,
        collapsedWidth: 60,
        minWidth: 184,
        maxWidth: 480,
        minRemainingViewport: 300,
        cssVar: '--chat-sidebar-width',
        widthStorageKey: 'autoglm_chat_sidebar_width',
        collapsedStorageKey: 'autoglm_chat_sidebar_collapsed',
    },
};

export function getSidebarConfig(key) {
    const config = SIDEBAR_CONFIG[key];
    if (!config) {
        throw new Error(`Unknown sidebar key: ${key}`);
    }
    return config;
}

export function computeMaxSidebarWidth(key, viewportWidth, state = {}) {
    const config = getSidebarConfig(key);
    if (!Number.isFinite(viewportWidth) || viewportWidth <= 0) {
        return config.maxWidth;
    }
    let reserved = config.minRemainingViewport;
    if (key === 'chat') {
        const navConfig = SIDEBAR_CONFIG.nav;
        const navUsed = state.navCollapsed
            ? navConfig.collapsedWidth
            : clampSidebarWidth('nav', state.navWidth ?? navConfig.defaultWidth);
        reserved += navUsed;
    }
    const available = Math.round(viewportWidth - reserved);
    return Math.max(config.minWidth, Math.min(config.maxWidth, available));
}

export function clampSidebarWidth(key, rawWidth, maxWidthOverride = null) {
    const config = getSidebarConfig(key);
    const parsed = typeof rawWidth === 'number' ? rawWidth : Number(rawWidth);
    if (!Number.isFinite(parsed) || parsed <= 0) {
        return config.defaultWidth;
    }
    const maxAllowed = Number.isFinite(maxWidthOverride)
        ? Math.max(config.minWidth, Math.round(maxWidthOverride))
        : config.maxWidth;
    return Math.min(maxAllowed, Math.max(config.minWidth, Math.round(parsed)));
}

export function resolveSidebarWidth(key, collapsed, width, viewportWidth, state = {}) {
    const config = getSidebarConfig(key);
    if (collapsed) {
        return config.collapsedWidth;
    }
    const maxAllowed = computeMaxSidebarWidth(key, viewportWidth, state);
    return clampSidebarWidth(key, width, maxAllowed);
}

function parseStoredBool(raw) {
    return raw === 'true' || raw === '1';
}

export function loadSidebarState(storage) {
    const state = {};
    for (const [key, config] of Object.entries(SIDEBAR_CONFIG)) {
        let rawWidth = null;
        let rawCollapsed = null;
        if (storage) {
            try {
                rawWidth = storage.getItem(config.widthStorageKey);
                rawCollapsed = storage.getItem(config.collapsedStorageKey);
            } catch (_) {
                rawWidth = null;
                rawCollapsed = null;
            }
        }
        state[key] = {
            width: clampSidebarWidth(key, rawWidth === null || rawWidth === '' ? NaN : rawWidth),
            collapsed: parseStoredBool(rawCollapsed),
        };
    }
    return state;
}

export function saveSidebarState(storage, key, { width, collapsed }) {
    if (!storage) return;
    const config = getSidebarConfig(key);
    try {
        if (width !== undefined) {
            storage.setItem(config.widthStorageKey, String(clampSidebarWidth(key, width)));
        }
        if (collapsed !== undefined) {
            storage.setItem(config.collapsedStorageKey, collapsed ? 'true' : 'false');
        }
    } catch (_) {
        // Ignore storage quota or private-browsing errors.
    }
}

export function getSessionCompactLabel(session, fallback = '新') {
    const title = String(session?.title || '').trim();
    if (!title) return fallback;

    const emojiMatch = title.match(/^(\p{Extended_Pictographic}(?:\uFE0F|\u200D\p{Extended_Pictographic})*)/u);
    if (emojiMatch) {
        return emojiMatch[1];
    }

    const firstChar = Array.from(title)[0] || fallback;
    if (/[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]/u.test(firstChar)) {
        return firstChar;
    }

    const compact = title.replace(/\s+/g, '');
    return Array.from(compact).slice(0, 2).join('') || fallback;
}

export function createSidebarController({
    navWidth,
    navCollapsed,
    chatWidth,
    chatCollapsed,
    activeDrag,
    getContainerEl = () => (typeof document !== 'undefined' ? document.querySelector('.app-container') : null),
    getViewportWidth = () => (typeof window !== 'undefined' ? window.innerWidth : 1440),
    storage = typeof localStorage !== 'undefined' ? localStorage : null,
    win = typeof window !== 'undefined' ? window : null,
    doc = typeof document !== 'undefined' ? document : null,
    requestFrame = typeof requestAnimationFrame === 'function' ? requestAnimationFrame : (cb) => setTimeout(cb, 0),
    cancelFrame = typeof cancelAnimationFrame === 'function' ? cancelAnimationFrame : clearTimeout,
} = {}) {
    const refs = {
        nav: { width: navWidth, collapsed: navCollapsed },
        chat: { width: chatWidth, collapsed: chatCollapsed },
    };

    let dragSession = null;

    function getStateSnapshot() {
        return {
            navWidth: navWidth.value,
            navCollapsed: navCollapsed.value,
            chatWidth: chatWidth.value,
            chatCollapsed: chatCollapsed.value,
        };
    }

    function applyCssWidth(key, widthPx) {
        const containerEl = getContainerEl();
        if (containerEl && containerEl.style) {
            containerEl.style.setProperty(getSidebarConfig(key).cssVar, `${widthPx}px`);
        }
    }

    function setCollapsed(key, collapsed) {
        const entry = refs[key];
        if (!entry) return;
        entry.collapsed.value = Boolean(collapsed);
        saveSidebarState(storage, key, {
            width: entry.width.value,
            collapsed: entry.collapsed.value,
        });
    }

    function toggle(key) {
        const entry = refs[key];
        if (!entry) return;
        setCollapsed(key, !entry.collapsed.value);
    }

    function resetWidth(key) {
        const entry = refs[key];
        if (!entry) return;
        const config = getSidebarConfig(key);
        const clampedDefault = clampSidebarWidth(
            key,
            config.defaultWidth,
            computeMaxSidebarWidth(key, getViewportWidth(), getStateSnapshot()),
        );
        entry.width.value = clampedDefault;
        applyCssWidth(key, clampedDefault);
        saveSidebarState(storage, key, {
            width: clampedDefault,
            collapsed: entry.collapsed.value,
        });
    }

    function detachDragListeners() {
        if (!dragSession || !win) return;
        win.removeEventListener('pointermove', dragSession.onMove);
        win.removeEventListener('pointerup', dragSession.onEnd);
        win.removeEventListener('pointercancel', dragSession.onEnd);
        win.removeEventListener('blur', dragSession.onEnd);
    }

    function finishDrag() {
        if (!dragSession) return;
        const { key, rafId, applyPendingWidth } = dragSession;
        if (rafId !== null) {
            cancelFrame(rafId);
            dragSession.rafId = null;
        }
        applyPendingWidth();
        detachDragListeners();
        dragSession = null;

        if (activeDrag) {
            activeDrag.value = '';
        }
        if (doc?.body?.classList) {
            doc.body.classList.remove('sidebar-resizing');
        }
        saveSidebarState(storage, key, {
            width: refs[key].width.value,
            collapsed: refs[key].collapsed.value,
        });
    }

    function startResize(key, event) {
        const entry = refs[key];
        if (!entry || entry.collapsed.value) return;
        if (event && event.button !== undefined && event.button !== 0) return;
        if (event && typeof event.preventDefault === 'function') {
            event.preventDefault();
        }

        // Cancel any lingering session before starting a fresh drag.
        if (dragSession) {
            finishDrag();
        }

        const startX = Number(event?.clientX ?? 0);
        const maxWidth = computeMaxSidebarWidth(key, getViewportWidth(), getStateSnapshot());
        const startWidth = clampSidebarWidth(key, entry.width.value, maxWidth);

        let pendingClientX = startX;
        let lastAppliedWidth = startWidth;

        const applyPendingWidth = () => {
            if (!dragSession) return;
            dragSession.rafId = null;
            const liveMax = computeMaxSidebarWidth(key, getViewportWidth(), getStateSnapshot());
            const nextWidth = clampSidebarWidth(key, startWidth + (pendingClientX - startX), liveMax);
            if (nextWidth !== lastAppliedWidth) {
                lastAppliedWidth = nextWidth;
                entry.width.value = nextWidth;
                applyCssWidth(key, nextWidth);
            }
        };

        const onMove = (moveEvent) => {
            pendingClientX = Number(moveEvent?.clientX ?? pendingClientX);
            if (dragSession && dragSession.rafId === null) {
                dragSession.rafId = requestFrame(applyPendingWidth);
            }
        };

        const onEnd = () => {
            finishDrag();
        };

        dragSession = {
            key,
            rafId: null,
            applyPendingWidth,
            onMove,
            onEnd,
        };

        if (activeDrag) {
            activeDrag.value = key;
        }
        if (doc?.body?.classList) {
            doc.body.classList.add('sidebar-resizing');
        }
        if (win) {
            win.addEventListener('pointermove', onMove);
            win.addEventListener('pointerup', onEnd);
            win.addEventListener('pointercancel', onEnd);
            win.addEventListener('blur', onEnd);
        }
    }

    function cleanup() {
        if (dragSession) {
            finishDrag();
        }
    }

    return {
        toggle,
        setCollapsed,
        resetWidth,
        startResize,
        cleanup,
    };
}
