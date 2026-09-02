(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    root.AirMacState = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    class ReconnectBackoff {
        constructor(random = Math.random) {
            this.random = random;
            this.attempts = 0;
        }

        next(fixedDelay = null) {
            const base = fixedDelay ?? Math.min(30000, 1000 * (2 ** this.attempts));
            if (fixedDelay === null) this.attempts += 1;
            return Math.round(base * (0.8 + this.random() * 0.4));
        }

        reset() {
            this.attempts = 0;
        }
    }

    class ProjectionState {
        constructor() {
            this.pending = null;
            this.confirmedText = '';
        }

        get isPending() {
            return this.pending !== null;
        }

        begin(requestId, text) {
            if (this.pending) return false;
            this.pending = { requestId, text };
            return true;
        }

        fail() {
            if (!this.pending) return null;
            const failed = this.pending;
            this.pending = null;
            return failed;
        }

        finish(requestId, status) {
            if (!this.pending || this.pending.requestId !== requestId) {
                return { outcome: 'ignored', text: '' };
            }
            const text = this.pending.text;
            this.pending = null;
            if (status === 'ok' || status === 'duplicate') {
                this.confirmedText = text;
                return { outcome: 'confirmed', text };
            }
            return { outcome: 'error', text };
        }

        noteUserInput() {
            this.confirmedText = '';
        }

        forgetConfirmed() {
            this.confirmedText = '';
        }

        shouldClearRestored(value) {
            return !this.pending && Boolean(this.confirmedText) && value === this.confirmedText;
        }
    }

    class GestureTouches {
        constructor() {
            this.max = 0;
        }

        observe(count) {
            this.max = Math.max(this.max, count);
            return this.max;
        }

        finish(remainingTouches) {
            if (remainingTouches > 0) return null;
            const completed = this.max;
            this.max = 0;
            return completed;
        }

        reset() {
            this.max = 0;
        }
    }

    class FourFingerAppGesture {
        constructor(threshold = 40) {
            this.threshold = threshold;
            this.triggered = false;
        }

        detect(touchCount, dx, dy) {
            if (this.triggered || touchCount !== 4) return false;
            if (dy >= -this.threshold || Math.abs(dy) <= Math.abs(dx)) return false;
            this.triggered = true;
            return true;
        }

        reset() {
            this.triggered = false;
        }
    }

    const DEFAULT_SETTINGS = Object.freeze({
        pointerSensitivity: 1.6,
        scrollSpeed: 1,
        naturalScroll: true,
        reduceMotion: false,
        lowPower: false,
        touchFeedback: true,
        threeFingerUp: 'mission_control',
        fourFingerUp: 'app_launcher',
    });

    function clampNumber(value, minimum, maximum, fallback) {
        const number = Number(value);
        if (!Number.isFinite(number)) return fallback;
        return Math.min(maximum, Math.max(minimum, number));
    }

    function normalizeSettings(value = {}) {
        const candidate = value && typeof value === 'object' ? value : {};
        const threeFingerUp = ['mission_control', 'app_launcher'].includes(candidate.threeFingerUp)
            ? candidate.threeFingerUp
            : DEFAULT_SETTINGS.threeFingerUp;
        const fourFingerUp = ['app_launcher', 'mission_control', 'disabled'].includes(candidate.fourFingerUp)
            ? candidate.fourFingerUp
            : DEFAULT_SETTINGS.fourFingerUp;
        return {
            pointerSensitivity: clampNumber(
                candidate.pointerSensitivity,
                0.6,
                3,
                DEFAULT_SETTINGS.pointerSensitivity,
            ),
            scrollSpeed: clampNumber(
                candidate.scrollSpeed,
                0.5,
                3,
                DEFAULT_SETTINGS.scrollSpeed,
            ),
            naturalScroll: typeof candidate.naturalScroll === 'boolean'
                ? candidate.naturalScroll
                : DEFAULT_SETTINGS.naturalScroll,
            reduceMotion: typeof candidate.reduceMotion === 'boolean'
                ? candidate.reduceMotion
                : DEFAULT_SETTINGS.reduceMotion,
            lowPower: typeof candidate.lowPower === 'boolean'
                ? candidate.lowPower
                : DEFAULT_SETTINGS.lowPower,
            touchFeedback: typeof candidate.touchFeedback === 'boolean'
                ? candidate.touchFeedback
                : DEFAULT_SETTINGS.touchFeedback,
            threeFingerUp,
            fourFingerUp,
        };
    }

    class SettingsStore {
        constructor(storage, key = 'airmac_settings_v1') {
            this.storage = storage;
            this.key = key;
        }

        load() {
            try {
                const stored = this.storage.getItem(this.key);
                return normalizeSettings(stored ? JSON.parse(stored) : {});
            } catch (_) {
                return normalizeSettings();
            }
        }

        save(value) {
            const settings = normalizeSettings(value);
            this.storage.setItem(this.key, JSON.stringify(settings));
            return settings;
        }

        reset() {
            this.storage.removeItem(this.key);
            return normalizeSettings();
        }
    }

    class LatencyTracker {
        constructor(alpha = 0.3) {
            this.alpha = clampNumber(alpha, 0.05, 1, 0.3);
            this.sentAt = null;
            this.value = null;
        }

        sent(now = Date.now()) {
            this.sentAt = now;
        }

        acknowledge(now = Date.now()) {
            if (this.sentAt === null) return this.value;
            const sample = Math.max(0, now - this.sentAt);
            this.sentAt = null;
            this.value = this.value === null
                ? sample
                : Math.round(this.value * (1 - this.alpha) + sample * this.alpha);
            return this.value;
        }

        reset() {
            this.sentAt = null;
            this.value = null;
        }
    }

    return {
        ReconnectBackoff,
        ProjectionState,
        GestureTouches,
        FourFingerAppGesture,
        DEFAULT_SETTINGS,
        normalizeSettings,
        SettingsStore,
        LatencyTracker,
    };
}));
