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
                { label: '唤醒', icon: '☀︎', theme: 'sunrise', message: { action: 'wake_watch' }, tone: 'accent' },
                { label: '锁定 Mac', icon: '⌾', theme: 'lock', message: { action: 'quick_action', command: 'lock_screen' }, tone: 'danger' },
                { label: '显示器睡眠', icon: '☾', theme: 'sleep', message: { action: 'display_sleep' } },
            ],
        },
        {
            title: '快捷菜单',
            actions: [
                { label: '控制中心', icon: '◩', theme: 'control', message: { action: 'quick_action', command: 'open_control_center' }, tone: 'accent' },
                { label: 'Apps', icon: '▦', theme: 'apps', message: { action: 'app_launcher' } },
                { label: '调度中心', icon: '◇', theme: 'mission', message: { action: 'mission_control' } },
                { label: '播放 / 暂停', icon: '▶︎', theme: 'media', message: { action: 'media', command: 'playpause' } },
                { label: '全屏', icon: '⛶', theme: 'fullscreen', message: { action: 'media', command: 'fullscreen' } },
                { label: '退出全屏应用', icon: '×', theme: 'close', message: { action: 'quick_action', command: 'close_fullscreen' }, tone: 'danger' },
            ],
        },
        {
            title: '声音与显示',
            actions: [
                { label: '音量减', icon: '▾', theme: 'volume-down', message: { action: 'quick_action', command: 'volume_down' } },
                { label: '静音', icon: '◌', theme: 'mute', message: { action: 'quick_action', command: 'volume_mute' } },
                { label: '音量加', icon: '▴', theme: 'volume-up', message: { action: 'quick_action', command: 'volume_up' } },
                { label: '切换扬声器', icon: '◖', theme: 'speaker', message: { action: 'quick_action', command: 'cycle_audio_output' }, tone: 'accent' },
                { label: '亮度减', icon: '☼', theme: 'dim', message: { action: 'quick_action', command: 'brightness_down' } },
                { label: '亮度加', icon: '☀︎', theme: 'bright', message: { action: 'quick_action', command: 'brightness_up' } },
                { label: '截屏到剪贴板', icon: '⌗', theme: 'screenshot', message: { action: 'quick_action', command: 'screenshot' } },
            ],
        },
        {
            title: '窗口',
            actions: [
                { label: '左半屏', icon: '◧', theme: 'window-left', message: { action: 'quick_action', command: 'window_left' } },
                { label: '填充', icon: '▣', theme: 'window-fill', message: { action: 'quick_action', command: 'window_fill' } },
                { label: '右半屏', icon: '◨', theme: 'window-right', message: { action: 'quick_action', command: 'window_right' } },
                { label: '居中', icon: '▢', theme: 'window-center', message: { action: 'quick_action', command: 'window_center' } },
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
                            <button type="button" data-message='${JSON.stringify(item.message)}' data-tone="${item.tone || ''}" data-theme="${item.theme || ''}">
                                <span class="icon">${item.icon}</span><span class="label">${item.label}</span>
                            </button>`).join('')}
                    </div>
                </section>`).join('');
            shadow.innerHTML = `
                <style>
                    :host { display: block; min-height: 0; color: white; }
                    section + section { margin-top: 20px; }
                    h2 { margin: 0 0 9px 3px; color: rgba(255,255,255,.43); font: 600 11px/1.2 -apple-system, sans-serif; letter-spacing: .09em; text-transform: uppercase; }
                    .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 15px 8px; }
                    button {
                        min-width: 0; min-height: 82px; padding: 0 1px;
                        display: flex; flex-direction: column; align-items: center; justify-content: flex-start; gap: 7px;
                        border: 0; border-radius: 18px;
                        background: transparent; color: rgba(255,255,255,.82);
                        box-shadow: none; font: 500 10.5px/1.12 -apple-system, BlinkMacSystemFont, sans-serif;
                        transition: transform .12s ease, filter .12s ease;
                        -webkit-tap-highlight-color: transparent; touch-action: manipulation;
                    }
                    button:active { transform: scale(.94); }
                    button:active .icon { filter: brightness(1.14) saturate(1.08); box-shadow: 0 5px 12px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.22); }
                    button[data-tone="accent"] { color: #75baff; }
                    button[data-tone="danger"] { color: #ff8a84; }
                    .icon {
                        width: 60px; height: 60px; flex: 0 0 60px;
                        display: grid; place-items: center; box-sizing: border-box;
                        border: 1px solid rgba(255,255,255,.16); border-radius: 13.5px;
                        background:
                            radial-gradient(circle at 28% 18%, rgba(255,255,255,.42), transparent 24px),
                            linear-gradient(145deg, var(--icon-from), var(--icon-to));
                        box-shadow: 0 8px 17px var(--icon-glow), inset 0 1px 0 rgba(255,255,255,.25);
                        color: var(--icon-color, rgba(255,255,255,.96));
                        font: 500 24px/1 -apple-system, BlinkMacSystemFont, sans-serif;
                        text-shadow: 0 1px 6px rgba(0,0,0,.28);
                    }
                    .label { min-height: 12px; text-align: center; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
                    button[data-theme="sunrise"] { --icon-from: #ffd86f; --icon-to: #ff7a59; --icon-glow: rgba(255,138,64,.24); }
                    button[data-theme="lock"] { --icon-from: #ff6b6b; --icon-to: #a73446; --icon-glow: rgba(255,78,78,.23); }
                    button[data-theme="sleep"] { --icon-from: #5968ff; --icon-to: #161f65; --icon-glow: rgba(78,93,255,.22); }
                    button[data-theme="control"] { --icon-from: #5ac8fa; --icon-to: #007aff; --icon-glow: rgba(0,122,255,.26); }
                    button[data-theme="apps"] { --icon-from: #8e8e93; --icon-to: #3a3a3c; --icon-glow: rgba(255,255,255,.11); }
                    button[data-theme="mission"] { --icon-from: #af52de; --icon-to: #5856d6; --icon-glow: rgba(175,82,222,.22); }
                    button[data-theme="media"] { --icon-from: #ff9f0a; --icon-to: #ff375f; --icon-glow: rgba(255,82,58,.23); }
                    button[data-theme="fullscreen"] { --icon-from: #64d2ff; --icon-to: #0a84ff; --icon-glow: rgba(10,132,255,.23); }
                    button[data-theme="close"] { --icon-from: #ff453a; --icon-to: #7a1f22; --icon-glow: rgba(255,69,58,.24); }
                    button[data-theme="volume-down"] { --icon-from: #30d158; --icon-to: #248a3d; --icon-glow: rgba(48,209,88,.2); }
                    button[data-theme="mute"] { --icon-from: #a1a1a6; --icon-to: #48484a; --icon-glow: rgba(180,180,188,.15); }
                    button[data-theme="volume-up"] { --icon-from: #32d74b; --icon-to: #00a35b; --icon-glow: rgba(50,215,75,.21); }
                    button[data-theme="speaker"] { --icon-from: #0a84ff; --icon-to: #5e5ce6; --icon-glow: rgba(94,92,230,.24); }
                    button[data-theme="dim"] { --icon-from: #8e8e93; --icon-to: #2c2c2e; --icon-glow: rgba(142,142,147,.14); }
                    button[data-theme="bright"] { --icon-from: #ffd60a; --icon-to: #ff9f0a; --icon-glow: rgba(255,214,10,.22); }
                    button[data-theme="screenshot"] { --icon-from: #bf5af2; --icon-to: #5e5ce6; --icon-glow: rgba(191,90,242,.22); }
                    button[data-theme="window-left"] { --icon-from: #5e5ce6; --icon-to: #0a84ff; --icon-glow: rgba(94,92,230,.2); }
                    button[data-theme="window-fill"] { --icon-from: #40c8e0; --icon-to: #30b0c7; --icon-glow: rgba(64,200,224,.18); }
                    button[data-theme="window-right"] { --icon-from: #0a84ff; --icon-to: #34c759; --icon-glow: rgba(52,199,89,.2); }
                    button[data-theme="window-center"] { --icon-from: #ff9f0a; --icon-to: #bf5af2; --icon-glow: rgba(255,159,10,.2); }
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
