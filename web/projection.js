/* AirMac projection: browser and Node compatible; initialization is explicit. */
(function(root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory;
    else (root.AirMacModules ||= {})['projection'] = factory;
})(globalThis, function(ctx) {
    'use strict';
    const {window, document, navigator, localStorage, WebSocket, TextEncoder, Date, setTimeout, clearTimeout, setInterval, clearInterval, requestAnimationFrame, cancelAnimationFrame} = ctx.env;
    const AirMacState = ctx.state;
    const t = (...args) => ctx.i18n.t(...args);
    const sendCmd = (...args) => ctx.connection.sendCmd(...args);
    const setHint = (...args) => ctx.connection.setHint(...args);
    const hintText = ctx.connection.hintText;
    const projectionInput = document.getElementById('projection-input');
    const projectionButton = document.getElementById('projection-btn');
    const projectionClear = document.getElementById('projection-clear');
    let projectionComposing = false;
    const projectionState = new AirMacState.ProjectionState();
    let retryProjection = null;

    function projectionRequestId() {
        if (window.crypto && typeof window.crypto.randomUUID === 'function') {
            return window.crypto.randomUUID();
        }
        return `text_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    }

    function setProjectionBusy(isBusy) {
        projectionInput.readOnly = isBusy;
        projectionButton.disabled = isBusy;
        projectionClear.disabled = isBusy;
    }

    function clearProjection(forgetConfirmed = true) {
        projectionInput.value = '';
        projectionInput.defaultValue = '';
        if (forgetConfirmed) projectionState.forgetConfirmed();
        projectionInput.style.height = '52px';
    }

    function failPendingProjection(message) {
        const failed = projectionState.fail();
        if (!failed) return;
        retryProjection = failed;
        setProjectionBusy(false);
        setHint(message);
    }

    function finishProjection(result) {
        const completed = projectionState.finish(result.request_id, result.status);
        if (completed.outcome === 'ignored') return;
        if (completed.outcome === 'confirmed') {
            retryProjection = null;
            clearProjection(false);
            setProjectionBusy(false);
            setHint('hintTextSent');
            setTimeout(() => {
                if (hintText.textContent === t('hintTextSent')) setHint('');
            }, 1600);
        } else {
            retryProjection = {
                requestId: result.request_id,
                text: completed.text,
            };
            setProjectionBusy(false);
            setHint('hintTextFailed');
        }
    }

    function restoreProjectionState() {
        if (projectionState.shouldClearRestored(projectionInput.value)) {
            clearProjection(false);
        }
    }

    function submitProjection() {
        if (projectionState.isPending || projectionComposing) return;
        const text = projectionInput.value;
        if (!text) return;
        const utf8Bytes = new TextEncoder().encode(text).length;
        if (utf8Bytes > 32768) {
            setHint('hintTextTooLarge');
            return;
        }
        projectionInput.blur();
        const requestId = retryProjection && retryProjection.text === text
            ? retryProjection.requestId
            : projectionRequestId();
        if (!projectionState.begin(requestId, text)) return;
        retryProjection = null;
        setProjectionBusy(true);
        if (!sendCmd({ action: 'type_text', request_id: requestId, text })) {
            failPendingProjection('hintNotConnected');
            return;
        }
        setHint('hintSendingText');
        if (navigator.vibrate) navigator.vibrate(15);
    }

    projectionButton.addEventListener('click', (e) => {
        e.preventDefault();
        if (projectionComposing) {
            projectionInput.blur();
            setTimeout(submitProjection, 0);
        } else {
            submitProjection();
        }
    });
    projectionClear.addEventListener('click', (e) => {
        e.preventDefault();
        retryProjection = null;
        clearProjection();
        projectionInput.focus();
        if (navigator.vibrate) navigator.vibrate(10);
    });
    projectionInput.addEventListener('compositionstart', () => {
        projectionComposing = true;
    });
    projectionInput.addEventListener('compositionend', () => {
        projectionComposing = false;
    });
    projectionInput.addEventListener('input', () => {
        projectionState.noteUserInput();
        retryProjection = null;
        projectionInput.style.height = '52px';
        projectionInput.style.height = `${Math.min(104, projectionInput.scrollHeight)}px`;
    });

    // --- Keyboard Logic ---
    const hiddenInput = document.getElementById('hidden-input');
    const keyboardTrigger = document.getElementById('keyboard-trigger');

    keyboardTrigger.addEventListener('touchend', (e) => {
        e.preventDefault(); // Prevent double click event
        hiddenInput.focus();
        if (navigator.vibrate) navigator.vibrate(15);
    });

    keyboardTrigger.addEventListener('click', (e) => {
        hiddenInput.focus();
        if (navigator.vibrate) navigator.vibrate(15);
    });

    hiddenInput.addEventListener('input', (e) => {
        if (e.data) {
            sendCmd({ action: 'type', char: e.data });
        }
        hiddenInput.value = '';
    });

    hiddenInput.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace' || e.key === 'Enter') {
            sendCmd({ action: 'keydown', key: e.key });
        }
    });

    document.body.addEventListener('click', (e) => {
        if (e.target !== keyboardTrigger && e.target !== hiddenInput) {
            hiddenInput.blur();
        }
    });

    return { failPendingProjection, finishProjection, restoreProjectionState, submitProjection };

});
