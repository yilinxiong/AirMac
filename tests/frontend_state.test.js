'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
    ReconnectBackoff,
    ProjectionState,
    GestureTouches,
    FourFingerAppGesture,
    SettingsStore,
    LatencyTracker,
} = require('../frontend_state.js');

test('reconnect backoff grows, jitters, and resets', () => {
    const backoff = new ReconnectBackoff(() => 0.5);
    assert.equal(backoff.next(), 1000);
    assert.equal(backoff.next(), 2000);
    assert.equal(backoff.next(3000), 3000);
    backoff.reset();
    assert.equal(backoff.next(), 1000);
});

test('projection clears only after matching completion', () => {
    const state = new ProjectionState();
    assert.equal(state.begin('request_1', 'hello'), true);
    assert.equal(state.begin('request_2', 'duplicate click'), false);
    assert.equal(state.finish('other', 'ok').outcome, 'ignored');
    assert.equal(state.finish('request_1', 'ok').outcome, 'confirmed');
    assert.equal(state.shouldClearRestored('hello'), true);
    state.noteUserInput();
    assert.equal(state.shouldClearRestored('hello'), false);
});

test('projection failure keeps the draft eligible for retry', () => {
    const state = new ProjectionState();
    state.begin('request_1', 'keep me');
    assert.deepEqual(state.fail(), { requestId: 'request_1', text: 'keep me' });
    assert.equal(state.isPending, false);
    assert.equal(state.shouldClearRestored('keep me'), false);
});

test('two-finger gesture is classified only after the final lift', () => {
    const touches = new GestureTouches();
    touches.observe(1);
    touches.observe(2);
    assert.equal(touches.finish(1), null);
    assert.equal(touches.finish(0), 2);
    assert.equal(touches.max, 0);
});

test('four-finger upward swipe opens the app launcher once', () => {
    const gesture = new FourFingerAppGesture(40);
    assert.equal(gesture.detect(4, 5, -39), false);
    assert.equal(gesture.detect(4, 8, -55), true);
    assert.equal(gesture.detect(4, 3, -80), false);
    gesture.reset();
    assert.equal(gesture.detect(4, 0, -41), true);
});

test('four-finger app gesture rejects other counts and directions', () => {
    const gesture = new FourFingerAppGesture(40);
    assert.equal(gesture.detect(3, 0, -80), false);
    assert.equal(gesture.detect(4, 80, -50), false);
    assert.equal(gesture.detect(4, 0, 80), false);
});

test('settings are persisted, clamped, and invalid values fall back safely', () => {
    const values = new Map();
    const storage = {
        getItem: (key) => values.get(key) ?? null,
        setItem: (key, value) => values.set(key, value),
        removeItem: (key) => values.delete(key),
    };
    const store = new SettingsStore(storage);
    const saved = store.save({
        pointerSensitivity: 99,
        scrollSpeed: '0.1',
        naturalScroll: false,
        threeFingerUp: 'unknown',
        fourFingerUp: 'disabled',
    });

    assert.equal(saved.pointerSensitivity, 3);
    assert.equal(saved.scrollSpeed, 0.5);
    assert.equal(saved.naturalScroll, false);
    assert.equal(saved.threeFingerUp, 'mission_control');
    assert.equal(saved.fourFingerUp, 'disabled');
    assert.deepEqual(store.load(), saved);

    values.set('airmac_settings_v1', '{bad json');
    assert.equal(store.load().pointerSensitivity, 1.6);
    assert.equal(store.reset().touchFeedback, true);
});

test('latency tracker smooths heartbeat round trips and resets', () => {
    const latency = new LatencyTracker(0.25);
    assert.equal(latency.acknowledge(100), null);
    latency.sent(100);
    assert.equal(latency.acknowledge(140), 40);
    latency.sent(200);
    assert.equal(latency.acknowledge(280), 50);
    latency.reset();
    assert.equal(latency.value, null);
});
