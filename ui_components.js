(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    root.AirMacUI = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    const DECK_GROUP_DEFINITIONS = Object.freeze([
        {
            title: { zh: '电源与登录', en: 'Power & Login' },
            actions: [
                { label: { zh: '唤醒', en: 'Wake' }, icon: 'sun', theme: 'sunrise', message: { action: 'wake_watch' }, tone: 'accent' },
                { label: { zh: '锁定 Mac', en: 'Lock Mac' }, icon: 'lock', theme: 'lock', message: { action: 'quick_action', command: 'lock_screen' }, tone: 'danger' },
                { label: { zh: '显示器睡眠', en: 'Display Sleep' }, icon: 'moon', theme: 'sleep', message: { action: 'display_sleep' } },
            ],
        },
        {
            title: { zh: '快捷菜单', en: 'Quick Menu' },
            actions: [
                { label: { zh: '控制中心', en: 'Control Center' }, icon: 'control-center', theme: 'control', message: { action: 'quick_action', command: 'open_control_center' }, tone: 'accent' },
                { label: { zh: 'Apps', en: 'Apps' }, icon: 'apps', theme: 'apps', message: { action: 'app_launcher' } },
                { label: { zh: '调度中心', en: 'Mission Control' }, icon: 'mission-control', theme: 'mission', message: { action: 'mission_control' } },
                { label: { zh: '播放 / 暂停', en: 'Play / Pause' }, icon: 'play-pause', theme: 'media', message: { action: 'media', command: 'playpause' } },
                { label: { zh: '全屏', en: 'Fullscreen' }, icon: 'fullscreen', theme: 'fullscreen', message: { action: 'media', command: 'fullscreen' } },
                { label: { zh: '退出全屏应用', en: 'Quit Fullscreen' }, icon: 'close', theme: 'close', message: { action: 'quick_action', command: 'close_fullscreen' }, tone: 'danger' },
            ],
        },
        {
            title: { zh: '声音与显示', en: 'Sound & Display' },
            actions: [
                { label: { zh: '音量减', en: 'Volume Down' }, icon: 'volume-low', theme: 'volume-down', message: { action: 'quick_action', command: 'volume_down' } },
                { label: { zh: '静音', en: 'Mute' }, icon: 'volume-mute', theme: 'mute', message: { action: 'quick_action', command: 'volume_mute' } },
                { label: { zh: '音量加', en: 'Volume Up' }, icon: 'volume-high', theme: 'volume-up', message: { action: 'quick_action', command: 'volume_up' } },
                { label: { zh: '切换扬声器', en: 'Switch Speaker' }, icon: 'airplay', theme: 'speaker', message: { action: 'quick_action', command: 'cycle_audio_output' }, tone: 'accent' },
                { label: { zh: '亮度减', en: 'Brightness Down' }, icon: 'brightness-low', theme: 'dim', message: { action: 'quick_action', command: 'brightness_down' } },
                { label: { zh: '亮度加', en: 'Brightness Up' }, icon: 'brightness-high', theme: 'bright', message: { action: 'quick_action', command: 'brightness_up' } },
                { label: { zh: '截屏到剪贴板', en: 'Screenshot' }, icon: 'screenshot', theme: 'screenshot', message: { action: 'quick_action', command: 'screenshot' } },
            ],
        },
        {
            title: { zh: '窗口', en: 'Windows' },
            actions: [
                { label: { zh: '左半屏', en: 'Left Half' }, icon: 'window-left', theme: 'window-left', message: { action: 'quick_action', command: 'window_left' } },
                { label: { zh: '填充', en: 'Fill' }, icon: 'window-fill', theme: 'window-fill', message: { action: 'quick_action', command: 'window_fill' } },
                { label: { zh: '右半屏', en: 'Right Half' }, icon: 'window-right', theme: 'window-right', message: { action: 'quick_action', command: 'window_right' } },
                { label: { zh: '居中', en: 'Center' }, icon: 'window-center', theme: 'window-center', message: { action: 'quick_action', command: 'window_center' } },
            ],
        },
    ]);

    function normalizeLanguage(language) {
        return language === 'en' ? 'en' : 'zh';
    }

    function localizeDeckGroups(language = 'zh') {
        const lang = normalizeLanguage(language);
        return DECK_GROUP_DEFINITIONS.map((group) => ({
            title: group.title[lang],
            actions: group.actions.map((item) => ({
                ...item,
                label: item.label[lang],
            })),
        }));
    }

    const DECK_GROUPS = Object.freeze(localizeDeckGroups('zh'));

    const ICONS = Object.freeze({
        sun: '<circle cx="12" cy="12" r="3.5"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4"/>',
        lock: '<rect x="5.5" y="10" width="13" height="10" rx="3"/><path d="M8.5 10V7.5a3.5 3.5 0 0 1 7 0V10M12 14v2.5"/>',
        moon: '<path d="M19.5 15.2A8 8 0 0 1 8.8 4.5 8 8 0 1 0 19.5 15.2Z"/>',
        'control-center': '<rect x="3" y="4" width="8" height="7" rx="3.5"/><rect x="13" y="4" width="8" height="7" rx="3.5"/><rect x="3" y="13" width="8" height="7" rx="3.5"/><rect x="13" y="13" width="8" height="7" rx="3.5"/><circle cx="7.5" cy="7.5" r="1.2" fill="currentColor" stroke="none"/><path d="M15.5 7.5h3M7 16.5h1M16.2 15.7l1.6 1.6M17.8 15.7l-1.6 1.6"/>',
        apps: '<rect x="3.5" y="3.5" width="6.5" height="6.5" rx="1.7"/><rect x="14" y="3.5" width="6.5" height="6.5" rx="1.7"/><rect x="3.5" y="14" width="6.5" height="6.5" rx="1.7"/><rect x="14" y="14" width="6.5" height="6.5" rx="1.7"/>',
        'mission-control': '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9.5h18M8.5 9.5V20M15.5 9.5V20"/>',
        'play-pause': '<path d="m5.5 5 8 7-8 7Z" fill="currentColor" stroke="none"/><path d="M17 6v12M20.5 6v12"/>',
        fullscreen: '<path d="M9 4H5a1 1 0 0 0-1 1v4M15 4h4a1 1 0 0 1 1 1v4M9 20H5a1 1 0 0 1-1-1v-4M15 20h4a1 1 0 0 0 1-1v-4"/>',
        close: '<circle cx="12" cy="12" r="8.5"/><path d="m8.5 8.5 7 7M15.5 8.5l-7 7"/>',
        'volume-low': '<path d="M5 10H2.8v4H5l4 3.5v-11Z"/><path d="M12.5 9.2a4 4 0 0 1 0 5.6"/>',
        'volume-mute': '<path d="M5 10H2.8v4H5l4 3.5v-11Z"/><path d="m14.5 9 6 6M20.5 9l-6 6"/>',
        'volume-high': '<path d="M5 10H2.8v4H5l4 3.5v-11Z"/><path d="M12.5 9.2a4 4 0 0 1 0 5.6M15 6.8a7.2 7.2 0 0 1 0 10.4"/>',
        airplay: '<rect x="3" y="4" width="18" height="13" rx="2.5"/><path d="m7.5 21 4.5-5 4.5 5Z" fill="currentColor" stroke="none"/>',
        'brightness-low': '<circle cx="12" cy="12" r="3"/><path d="M12 4v1.5M12 18.5V20M4 12h1.5M18.5 12H20M6.3 6.3l1 1M16.7 16.7l1 1M17.7 6.3l-1 1M7.3 16.7l-1 1"/>',
        'brightness-high': '<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4"/>',
        screenshot: '<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="12" r="4"/>',
        'window-left': '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M12 4v16"/><path d="M6 12h3" opacity=".75"/>',
        'window-fill': '<rect x="3" y="4" width="18" height="16" rx="3"/><rect x="6.5" y="7.5" width="11" height="9" rx="1.5"/>',
        'window-right': '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M12 4v16"/><path d="M15 12h3" opacity=".75"/>',
        'window-center': '<rect x="3" y="4" width="18" height="16" rx="3"/><rect x="8" y="7.5" width="8" height="9" rx="1.5"/>',
    });

    function iconSvg(name) {
        return `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ''}</svg>`;
    }

    const HTMLElementBase = typeof HTMLElement === 'undefined' ? class {} : HTMLElement;

    class AirMacStatus extends HTMLElementBase {
        connectedCallback() {
            if (this.shadowRoot) return;
            const shadow = this.attachShadow({ mode: 'open' });
            shadow.innerHTML = `
                <style>
                    :host { display: inline-flex; min-width: 0; }
                    .pill {
                        display: inline-flex; align-items: center; gap: 7px;
                        min-width: 0; height: 34px; padding: 0 12px;
                        border: 1px solid rgba(255,255,255,.1); border-radius: 999px;
                        background: rgba(255,255,255,.07); color: rgba(255,255,255,.72);
                        box-sizing: border-box; font: 600 12px/1 -apple-system, BlinkMacSystemFont, sans-serif;
                        backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
                    }
                    .dot { width: 7px; height: 7px; flex: 0 0 auto; border-radius: 50%; background: #8e8e93; }
                    .label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                    .latency { color: rgba(255,255,255,.42); font-variant-numeric: tabular-nums; }
                    .pill[data-state="connecting"] .dot { background: #ffd60a; box-shadow: 0 0 9px rgba(255,214,10,.5); }
                    .pill[data-state="online"] .dot { background: #30d158; box-shadow: 0 0 10px rgba(48,209,88,.55); }
                    .pill[data-state="offline"] .dot, .pill[data-state="error"] .dot { background: #ff453a; }
                </style>
                <div class="pill" data-state="offline" role="status" aria-live="polite">
                    <span class="dot"></span><span class="label">未连接</span><span class="latency"></span>
                </div>`;
        }

        setStatus(state, label, latency = null) {
            if (!this.shadowRoot) this.connectedCallback();
            const pill = this.shadowRoot.querySelector('.pill');
            pill.dataset.state = state;
            pill.querySelector('.label').textContent = label;
            pill.querySelector('.latency').textContent = Number.isFinite(latency) ? `${Math.round(latency)} ms` : '';
        }
    }

    class AirMacDeck extends HTMLElementBase {
        static get observedAttributes() {
            return ['lang'];
        }

        connectedCallback() {
            if (this.shadowRoot) return;
            this.attachShadow({ mode: 'open' });
            const shadow = this.shadowRoot;
            shadow.addEventListener('click', (event) => {
                const button = event.target.closest('button[data-message]');
                if (!button) return;
                this.dispatchEvent(new CustomEvent('airmac-command', {
                    bubbles: true,
                    composed: true,
                    detail: JSON.parse(button.dataset.message),
                }));
            });
            this.render();
        }

        attributeChangedCallback() {
            if (this.shadowRoot) this.render();
        }

        setLanguage(language) {
            this.setAttribute('lang', normalizeLanguage(language));
        }

        render() {
            const shadow = this.shadowRoot;
            const groups = localizeDeckGroups(this.getAttribute('lang')).map((group) => `
                <section>
                    <h2>${group.title}</h2>
                    <div class="grid">
                        ${group.actions.map((item) => `
                            <button type="button" data-message='${JSON.stringify(item.message)}' data-tone="${item.tone || ''}" data-theme="${item.theme || ''}">
                                <span class="icon">${iconSvg(item.icon)}</span><span class="label">${item.label}</span>
                            </button>`).join('')}
                    </div>
                </section>`).join('');
            shadow.innerHTML = `
                <style>
                    :host { display: block; min-height: 0; color: white; }
                    section + section { margin-top: 20px; }
                    h2 { margin: 0 0 9px 3px; color: rgba(255,255,255,.43); font: 600 11px/1.2 -apple-system, sans-serif; letter-spacing: .09em; text-transform: uppercase; }
                    .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px 8px; }
                    button {
                        min-width: 0; min-height: 90px; padding: 0 1px;
                        display: flex; flex-direction: column; align-items: center; justify-content: flex-start; gap: 8px;
                        border: 0; border-radius: 18px;
                        background: transparent; color: rgba(255,255,255,.82);
                        box-shadow: none; font: 500 10.5px/1.12 -apple-system, BlinkMacSystemFont, sans-serif;
                        transition: transform .12s ease, filter .12s ease;
                        -webkit-tap-highlight-color: transparent; touch-action: manipulation;
                    }
                    button:active { transform: scale(.96); }
                    button:active .icon { background: rgba(255,255,255,.14); transform: scale(.96); }
                    .icon {
                        width: 66px; height: 66px; flex: 0 0 66px;
                        display: grid; place-items: center; box-sizing: border-box;
                        border: 1px solid rgba(255,255,255,.095); border-radius: 15px;
                        background: linear-gradient(155deg, rgba(255,255,255,.105), rgba(255,255,255,.055));
                        box-shadow: 0 5px 14px rgba(0,0,0,.14), inset 0 1px 0 rgba(255,255,255,.075);
                        color: var(--symbol-color, rgba(255,255,255,.9));
                        transition: transform .12s ease, background .12s ease;
                    }
                    .icon svg { width: 30px; height: 30px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
                    .label { min-height: 12px; text-align: center; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
                    button[data-theme="sunrise"] { --symbol-color: #f5c451; }
                    button[data-theme="lock"], button[data-theme="close"] { --symbol-color: #ff6961; }
                    button[data-theme="sleep"], button[data-theme="mission"] { --symbol-color: #a8a5ff; }
                    button[data-theme="control"], button[data-theme="fullscreen"], button[data-theme="speaker"] { --symbol-color: #66b5ff; }
                    button[data-theme="media"] { --symbol-color: #70d18c; }
                    button[data-theme="bright"] { --symbol-color: #f5c451; }
                    button[data-theme="screenshot"] { --symbol-color: #c6a3ed; }
                    button[data-tone="danger"] .icon { background: rgba(255,89,82,.075); border-color: rgba(255,105,97,.14); }
                    @media (prefers-reduced-motion: reduce) { button { transition: none; } }
                </style>${groups}`;
        }
    }

    if (typeof customElements !== 'undefined') {
        if (!customElements.get('airmac-status')) customElements.define('airmac-status', AirMacStatus);
        if (!customElements.get('airmac-deck')) customElements.define('airmac-deck', AirMacDeck);
    }

    return { DECK_GROUPS, ICONS, localizeDeckGroups, AirMacStatus, AirMacDeck };
}));
