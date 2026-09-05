/* AirMac i18n: browser and Node compatible; initialization is explicit. */
(function(root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory;
    else (root.AirMacModules ||= {})['i18n'] = factory;
})(globalThis, function(ctx) {
    'use strict';
    const {window, document, navigator, localStorage, WebSocket, TextEncoder, Date, setTimeout, clearTimeout, setInterval, clearInterval, requestAnimationFrame, cancelAnimationFrame} = ctx.env;
    const AirMacState = ctx.state;
    const i18n = {
        zh: {
            statusVersionMismatch: '需要更新',
            hintVersionMismatch: '客户端与服务版本不兼容，请刷新页面或更新 AirMac。',
            hintRateLimited: '认证尝试过于频繁，将稍后重试。',
            htmlLang: 'zh-CN',
            switchLabel: 'EN',
            switchAria: 'Switch to English',
            settingsAria: '打开设置',
            closeSettingsAria: '关闭设置',
            installDefault: '将 AirMac 添加到主屏幕，使用时更像原生 App。',
            installDismiss: '知道了',
            installIOS: '点 Safari 的分享按钮，再选“添加到主屏幕”。',
            installPrompt: '安装 AirMac，获得全屏触控板体验。',
            installAction: '安装',
            pairTitle: '连接 AirMac',
            pairDescriptionStart: '为这台 iPhone 命名，然后在 Mac 上获取一次性验证码。',
            pairDescriptionCode: '在 Mac 弹窗中查看 6 位验证码，并在下方输入。',
            pairNamePlaceholder: '设备名称',
            pairStart: '在 Mac 上显示验证码',
            pairComplete: '完成安全配对',
            pairNameRequired: '请输入设备名称',
            pairCodeRequired: '请输入 6 位验证码',
            requestFailed: '请求失败，请稍后重试',
            navAria: '主要功能',
            padAria: '触控板',
            deckAria: '快捷控制',
            textAria: '文本输入',
            textTitle: '文本输入',
            textDescription: '长文本会作为一次完整投射发送；实时键盘适合短句和退格。',
            textPlaceholder: '输入长文本投射到 Mac...',
            clearTextAria: '清空长文本',
            sendTextAria: '发送长文本',
            keyboardButton: '⌨︎ 打开实时键盘',
            navPad: '触控板',
            navDeck: '快捷台',
            navText: '文本',
            gestureGuideAria: '手势提示',
            gestureGuideOne: '单指移动/点击 · 双指滚动/右键',
            gestureGuideTwo: '三指左右切桌面 · 三/四指上滑调度/应用',
            settingsTitle: '控制设置',
            pointerSensitivity: '指针灵敏度',
            scrollSpeed: '滚动速度',
            naturalScroll: '自然滚动方向',
            threeFingerUp: '三指上滑',
            fourFingerUp: '四指上滑',
            optionMission: '调度中心',
            optionApps: 'Apps 应用界面',
            optionDisabled: '关闭',
            touchFeedback: '触点反馈',
            reduceMotion: '减少动态效果',
            lowPower: '低功耗模式',
            resetDefaults: '恢复默认',
            save: '保存',
            statusPairing: '等待配对',
            statusConnecting: '连接中',
            statusReconnect: '重连中',
            statusOnline: '已连接',
            statusAuthExpired: '认证失效',
            statusBusy: '控制器忙',
            statusReplaced: '会话已替换',
            statusAuthFailed: '认证失败',
            statusPaused: '已暂停',
            hintConnecting: '连接中...',
            hintProjectionInterrupted: '连接中断，文本尚未确认发送',
            hintCredentialExpired: '设备凭据已失效，请重新配对',
            hintBusy: '另一台设备正在控制 Mac',
            hintReplaced: '连接已被这台设备的新会话替换',
            hintDisconnectedRetrying: '断开连接，重连中...',
            hintCopySuccess: '复制成功',
            hintQueueFull: '指令过快，已丢弃部分输入',
            hintProjectionTimeout: '连接超时，文本内容已保留',
            hintTimeoutRetrying: '连接超时，重新连接中...',
            hintPagePaused: '页面已暂停，文本内容已保留',
            hintNetworkOnline: '网络已恢复，重新连接中...',
            hintTextSent: '文本已发送',
            hintTextFailed: '文本发送失败，内容已保留',
            hintTextTooLarge: '文本超过 32 KiB，请缩短后重试',
            hintNotConnected: '尚未连接，内容已保留',
            hintSendingText: '正在发送文本...',
            toastSettingsSaved: '设置已保存',
            toastMission: '调度中心',
            toastApps: 'Apps',
            toastNextSpace: '下一个桌面',
            toastPreviousSpace: '上一个桌面',
            toastCommandSent: '指令已发送',
            toastWaitingConnection: '等待连接',
            toastAudioSwitched: '已切换到 {name}',
            toastAudioFailed: '无法切换扬声器',
            toastCloseRequested: '已请求退出全屏应用',
            toastNotFullscreen: '当前窗口不是全屏',
            toastCloseFailed: '无法退出全屏应用',
        },
        en: {
            statusVersionMismatch: 'Update Required',
            hintVersionMismatch: 'Client and server versions are incompatible. Refresh or update AirMac.',
            hintRateLimited: 'Too many authentication attempts. Retrying shortly.',
            htmlLang: 'en',
            switchLabel: '中',
            switchAria: '切换到中文',
            settingsAria: 'Open Settings',
            closeSettingsAria: 'Close Settings',
            installDefault: 'Add AirMac to your Home Screen for an app-like experience.',
            installDismiss: 'Got it',
            installIOS: 'Tap Safari Share, then choose "Add to Home Screen".',
            installPrompt: 'Install AirMac for a full-screen trackpad experience.',
            installAction: 'Install',
            pairTitle: 'Connect AirMac',
            pairDescriptionStart: 'Name this iPhone, then get a one-time pairing code on your Mac.',
            pairDescriptionCode: 'Read the 6-digit code in the Mac dialog, then enter it below.',
            pairNamePlaceholder: 'Device name',
            pairStart: 'Show code on Mac',
            pairComplete: 'Complete secure pairing',
            pairNameRequired: 'Enter a device name',
            pairCodeRequired: 'Enter the 6-digit code',
            requestFailed: 'Request failed. Please try again.',
            navAria: 'Main features',
            padAria: 'Trackpad',
            deckAria: 'Quick controls',
            textAria: 'Text input',
            textTitle: 'Text Input',
            textDescription: 'Long text is sent as one projection; live keyboard is best for short text and backspace.',
            textPlaceholder: 'Type long text to project to Mac...',
            clearTextAria: 'Clear long text',
            sendTextAria: 'Send long text',
            keyboardButton: '⌨︎ Open Live Keyboard',
            navPad: 'Pad',
            navDeck: 'Deck',
            navText: 'Text',
            gestureGuideAria: 'Gesture hints',
            gestureGuideOne: 'One finger move/tap · Two fingers scroll/right click',
            gestureGuideTwo: 'Three fingers switch Spaces · Three/four up for Mission/Apps',
            settingsTitle: 'Controls',
            pointerSensitivity: 'Pointer Sensitivity',
            scrollSpeed: 'Scroll Speed',
            naturalScroll: 'Natural Scrolling',
            threeFingerUp: 'Three-Finger Up',
            fourFingerUp: 'Four-Finger Up',
            optionMission: 'Mission Control',
            optionApps: 'Apps',
            optionDisabled: 'Off',
            touchFeedback: 'Touch Feedback',
            reduceMotion: 'Reduce Motion',
            lowPower: 'Low Power Mode',
            resetDefaults: 'Reset Defaults',
            save: 'Save',
            statusPairing: 'Pairing',
            statusConnecting: 'Connecting',
            statusReconnect: 'Reconnecting',
            statusOnline: 'Connected',
            statusAuthExpired: 'Auth Expired',
            statusBusy: 'Controller Busy',
            statusReplaced: 'Session Replaced',
            statusAuthFailed: 'Auth Failed',
            statusPaused: 'Paused',
            hintConnecting: 'Connecting...',
            hintProjectionInterrupted: 'Connection interrupted; text was not confirmed',
            hintCredentialExpired: 'Device credentials expired. Pair again.',
            hintBusy: 'Another device is controlling this Mac',
            hintReplaced: 'This session was replaced by a new session from this device',
            hintDisconnectedRetrying: 'Disconnected, reconnecting...',
            hintCopySuccess: 'Copied',
            hintQueueFull: 'Commands were too fast; some input was dropped',
            hintProjectionTimeout: 'Connection timed out; text was preserved',
            hintTimeoutRetrying: 'Connection timed out, reconnecting...',
            hintPagePaused: 'Page paused; text was preserved',
            hintNetworkOnline: 'Network restored, reconnecting...',
            hintTextSent: 'Text sent',
            hintTextFailed: 'Text failed; content was preserved',
            hintTextTooLarge: 'Text exceeds 32 KiB. Shorten it and try again.',
            hintNotConnected: 'Not connected; content was preserved',
            hintSendingText: 'Sending text...',
            toastSettingsSaved: 'Settings saved',
            toastMission: 'Mission Control',
            toastApps: 'Apps',
            toastNextSpace: 'Next Space',
            toastPreviousSpace: 'Previous Space',
            toastCommandSent: 'Command sent',
            toastWaitingConnection: 'Waiting for connection',
            toastAudioSwitched: 'Switched to {name}',
            toastAudioFailed: 'Could not switch speaker',
            toastCloseRequested: 'Requested fullscreen app quit',
            toastNotFullscreen: 'Current window is not fullscreen',
            toastCloseFailed: 'Could not quit fullscreen app',
        },
    };
    const languageKey = 'airmac_language';
    const browserLanguage = navigator.language && navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en';
    let language = localStorage.getItem(languageKey) || browserLanguage;
    if (!Object.prototype.hasOwnProperty.call(i18n, language)) language = 'zh';

    function t(key, values = {}) {
        const template = i18n[language][key] ?? i18n.zh[key] ?? key;
        return template.replace(/\{(\w+)\}/g, (_, name) => values[name] ?? '');
    }

    function setElementText(id, key) {
        document.getElementById(id).textContent = t(key);
    }

    function setElementAria(id, key) {
        document.getElementById(id).setAttribute('aria-label', t(key));
    }

    function setSelectOptions(id, optionKeys) {
        const select = document.getElementById(id);
        Array.from(select.options).forEach((option, index) => {
            option.textContent = t(optionKeys[index]);
        });
    }

    const installCoach = document.getElementById('install-coach');
    const installCoachText = document.getElementById('install-coach-text');
    const installCoachButton = document.getElementById('install-coach-button');
    const languageToggle = document.getElementById('language-toggle');
    const installHintKey = 'airmac_install_hint_dismissed_v1';
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches
        || window.navigator.standalone === true;
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
        || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    let deferredInstallPrompt = null;
    let installCoachMode = 'default';

    function applyInstallCoachLanguage() {
        const textKey = installCoachMode === 'ios'
            ? 'installIOS'
            : (installCoachMode === 'prompt' ? 'installPrompt' : 'installDefault');
        installCoachText.textContent = t(textKey);
        installCoachButton.textContent = t(installCoachMode === 'prompt' ? 'installAction' : 'installDismiss');
    }

    function dismissInstallCoach() {
        installCoach.hidden = true;
        localStorage.setItem(installHintKey, '1');
    }

    if (!isStandalone && localStorage.getItem(installHintKey) !== '1') {
        if (isIOS) {
            installCoachMode = 'ios';
            applyInstallCoachLanguage();
            window.setTimeout(() => { installCoach.hidden = false; }, 1800);
        }
        window.addEventListener('beforeinstallprompt', (event) => {
            event.preventDefault();
            deferredInstallPrompt = event;
            installCoachMode = 'prompt';
            applyInstallCoachLanguage();
            installCoach.hidden = false;
        });
    }

    installCoachButton.addEventListener('click', async () => {
        if (!deferredInstallPrompt) {
            dismissInstallCoach();
            return;
        }
        deferredInstallPrompt.prompt();
        await deferredInstallPrompt.userChoice;
        deferredInstallPrompt = null;
        dismissInstallCoach();
    });
    window.addEventListener('appinstalled', dismissInstallCoach);


    return { t, setElementText, setElementAria, setSelectOptions, languageToggle, applyInstallCoachLanguage,
        get language() { return language; },
        toggle() { language = language === 'zh' ? 'en' : 'zh'; localStorage.setItem(languageKey, language); }
    };

});
