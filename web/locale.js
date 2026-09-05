/* AirMac locale: browser and Node compatible; initialization is explicit. */
(function(root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory;
    else (root.AirMacModules ||= {})['locale'] = factory;
})(globalThis, function(ctx) {
    'use strict';
    const {window, document, navigator, localStorage, WebSocket, TextEncoder, Date, setTimeout, clearTimeout, setInterval, clearInterval, requestAnimationFrame, cancelAnimationFrame} = ctx.env;
    const AirMacState = ctx.state;
    const {t, setElementText, setElementAria, setSelectOptions, languageToggle, applyInstallCoachLanguage} = ctx.i18n;
    function applyLanguage() {
        document.documentElement.lang = t('htmlLang');
        languageToggle.textContent = t('switchLabel');
        languageToggle.setAttribute('aria-label', t('switchAria'));
        setElementAria('settings-button', 'settingsAria');
        setElementAria('settings-close', 'closeSettingsAria');
        setElementAria('pad-view', 'padAria');
        setElementAria('deck-view', 'deckAria');
        setElementAria('text-view', 'textAria');
        setElementAria('projection-clear', 'clearTextAria');
        setElementAria('projection-btn', 'sendTextAria');
        setElementAria('main-nav', 'navAria');
        setElementAria('gesture-guide', 'gestureGuideAria');
        setElementText('pairing-title', 'pairTitle');
        setElementText('text-title', 'textTitle');
        setElementText('text-description', 'textDescription');
        document.getElementById('projection-input').setAttribute('placeholder', t('textPlaceholder'));
        document.getElementById('pairing-name').setAttribute('placeholder', t('pairNamePlaceholder'));
        setElementText('keyboard-trigger', 'keyboardButton');
        document.querySelector('[data-view="pad"] .nav-label').textContent = t('navPad');
        document.querySelector('[data-view="deck"] .nav-label').textContent = t('navDeck');
        document.querySelector('[data-view="text"] .nav-label').textContent = t('navText');
        document.querySelector('[data-i18n="gesture-guide-one"]').textContent = t('gestureGuideOne');
        document.querySelector('[data-i18n="gesture-guide-two"]').textContent = t('gestureGuideTwo');
        setElementText('settings-title', 'settingsTitle');
        setElementText('label-pointer-sensitivity', 'pointerSensitivity');
        setElementText('label-scroll-speed', 'scrollSpeed');
        setElementText('label-natural-scroll', 'naturalScroll');
        setElementText('label-three-finger-up', 'threeFingerUp');
        setElementText('label-four-finger-up', 'fourFingerUp');
        setElementText('label-touch-feedback', 'touchFeedback');
        setElementText('label-reduce-motion', 'reduceMotion');
        setElementText('label-low-power', 'lowPower');
        setElementText('settings-reset', 'resetDefaults');
        setElementText('settings-save', 'save');
        setSelectOptions('three-finger-up', ['optionMission', 'optionApps']);
        setSelectOptions('four-finger-up', ['optionApps', 'optionMission', 'optionDisabled']);
        document.getElementById('quick-deck').setAttribute('lang', ctx.i18n.language);
        applyInstallCoachLanguage();
        ctx.connection.refreshLanguage();
        ctx.pairing.refreshLanguage();
    }

    applyLanguage();
    languageToggle.addEventListener('click', () => {
        ctx.i18n.toggle();
        applyLanguage();
        if (navigator.vibrate) navigator.vibrate(8);
    });


    return { applyLanguage };

});
