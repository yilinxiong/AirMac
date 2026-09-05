/* AirMac settings: browser and Node compatible; initialization is explicit. */
(function(root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory;
    else (root.AirMacModules ||= {})['settings'] = factory;
})(globalThis, function(ctx) {
    'use strict';
    const {window, document, navigator, localStorage, WebSocket, TextEncoder, Date, setTimeout, clearTimeout, setInterval, clearInterval, requestAnimationFrame, cancelAnimationFrame} = ctx.env;
    const AirMacState = ctx.state;
    const t = (...args) => ctx.i18n.t(...args);
    // View shell and persisted preferences
    const settingsStore = new AirMacState.SettingsStore(localStorage);
    let settings = settingsStore.load();
    const settingsOverlay = document.getElementById('settings-overlay');
    const settingsButton = document.getElementById('settings-button');
    const gestureHelpButton = document.getElementById('gesture-help-button');
    const gestureGuide = document.getElementById('gesture-guide');
    const settingsForm = document.getElementById('settings-form');
    const pointerInput = document.getElementById('pointer-sensitivity');
    const scrollInput = document.getElementById('scroll-speed');
    const pointerValue = document.getElementById('pointer-value');
    const scrollValue = document.getElementById('scroll-value');
    const gestureToast = document.getElementById('gesture-toast');
    let gestureToastTimer = null;

    function applySettings() {
        document.body.classList.toggle('reduce-motion', settings.reduceMotion);
        document.body.classList.toggle('low-power', settings.lowPower);
    }

    function populateSettings() {
        pointerInput.value = settings.pointerSensitivity;
        scrollInput.value = settings.scrollSpeed;
        pointerValue.textContent = `${Number(pointerInput.value).toFixed(1)}×`;
        scrollValue.textContent = `${Number(scrollInput.value).toFixed(1)}×`;
        document.getElementById('natural-scroll').checked = settings.naturalScroll;
        document.getElementById('three-finger-up').value = settings.threeFingerUp;
        document.getElementById('four-finger-up').value = settings.fourFingerUp;
        document.getElementById('touch-feedback-setting').checked = settings.touchFeedback;
        document.getElementById('reduce-motion').checked = settings.reduceMotion;
        document.getElementById('low-power').checked = settings.lowPower;
    }

    function readSettingsForm() {
        return {
            pointerSensitivity: pointerInput.value,
            scrollSpeed: scrollInput.value,
            naturalScroll: document.getElementById('natural-scroll').checked,
            threeFingerUp: document.getElementById('three-finger-up').value,
            fourFingerUp: document.getElementById('four-finger-up').value,
            touchFeedback: document.getElementById('touch-feedback-setting').checked,
            reduceMotion: document.getElementById('reduce-motion').checked,
            lowPower: document.getElementById('low-power').checked,
        };
    }

    function openSettings() {
        populateSettings();
        settingsOverlay.hidden = false;
        document.getElementById('settings-close').focus({ preventScroll: true });
    }

    function closeSettings() {
        settingsOverlay.hidden = true;
        settingsButton.focus({ preventScroll: true });
    }

    function showGestureFeedback(message) {
        clearTimeout(gestureToastTimer);
        gestureToast.textContent = message;
        gestureToast.classList.add('visible');
        gestureToastTimer = setTimeout(() => gestureToast.classList.remove('visible'), 950);
    }

    function setGestureGuideVisible(visible) {
        gestureGuide.hidden = !visible;
        gestureHelpButton.setAttribute('aria-expanded', visible ? 'true' : 'false');
    }

    applySettings();
    gestureHelpButton.addEventListener('click', (event) => {
        event.stopPropagation();
        setGestureGuideVisible(gestureGuide.hidden);
        if (navigator.vibrate) navigator.vibrate(8);
    });
    document.addEventListener('click', (event) => {
        if (gestureGuide.hidden) return;
        if (event.target === gestureHelpButton || gestureGuide.contains(event.target)) return;
        setGestureGuideVisible(false);
    });
    settingsButton.addEventListener('click', openSettings);
    document.getElementById('settings-close').addEventListener('click', closeSettings);
    settingsOverlay.addEventListener('click', (event) => {
        if (event.target === settingsOverlay) closeSettings();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !settingsOverlay.hidden) closeSettings();
    });
    pointerInput.addEventListener('input', () => { pointerValue.textContent = `${Number(pointerInput.value).toFixed(1)}×`; });
    scrollInput.addEventListener('input', () => { scrollValue.textContent = `${Number(scrollInput.value).toFixed(1)}×`; });
    settingsForm.addEventListener('submit', (event) => {
        event.preventDefault();
        settings = settingsStore.save(readSettingsForm());
        applySettings();
        closeSettings();
        showGestureFeedback(t('toastSettingsSaved'));
    });
    document.getElementById('settings-reset').addEventListener('click', () => {
        settings = settingsStore.reset();
        populateSettings();
        applySettings();
    });

    document.querySelectorAll('.nav-button').forEach((button) => {
        button.addEventListener('click', () => {
            document.querySelectorAll('.nav-button').forEach((item) => item.classList.toggle('active', item === button));
            document.querySelectorAll('.view').forEach((view) => view.classList.toggle('active', view.id === `${button.dataset.view}-view`));
            if (navigator.vibrate) navigator.vibrate(8);
        });
    });


    return { get settings() { return settings; }, showGestureFeedback };

});
