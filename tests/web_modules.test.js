'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { start } = require('../web/app.js');
const state = require('../frontend_state.js');
const modules = Object.fromEntries(['i18n', 'settings', 'background', 'credentials', 'pairing', 'connection', 'projection', 'gestures', 'locale'].map(name => [name, require(`../web/${name}.js`)]));

class Element {
    constructor() {
        this.handlers = {};
        this.value = '';
        this.textContent = '';
        this.style = {};
        this.options = [{}, {}, {}];
        this.dataset = {};
        this.classes = new Set();
        this.classList = {
            add: c => this.classes.add(c), remove: c => this.classes.delete(c),
            toggle: (c, enabled) => enabled ? this.classes.add(c) : this.classes.delete(c),
        };
    }
    addEventListener(name, fn) { (this.handlers[name] ||= []).push(fn); }
    emit(name, details = {}) { return Promise.all((this.handlers[name] || []).map(fn => fn({ preventDefault() {}, ...details }))); }
    setAttribute(name, value) { this[name] = value; }
    setStatus(...args) { this.status = args; }
    focus() {}
    blur() {}
    select() {}
    appendChild() {}
    getBoundingClientRect() { return {left: 0, top: 0}; }
    getContext() { return { fillRect() {}, fillText() {} }; }
}

function environment(paired = true) {
    const elements = new Map();
    const element = id => {
        if (!elements.has(id)) elements.set(id, new Element());
        if (id === 'three-finger-up') elements.get(id).options = [{}, {}];
        return elements.get(id);
    };
    const document = Object.assign(new Element(), {
        hidden: false, body: new Element(), documentElement: new Element(),
        getElementById: element, querySelector: element,
        querySelectorAll: () => [], createElement: () => new Element(),
    });
    const storage = new Map(paired ? [['airmac_device_id', 'device'], ['airmac_device_token', 'token']] : []);
    const timers = new Map(); let next = 0; const sockets = [];
    class Socket {
        static CONNECTING = 0; static OPEN = 1; static CLOSED = 3;
        constructor() { this.readyState = 0; this.sent = []; sockets.push(this); }
        open() { this.readyState = 1; this.onopen(); }
        send(raw) { this.sent.push(JSON.parse(raw)); }
        message(payload) { this.onmessage({data: JSON.stringify(payload)}); }
        close(code = 1000) { this.readyState = 3; this.onclose({code}); }
    }
    let now = 1000;
    const env = Object.assign(new Element(), {
        document, navigator: {language: 'en', userAgent: '', platform: '', maxTouchPoints: 0},
        localStorage: {getItem: k => storage.get(k) ?? null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k)},
        matchMedia: () => ({ matches: true }),
        location: { protocol: 'http:', host: 'testserver' },
        innerWidth: 390, innerHeight: 844,
        setTimeout: (fn, delay) => { timers.set(++next, {fn, delay}); return next; },
        clearTimeout: id => timers.delete(id),
        setInterval: (fn, delay) => { timers.set(++next, {fn, delay, interval: true}); return next; },
        clearInterval: id => timers.delete(id),
        requestAnimationFrame: () => ++next, cancelAnimationFrame() {},
        WebSocket: Socket, TextEncoder, Date: { now: () => now },
        fetch: async () => { throw Error('Unexpected network call'); },
        advance(ms) { now += ms; },
    });
    env.window = env;
    const ctx = start(env, modules, state);
    return {ctx, env, element, sockets, timers, storage};
}

function authenticate(socket) {
    socket.open();
    socket.message({type: 'auth_ok', protocol_version: 2, heartbeat_interval_ms: 5000,
        limits: {message_bytes: 65536, text_bytes: 32768, move_delta: 500, scroll_delta: 1000}});
}

test('bootstrap initializes every module and supports bilingual UI', async () => {
    const {ctx, element, sockets} = environment();
    assert.equal(sockets.length, 1);
    authenticate(sockets[0]);
    assert.equal(sockets[0].sent[0].protocol_version, 2);
    assert.equal(ctx.connection.serverInfo.protocolVersion, 2);
    assert.equal(element('connection-status').status[0], 'online');
    assert.equal(ctx.i18n.language, 'en');
    await element('language-toggle').emit('click');
    assert.equal(ctx.i18n.language, 'zh');
    assert.equal(element('text-title').textContent, '文本输入');
});

test('unsupported handshake stops reconnecting without deleting credentials', () => {
    const {sockets, storage, timers, element} = environment();
    sockets[0].open();
    sockets[0].message({type:'auth_ok', protocol_version:99});
    assert.equal(element('connection-status').status[0], 'error');
    assert.equal(storage.get('airmac_device_token'), 'token');
    assert.equal([...timers.values()].some(timer => !timer.interval), false);
});

test('pairing obtains credentials and starts v2 authentication', async () => {
    const {ctx, env, element, sockets} = environment(false);
    assert.equal(sockets.length, 0);
    let calls = 0;
    env.fetch = async (url, options) => {
        calls++;
        const body = JSON.parse(options.body);
        if (url.endsWith('start')) {
            assert.equal(body.device_name, 'iPhone');
            return {ok: true, json: async () => ({challenge_id: 'challenge'})};
        }
        assert.equal(body.code, '123456');
        return {ok: true, json: async () => ({device_id: 'paired', token: 'secret', device_name: 'iPhone'})};
    };
    await ctx.pairing.startPairing();
    element('pairing-code').value = '123456';
    await ctx.pairing.completePairing();
    assert.equal(calls, 2);
    assert.equal(sockets.length, 1);
    sockets[0].open();
    assert.equal(sockets[0].sent[0].device_id, 'paired');
});

test('suspension closes the connection and resumes without clearing credentials', async () => {
    const {env, sockets, storage, element} = environment();
    authenticate(sockets[0]);
    env.document.hidden = true;
    await env.document.emit('visibilitychange');
    assert.equal(sockets[0].readyState, 3);
    assert.equal(element('connection-status').status[0], 'offline');
    env.document.hidden = false;
    await env.document.emit('visibilitychange');
    assert.equal(sockets.length, 2);
    assert.equal(storage.get('airmac_device_token'), 'token');
});

test('heartbeat and authentication errors follow distinct recovery paths', () => {
    const {ctx, sockets, storage, element, env} = environment();
    authenticate(sockets[0]);
    ctx.connection.probeConnection();
    assert.equal(sockets[0].sent.at(-1).action, 'heartbeat');
    env.advance(40);
    sockets[0].message({type: 'heartbeat_ack'});
    assert.equal(element('connection-status').status[2], 40);
    sockets[0].close(4003);
    assert.equal(storage.has('airmac_device_token'), false);
});

test('text draft retries the same request and clears only on matching success', () => {
    const {ctx, sockets, element} = environment();
    authenticate(sockets[0]);
    const field = element('projection-input'); field.value = 'long text';
    ctx.projection.submitProjection();
    const request = sockets[0].sent.at(-1);
    sockets[0].close(1006);
    assert.equal(field.value, 'long text');
    ctx.connection.connect(); authenticate(sockets[1]);
    ctx.projection.submitProjection();
    assert.equal(sockets[1].sent.at(-1).request_id, request.request_id);
    sockets[1].message({type:'action_result', action:'type_text', request_id:'other', status:'ok'});
    assert.equal(field.value, 'long text');
    sockets[1].message({type:'action_result', action:'type_text', request_id:request.request_id, status:'duplicate'});
    assert.equal(field.value, '');
});

const touches = (n, x=100, y=100) => Array.from({length:n}, (_,i) => ({clientX:x+i*10, clientY:y}));
test('one/two-finger taps and three/four-finger swipes survive extraction', async () => {
    const {sockets, element, env} = environment(); authenticate(sockets[0]);
    const pad = element('trackpad');
    await pad.emit('touchstart', {touches:touches(1)});
    await pad.emit('touchend', {touches:[]});
    assert.deepEqual(sockets[0].sent.at(-1), {action:'click', button:'left'});
    env.advance(1000);
    await pad.emit('touchstart', {touches:touches(2)});
    const before = sockets[0].sent.length;
    await pad.emit('touchend', {touches:touches(1)});
    assert.equal(sockets[0].sent.length, before);
    await pad.emit('touchend', {touches:[]});
    assert.deepEqual(sockets[0].sent.at(-1), {action:'click', button:'right'});
    for (const [n, action] of [[3,'mission_control'],[4,'app_launcher']]) {
        await pad.emit('touchstart', {touches:touches(n)});
        await pad.emit('touchmove', {touches:touches(n,100,40)});
        assert.equal(sockets[0].sent.at(-1).action, action);
        const count = sockets[0].sent.length;
        await pad.emit('touchend', {touches:touches(n-1)});
        await pad.emit('touchend', {touches:[]});
        assert.equal(sockets[0].sent.length, count);
    }
});
