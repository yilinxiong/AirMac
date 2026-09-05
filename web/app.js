(function(root) {
    'use strict';
    function start(env = root, modules = root.AirMacModules, state = root.AirMacState) {
        const ctx = { env, state };
        for (const name of ['i18n', 'settings', 'background', 'credentials', 'pairing', 'connection', 'projection', 'gestures', 'locale']) {
            ctx[name] = modules[name](ctx);
        }
        if ('serviceWorker' in env.navigator && env.isSecureContext) {
            env.addEventListener('load', () => {
                env.navigator.serviceWorker.register('/service-worker.js').catch(() => {});
            });
        }
        ctx.connection.start();
        return ctx;
    }
    if (typeof module === 'object' && module.exports) module.exports = { start };
    else start();
})(globalThis);
