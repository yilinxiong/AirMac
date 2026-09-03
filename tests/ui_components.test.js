'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { DECK_GROUPS } = require('../ui_components.js');

test('quick deck exposes only fixed protocol messages', () => {
    const actions = DECK_GROUPS.flatMap((group) => group.actions);
    assert.equal(actions.length, 21);
    assert.equal(actions.some((item) => item.message.action === 'app_launcher'), true);
    assert.equal(actions.some((item) => item.message.command === 'screenshot'), true);
    assert.equal(actions.some((item) => item.message.command === 'open_wifi'), true);
    assert.equal(actions.some((item) => item.message.command === 'open_bluetooth'), true);
    assert.equal(actions.some((item) => item.message.command === 'open_airdrop'), true);
    assert.equal(actions.some((item) => item.message.command === 'cycle_audio_output'), true);
    assert.equal(actions.some((item) => JSON.stringify(item.message).includes('shell')), false);
    for (const item of actions) {
        assert.deepEqual(Object.keys(item.message).sort(),
            item.message.command ? ['action', 'command'] : ['action']);
    }
});
