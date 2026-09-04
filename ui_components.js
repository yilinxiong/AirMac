(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    root.AirMacUI = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    const DECK_GROUPS = Object.freeze([
        {
            title: '电源与登录',
            actions: [
                { label: '唤醒', icon: '☀', message: { action: 'wake_watch' }, tone: 'accent' },
                { label: '锁定 Mac', icon: '⌾', message: { action: 'quick_action', command: 'lock_screen' }, tone: 'danger' },
                { label: '显示器睡眠', icon: '☾', message: { action: 'display_sleep' } },
            ],
        },
        {
            title: '快捷菜单',
            actions: [
                { label: '控制中心', icon: '◩', message: { action: 'quick_action', command: 'open_control_center' }, tone: 'accent' },
                { label: 'Apps', icon: '◫', message: { action: 'app_launcher' } },
                { label: '调度中心', icon: '◇', message: { action: 'mission_control' } },
                { label: '播放 / 暂停', icon: '▶︎', message: { action: 'media', command: 'playpause' } },
                { label: '全屏', icon: '⛶', message: { action: 'media', command: 'fullscreen' } },
                { label: '退出全屏应用', icon: '×', message: { action: 'quick_action', command: 'close_fullscreen' }, tone: 'danger' },
            ],
        },
        {
            title: '声音与显示',
            actions: [
                { label: '音量减', icon: '▾', message: { action: 'quick_action', command: 'volume_down' } },
                { label: '静音', icon: '◌', message: { action: 'quick_action', command: 'volume_mute' } },
                { label: '音量加', icon: '▴', message: { action: 'quick_action', command: 'volume_up' } },
                { label: '切换扬声器', icon: '◖', message: { action: 'quick_action', command: 'cycle_audio_output' }, tone: 'accent' },
                { label: '亮度减', icon: '☼', message: { action: 'quick_action', command: 'brightness_down' } },
                { label: '亮度加', icon: '☀︎', message: { action: 'quick_action', command: 'brightness_up' } },
                { label: '截屏到剪贴板', icon: '⌗', message: { action: 'quick_action', command: 'screenshot' } },
            ],
        },
        {
            title: '窗口',
            actions: [
                { label: '左半屏', icon: '◧', message: { action: 'quick_action', command: 'window_left' } },
                { label: '填充', icon: '▣', message: { action: 'quick_action', command: 'window_fill' } },
                { label: '右半屏', icon: '◨', message: { action: 'quick_action', command: 'window_right' } },
                { label: '居中', icon: '▢', message: { action: 'quick_action', command: 'window_center' } },
            ],
        },
    ]);

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
        connectedCallback() {
            if (this.shadowRoot) return;
            const shadow = this.attachShadow({ mode: 'open' });
            const groups = DECK_GROUPS.map((group) => `
                <section>
                    <h2>${group.title}</h2>
                    <div class="grid">
                        ${group.actions.map((item) => `
                            <button type="button" data-message='${JSON.stringify(item.message)}' data-tone="${item.tone || ''}">
                                <span class="icon">${item.icon}</span><span class="label">${item.label}</span>
                            </button>`).join('')}
                    </div>
                </section>`).join('');
            shadow.innerHTML = `
                <style>
                    :host { display: block; min-height: 0; color: white; }
                    section + section { margin-top: 20px; }
                    h2 { margin: 0 0 9px 3px; color: rgba(255,255,255,.43); font: 600 11px/1.2 -apple-system, sans-serif; letter-spacing: .09em; text-transform: uppercase; }
                    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 11px 8px; }
                    button {
                        min-width: 0; min-height: 82px; padding: 2px;
                        display: flex; flex-direction: column; align-items: center; justify-content: flex-start; gap: 7px;
                        border: 0; border-radius: 18px;
                        background: transparent; color: rgba(255,255,255,.82);
                        box-shadow: none; font: 500 11px/1.15 -apple-system, sans-serif;
                        -webkit-tap-highlight-color: transparent; touch-action: manipulation;
                    }
                    button:active { transform: scale(.96); }
                    button:active .icon { filter: brightness(1.18); }
                    button[data-tone="accent"] { color: #75baff; }
                    button[data-tone="accent"] .icon {
                        border-color: rgba(70,164,255,.34);
                        background: linear-gradient(145deg, rgba(35,142,255,.35), rgba(10,94,200,.2));
                    }
                    button[data-tone="danger"] { color: #ff8a84; }
                    button[data-tone="danger"] .icon {
                        border-color: rgba(255,105,97,.24);
                        background: linear-gradient(145deg, rgba(255,92,83,.18), rgba(119,32,30,.12));
                    }
                    .icon {
                        width: 60px; height: 60px; flex: 0 0 60px;
                        display: grid; place-items: center; box-sizing: border-box;
                        border: 1px solid rgba(255,255,255,.12); border-radius: 15px;
                        background: linear-gradient(145deg, rgba(255,255,255,.115), rgba(255,255,255,.05));
                        box-shadow: 0 7px 18px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.07);
                        font: 400 23px/1 -apple-system, sans-serif;
                    }
                    .label { min-height: 13px; text-align: center; }
                    @media (min-width: 430px) {
                        .grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
                        button { min-height: 87px; }
                        .icon { width: 64px; height: 64px; flex-basis: 64px; border-radius: 16px; }
                    }
                    @media (prefers-reduced-motion: reduce) { button { transition: none; } }
                </style>${groups}`;
            shadow.addEventListener('click', (event) => {
                const button = event.target.closest('button[data-message]');
                if (!button) return;
                this.dispatchEvent(new CustomEvent('airmac-command', {
                    bubbles: true,
                    composed: true,
                    detail: JSON.parse(button.dataset.message),
                }));
            });
        }
    }

    if (typeof customElements !== 'undefined') {
        if (!customElements.get('airmac-status')) customElements.define('airmac-status', AirMacStatus);
        if (!customElements.get('airmac-deck')) customElements.define('airmac-deck', AirMacDeck);
    }

    return { DECK_GROUPS, AirMacStatus, AirMacDeck };
}));
