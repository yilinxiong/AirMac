/* AirMac pairing: browser and Node compatible; initialization is explicit. */
(function(root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory;
    else (root.AirMacModules ||= {})['pairing'] = factory;
})(globalThis, function(ctx) {
    'use strict';
    const {window, document, navigator, localStorage, WebSocket, TextEncoder, Date, setTimeout, clearTimeout, setInterval, clearInterval, requestAnimationFrame, cancelAnimationFrame} = ctx.env;
    const AirMacState = ctx.state;
    const t = (...args) => ctx.i18n.t(...args);
    const setConnectionStatus = (...args) => ctx.connection.setConnectionStatus(...args);
    let pairingChallengeId = null;
    const pairingOverlay = document.getElementById('pairing-overlay');
    const pairingName = document.getElementById('pairing-name');
    const pairingCode = document.getElementById('pairing-code');
    const pairingButton = document.getElementById('pairing-button');
    const pairingDescription = document.getElementById('pairing-description');
    const pairingError = document.getElementById('pairing-error');
    pairingName.value = ctx.credentials.deviceName;

    function showPairing(message = '') {
        ctx.connection.setReconnect(false);
        setConnectionStatus('offline', 'statusPairing');
        pairingOverlay.classList.remove('hidden');
        pairingError.textContent = message;
        pairingChallengeId = null;
        pairingName.classList.remove('hidden');
        pairingCode.classList.add('hidden');
        pairingCode.value = '';
        pairingButton.textContent = t('pairStart');
        pairingDescription.textContent = t('pairDescriptionStart');
        pairingButton.disabled = false;
    }

    function hidePairing() {
        pairingOverlay.classList.add('hidden');
        ctx.connection.setReconnect(true);
    }

    async function responseError(response) {
        try {
            const body = await response.json();
            return body.detail || t('requestFailed');
        } catch (_) {
            return t('requestFailed');
        }
    }

    async function startPairing() {
        const name = pairingName.value.trim();
        if (!name) {
            pairingError.textContent = t('pairNameRequired');
            return;
        }
        pairingButton.disabled = true;
        pairingError.textContent = '';
        try {
            const response = await ctx.env.fetch('/api/pairing/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ device_name: name })
            });
            if (!response.ok) throw new Error(await responseError(response));
            const result = await response.json();
            pairingChallengeId = result.challenge_id;
            ctx.credentials.deviceName = name;
            pairingName.classList.add('hidden');
            pairingCode.classList.remove('hidden');
            pairingDescription.textContent = t('pairDescriptionCode');
            pairingButton.textContent = t('pairComplete');
            pairingCode.focus();
        } catch (error) {
            pairingError.textContent = error.message;
        } finally {
            pairingButton.disabled = false;
        }
    }

    async function completePairing() {
        const code = pairingCode.value.replace(/\D/g, '');
        if (code.length !== 6) {
            pairingError.textContent = t('pairCodeRequired');
            return;
        }
        pairingButton.disabled = true;
        pairingError.textContent = '';
        try {
            const response = await ctx.env.fetch('/api/pairing/complete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ challenge_id: pairingChallengeId, code })
            });
            if (!response.ok) throw new Error(await responseError(response));
            const result = await response.json();
            ctx.credentials.save(result);
            hidePairing();
            ctx.connection.connect();
        } catch (error) {
            pairingError.textContent = error.message;
            pairingCode.select();
        } finally {
            pairingButton.disabled = false;
        }
    }

    pairingButton.addEventListener('click', () => {
        if (pairingChallengeId) completePairing();
        else startPairing();
    });
    pairingCode.addEventListener('input', () => {
        pairingCode.value = pairingCode.value.replace(/\D/g, '').slice(0, 6);
    });
    pairingCode.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') completePairing();
    });


    function refreshLanguage() {
        pairingDescription.textContent = t(pairingChallengeId ? 'pairDescriptionCode' : 'pairDescriptionStart');
        pairingButton.textContent = t(pairingChallengeId ? 'pairComplete' : 'pairStart');
    }
    return { showPairing, hidePairing, refreshLanguage, startPairing, completePairing };

});
