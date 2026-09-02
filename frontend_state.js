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

    return { ReconnectBackoff, ProjectionState, GestureTouches, FourFingerAppGesture };
}));
