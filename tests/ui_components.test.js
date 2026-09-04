'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { DECK_GROUPS, ICONS, localizeDeckGroups } = require('../ui_components.js');

test('quick deck exposes only fixed protocol messages', () => {
    const actions = DECK_GROUPS.flatMap((group) => group.actions);
    assert.equal(actions.length, 20);
    assert.equal(DECK_GROUPS[0].title, '电源与登录');
    assert.equal(DECK_GROUPS[1].title, '快捷菜单');
    assert.equal(DECK_GROUPS.at(-1).title, '窗口');
    assert.deepEqual(
        DECK_GROUPS[0].actions.map((item) => item.label),
        ['唤醒', '锁定 Mac', '显示器睡眠'],
    );
    assert.equal(actions.some((item) => item.message.action === 'app_launcher'), true);
    assert.equal(actions.some((item) => item.message.command === 'screenshot'), true);
    assert.equal(actions.some((item) => item.message.command === 'open_control_center'), true);
    assert.equal(actions.some((item) => item.message.command === 'close_fullscreen'), true);
    assert.equal(
        actions.find((item) => item.message.command === 'close_fullscreen').label,
        '退出全屏应用',
    );
    assert.equal(actions.some((item) => item.message.command === 'open_wifi'), false);
    assert.equal(actions.some((item) => item.message.command === 'open_bluetooth'), false);
    assert.equal(actions.some((item) => item.message.command === 'open_airdrop'), false);
    assert.equal(actions.some((item) => item.message.command === 'cycle_audio_output'), true);
    assert.equal(actions.some((item) => JSON.stringify(item.message).includes('shell')), false);
    for (const item of actions) {
        assert.equal(typeof ICONS[item.icon], 'string');
        assert.match(ICONS[item.icon], /^</);
        assert.deepEqual(Object.keys(item.message).sort(),
            item.message.command ? ['action', 'command'] : ['action']);
    }
});

test('quick deck labels can switch to English without changing messages', () => {
    const zhActions = DECK_GROUPS.flatMap((group) => group.actions);
    const enGroups = localizeDeckGroups('en');
    const enActions = enGroups.flatMap((group) => group.actions);

    assert.equal(enGroups[0].title, 'Power & Login');
    assert.equal(enGroups[1].title, 'Quick Menu');
    assert.equal(enGroups.at(-1).title, 'Windows');
    assert.deepEqual(
        enGroups[0].actions.map((item) => item.label),
        ['Wake', 'Lock Mac', 'Display Sleep'],
    );
    assert.equal(
        enActions.find((item) => item.message.command === 'close_fullscreen').label,
        'Quit Fullscreen',
    );
    assert.deepEqual(
        enActions.map((item) => item.message),
        zhActions.map((item) => item.message),
    );
});
