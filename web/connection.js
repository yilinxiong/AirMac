/* AirMac connection: browser and Node compatible; initialization is explicit. */
(function(root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory;
    else (root.AirMacModules ||= {})['connection'] = factory;
})(globalThis, function(ctx) {
    'use strict';
    const {window, document, navigator, localStorage, WebSocket, TextEncoder, Date, setTimeout, clearTimeout, setInterval, clearInterval, requestAnimationFrame, cancelAnimationFrame} = ctx.env;
    const AirMacState = ctx.state;
    const t = (...args) => ctx.i18n.t(...args);
    const showGestureFeedback = (...args) => ctx.settings.showGestureFeedback(...args);
    const showPairing = (...args) => ctx.pairing.showPairing(...args);
    const clearCredentials = () => ctx.credentials.clear();
    const failPendingProjection = (...args) => ctx.projection.failPendingProjection(...args);
    const finishProjection = (...args) => ctx.projection.finishProjection(...args);
    const restoreProjectionState = () => ctx.projection.restoreProjectionState();
    let reconnectTimer = null;
    const reconnectBackoff = new AirMacState.ReconnectBackoff();
    let shouldReconnect = true;
    let isPageSuspended = document.hidden;
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws`;
    let ws;
    let isConnected = false;
    let lastServerActivity = Date.now();
    let reconnectProbeTimer = null;
    const hintText = document.getElementById('status-text');
    const spinner = document.getElementById('status-spinner');
    const connectionStatus = document.getElementById('connection-status');
    const latencyTracker = new AirMacState.LatencyTracker();
    let lastConnectionStatus = { state: 'offline', labelKey: 'statusPairing', latency: null };
    let lastHint = { key: '', values: {} };
    let serverInfo = null;
    let heartbeatTimer = null;

    function acceptHello(data) {
        const version = data.protocol_version ?? 1;
        if (version !== 1 && version !== 2) return false;
        const heartbeat = data.heartbeat_interval_ms ?? 5000;
        if (!Number.isInteger(heartbeat) || heartbeat < 1000 || heartbeat > 60000) return false;
        serverInfo = {protocolVersion: version, heartbeatInterval: heartbeat,
            capabilities: Array.isArray(data.capabilities) ? data.capabilities.filter(v => typeof v === 'string') : []};
        clearInterval(heartbeatTimer);
        heartbeatTimer = setInterval(probeConnection, heartbeat);
        return true;
    }

    function refreshConnectionStatus() {
        const { state, labelKey, latency } = lastConnectionStatus;
        connectionStatus.setStatus(state, t(labelKey), state === 'online' ? latency : null);
    }

    function setConnectionStatus(state, labelKey, latency = latencyTracker.value) {
        lastConnectionStatus = {
            state,
            labelKey,
            latency: state === 'online' ? latency : null,
        };
        refreshConnectionStatus();
    }

    function setHint(key, values = {}) {
        lastHint = { key, values };
        hintText.textContent = key ? t(key, values) : '';
    }

    function connect() {
        if (isPageSuspended || document.hidden) return;
        if (!ctx.credentials.deviceId || !ctx.credentials.deviceToken) {
            showPairing();
            return;
        }
        if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
            return;
        }
        clearTimeout(reconnectTimer);
        clearTimeout(reconnectProbeTimer);
        shouldReconnect = true;
        isConnected = false;
        latencyTracker.reset();
        setConnectionStatus('connecting', 'statusConnecting');
        setHint('hintConnecting');
        spinner.style.display = 'block';
        const socket = new WebSocket(wsUrl);
        ws = socket;
        socket.onopen = () => {
            lastServerActivity = Date.now();
            socket.send(JSON.stringify({
                type: 'authenticate',
                device_id: ctx.credentials.deviceId,
                token: ctx.credentials.deviceToken,
                protocol_version: 2,
                client_version: '0.3.0-web'
            }));
        };
        socket.onclose = (e) => {
            if (ws !== socket) return;
            ws = null;
            isConnected = false;
            clearTimeout(reconnectProbeTimer);
            failPendingProjection('hintProjectionInterrupted');
            if (e.code === 4003) {
                clearCredentials();
                setConnectionStatus('error', 'statusAuthExpired');
                spinner.style.display = 'none';
                showPairing(t('hintCredentialExpired'));
            } else if (e.code === 4009) {
                setConnectionStatus('error', 'statusBusy');
                setHint('hintBusy');
                spinner.style.display = 'block';
                scheduleReconnect(3000);
            } else if (e.code === 4012) {
                setConnectionStatus('connecting', 'statusReconnect');
                setHint('hintRateLimited');
                scheduleReconnect(60000);
            } else if (e.code === 4011) {
                shouldReconnect = false;
                spinner.style.display = 'none';
                setConnectionStatus('error', 'statusVersionMismatch');
                setHint('hintVersionMismatch');
            } else if (e.code === 4010) {
                shouldReconnect = false;
                setConnectionStatus('offline', 'statusReplaced');
                setHint('hintReplaced');
                spinner.style.display = 'none';
            } else if (shouldReconnect) {
                setConnectionStatus('connecting', 'statusReconnect');
                setHint('hintDisconnectedRetrying');
                spinner.style.display = 'block';
                scheduleReconnect();
            }
        };
        socket.onerror = (err) => {
            console.error("WebSocket Error:", err);
        };
        socket.onmessage = (event) => {
            try {
                if (ws !== socket) return;
                lastServerActivity = Date.now();
                const data = JSON.parse(event.data);
                if (data.type === 'auth_ok') {
                    if (!acceptHello(data)) {
                        socket.close(4011, 'unsupported_protocol');
                        return;
                    }
                    isConnected = true;
                    reconnectBackoff.reset();
                    setConnectionStatus('online', 'statusOnline');
                    setHint('');
                    spinner.style.display = 'none';
                } else if (data.type === 'heartbeat_ack') {
                    setConnectionStatus('online', 'statusOnline', latencyTracker.acknowledge(Date.now()));
                } else if (data.type === 'auth_failed') {
                    shouldReconnect = false;
                    setConnectionStatus('error', 'statusAuthFailed');
                    clearCredentials();
                } else if (data.type === 'copy_success') {
                    if (navigator.vibrate) navigator.vibrate([15, 30, 15]);
                    setHint('hintCopySuccess');
                    setTimeout(() => { if (hintText.textContent === t('hintCopySuccess')) setHint(''); }, 2000);
                } else if (data.type === 'error' && data.code === 'queue_full') {
                    setHint('hintQueueFull');
                } else if (data.type === 'action_result' && data.action === 'type_text') {
                    finishProjection(data);
                } else if (data.type === 'action_result' && data.action === 'quick_action'
                        && data.command === 'cycle_audio_output') {
                    if (data.status === 'ok' && data.output_name) {
                        showGestureFeedback(t('toastAudioSwitched', { name: data.output_name }));
                    } else {
                        showGestureFeedback(t('toastAudioFailed'));
                    }
                } else if (data.type === 'action_result' && data.action === 'quick_action'
                        && data.command === 'close_fullscreen') {
                    if (data.status === 'closed') {
                        showGestureFeedback(t('toastCloseRequested'));
                    } else if (data.status === 'ignored') {
                        showGestureFeedback(t('toastNotFullscreen'));
                    } else {
                        showGestureFeedback(t('toastCloseFailed'));
                    }
                }
            } catch (e) {
                console.error("Error parsing message:", e);
            }
        };
    }

    function scheduleReconnect(delay) {
        if (isPageSuspended || !shouldReconnect || !ctx.credentials.deviceId || !ctx.credentials.deviceToken) return;
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(connect, reconnectBackoff.next(delay ?? null));
    }

    function forceReconnect(reason) {
        if (isPageSuspended || !ctx.credentials.deviceId || !ctx.credentials.deviceToken || !shouldReconnect) return;
        failPendingProjection('hintProjectionTimeout');
        const staleSocket = ws;
        ws = null;
        isConnected = false;
        latencyTracker.reset();
        setConnectionStatus('connecting', 'statusReconnect');
        setHint(reason);
        spinner.style.display = 'block';
        if (staleSocket) {
            try { staleSocket.close(4000, 'heartbeat_timeout'); } catch (_) {}
        }
        connect();
    }

    function probeConnection() {
        if (isPageSuspended || !ctx.credentials.deviceId || !ctx.credentials.deviceToken || !shouldReconnect || document.hidden) return;
        if (!ws || ws.readyState === WebSocket.CLOSED) {
            connect();
            return;
        }
        if (ws.readyState !== WebSocket.OPEN || !isConnected) return;
        if (Date.now() - lastServerActivity > Math.max(12000, (serverInfo?.heartbeatInterval ?? 5000) * 2.4)) {
            forceReconnect('hintTimeoutRetrying');
            return;
        }
        latencyTracker.sent(Date.now());
        ws.send(JSON.stringify({ action: 'heartbeat' }));
    }

    function suspendConnection() {
        if (isPageSuspended) return;
        isPageSuspended = true;
        failPendingProjection('hintPagePaused');
        clearTimeout(reconnectTimer);
        clearTimeout(reconnectProbeTimer);
        isConnected = false;
        latencyTracker.reset();
        setConnectionStatus('offline', 'statusPaused');
        setHint('');
        spinner.style.display = 'none';
        const activeSocket = ws;
        ws = null;
        if (activeSocket) {
            try {
                if (activeSocket.readyState === WebSocket.OPEN) {
                    activeSocket.close(4002, 'client_background');
                } else {
                    activeSocket.close();
                }
            } catch (_) {}
        }
    }

    function resumeConnection() {
        isPageSuspended = false;
        shouldReconnect = true;
        reconnectBackoff.reset();
        lastServerActivity = Date.now();
        if (ctx.credentials.deviceId && ctx.credentials.deviceToken) connect();
        restoreProjectionState();
    }

    heartbeatTimer = setInterval(probeConnection, 5000);
    window.addEventListener('online', () => {
        if (!isPageSuspended) forceReconnect('hintNetworkOnline');
    });
    window.addEventListener('pagehide', suspendConnection);
    window.addEventListener('pageshow', resumeConnection);
    window.addEventListener('focus', () => {
        if (!isPageSuspended) probeConnection();
    });
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) suspendConnection();
        else resumeConnection();
    });

    function start() {
        if (ctx.credentials.deviceId && ctx.credentials.deviceToken) connect();
        else showPairing();
    }

    function sendCmd(cmd) {
        if (isConnected && ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(cmd));
            return true;
        } else if (ctx.credentials.deviceId && ctx.credentials.deviceToken) {
            probeConnection();
        }
        return false;
    }


    return { connect, start, sendCmd, suspendConnection, resumeConnection, probeConnection, setConnectionStatus, setHint, hintText,
    setReconnect(value) { shouldReconnect = value; },
    get serverInfo() { return serverInfo; },
    refreshLanguage() { refreshConnectionStatus(); if (lastHint.key) setHint(lastHint.key, lastHint.values); }
    };

});
