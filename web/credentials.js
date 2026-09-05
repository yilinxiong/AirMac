/* AirMac credentials: browser and Node compatible; initialization is explicit. */
(function(root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory;
    else (root.AirMacModules ||= {})['credentials'] = factory;
})(globalThis, function(ctx) {
    'use strict';
    const {window, document, navigator, localStorage, WebSocket, TextEncoder, Date, setTimeout, clearTimeout, setInterval, clearInterval, requestAnimationFrame, cancelAnimationFrame} = ctx.env;
    const AirMacState = ctx.state;
    const keys = { deviceId: 'airmac_device_id', token: 'airmac_device_token', deviceName: 'airmac_device_name' };
    const credentials = {deviceId: localStorage.getItem(keys.deviceId), deviceToken: localStorage.getItem(keys.token), deviceName: localStorage.getItem(keys.deviceName) || 'iPhone'};
    localStorage.removeItem('mac_remote_device_id');
    localStorage.removeItem('mac_remote_device_name');
    credentials.clear = () => {
        credentials.deviceId = credentials.deviceToken = null;
        localStorage.removeItem(keys.deviceId);
        localStorage.removeItem(keys.token);
    };
    credentials.save = (result) => {
        credentials.deviceId = result.device_id;
        credentials.deviceToken = result.token;
        credentials.deviceName = result.device_name;
        localStorage.setItem(keys.deviceId, credentials.deviceId);
        localStorage.setItem(keys.token, credentials.deviceToken);
        localStorage.setItem(keys.deviceName, credentials.deviceName);
    };
    return credentials;
});
