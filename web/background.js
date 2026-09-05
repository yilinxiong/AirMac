/* AirMac background: browser and Node compatible; initialization is explicit. */
(function(root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory;
    else (root.AirMacModules ||= {})['background'] = factory;
})(globalThis, function(ctx) {
    'use strict';
    const {window, document, navigator, localStorage, WebSocket, TextEncoder, Date, setTimeout, clearTimeout, setInterval, clearInterval, requestAnimationFrame, cancelAnimationFrame} = ctx.env;
    const AirMacState = ctx.state;
    // Matrix Rain Setup
    const canvas = document.getElementById('matrixCanvas');
    const drawing = canvas.getContext('2d');

    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    const chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ'.split('');
    const fontSize = 16;
    const columns = Math.floor(canvas.width / fontSize) + 1;
    const drops = [];
    for(let x = 0; x < columns; x++) {
        drops[x] = Math.random() * -100;
    }

    function drawMatrix() {
        drawing.fillStyle = 'rgba(28, 28, 30, 0.08)';
        drawing.fillRect(0, 0, canvas.width, canvas.height);

        drawing.fillStyle = 'rgba(0, 191, 255, 0.8)';
        drawing.font = fontSize + 'px monospace';

        for(let i = 0; i < drops.length; i++) {
            if(drops[i] > 0) {
                const text = chars[Math.floor(Math.random() * chars.length)];
                drawing.fillText(text, i * fontSize, drops[i] * fontSize);
            }

            if(drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
                drops[i] = 0;
            }
            drops[i]++;
        }
    }
    let lastMatrixFrame = 0;
    function animateMatrix(timestamp) {
        const frameInterval = ctx.settings.settings.lowPower ? Infinity : (ctx.settings.settings.reduceMotion ? 120 : 35);
        if (!document.hidden && timestamp - lastMatrixFrame >= frameInterval) {
            drawMatrix();
            lastMatrixFrame = timestamp;
        }
        requestAnimationFrame(animateMatrix);
    }
    requestAnimationFrame(animateMatrix);



    return {};

});
