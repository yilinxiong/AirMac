/* AirMac gestures: browser and Node compatible; initialization is explicit. */
(function(root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory;
    else (root.AirMacModules ||= {})['gestures'] = factory;
})(globalThis, function(ctx) {
    'use strict';
    const {window, document, navigator, localStorage, WebSocket, TextEncoder, Date, setTimeout, clearTimeout, setInterval, clearInterval, requestAnimationFrame, cancelAnimationFrame} = ctx.env;
    const AirMacState = ctx.state;
    const t = (...args) => ctx.i18n.t(...args);
    const sendCmd = (...args) => ctx.connection.sendCmd(...args);
    const showGestureFeedback = (...args) => ctx.settings.showGestureFeedback(...args);
    function bounded(value, limit) {
        return Math.max(-limit, Math.min(limit, value));
    }

    // --- Trackpad Logic ---
    const trackpad = document.getElementById('trackpad');
    let lastTouch = null;
    let lastTouchTime = 0;
    let isMoved = false;
    let isThreeFingerSwiped = false;
    let dragTimer = null;
    let isDragging = false;
    let lastTapTime = 0;
    let isDoubleTap = false;
    const gestureTouches = new AirMacState.GestureTouches();
    const fourFingerAppGesture = new AirMacState.FourFingerAppGesture();
    const touchFeedback = document.getElementById('touch-feedback');
    const touchDots = Array.from({ length: 4 }, () => {
        const dot = document.createElement('span');
        dot.className = 'touch-dot';
        touchFeedback.appendChild(dot);
        return dot;
    });
    let pendingTouchFrame = null;

    function renderTouchFeedback(touches) {
        if (!ctx.settings.settings.touchFeedback || ctx.settings.settings.lowPower) {
            touchDots.forEach((dot) => dot.classList.remove('visible'));
            return;
        }
        const points = Array.from(touches).map((touch) => ({ x: touch.clientX, y: touch.clientY }));
        if (pendingTouchFrame !== null) cancelAnimationFrame(pendingTouchFrame);
        pendingTouchFrame = requestAnimationFrame(() => {
            const bounds = trackpad.getBoundingClientRect();
            touchDots.forEach((dot, index) => {
                const point = points[index];
                dot.classList.toggle('visible', Boolean(point));
                if (point) {
                    dot.style.left = `${point.x - bounds.left}px`;
                    dot.style.top = `${point.y - bounds.top}px`;
                }
            });
            pendingTouchFrame = null;
        });
    }

    function touchCenter(touches) {
        const points = Array.from(touches);
        return {
            x: points.reduce((sum, touch) => sum + touch.clientX, 0) / points.length,
            y: points.reduce((sum, touch) => sum + touch.clientY, 0) / points.length
        };
    }

    function triggerAutoCopy() {
        setTimeout(() => {
            sendCmd({ action: 'auto_copy' });
        }, 200);
    }

    trackpad.addEventListener('touchstart', (e) => {
        e.preventDefault();
        renderTouchFeedback(e.touches);
        const isNewGesture = gestureTouches.max === 0;
        gestureTouches.observe(e.touches.length);
        if (e.touches.length > 1) {
            lastTapTime = 0;
            isDoubleTap = false;
        }
        if (isNewGesture) {
            isMoved = false;
            isThreeFingerSwiped = false;
            fourFingerAppGesture.reset();
            lastTouchTime = Date.now();
        }

        if (e.touches.length === 1) {
            lastTouch = { x: e.touches[0].clientX, y: e.touches[0].clientY };

            if (isNewGesture) {
                const currentTime = Date.now();
                const tapLength = currentTime - lastTapTime;
                if (tapLength < 300 && tapLength > 0) {
                    isDoubleTap = true;
                    sendCmd({ action: 'triple_click' });
                    triggerAutoCopy();
                } else {
                    isDoubleTap = false;
                }
                lastTapTime = currentTime;
            }

            dragTimer = setTimeout(() => {
                isDragging = true;
                if (navigator.vibrate) navigator.vibrate([10, 30, 10]);
                sendCmd({ action: 'mouse_down' });
            }, 500);
        } else if (e.touches.length === 2) {
            clearTimeout(dragTimer);
            if (isDragging) {
                sendCmd({ action: 'mouse_up' });
                isDragging = false;
            }
            lastTouch = {
                x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
                y: (e.touches[0].clientY + e.touches[1].clientY) / 2
            };
        } else if (e.touches.length === 3) {
            clearTimeout(dragTimer);
            if (isDragging) {
                sendCmd({ action: 'mouse_up' });
                isDragging = false;
            }
            lastTouch = {
                x: (e.touches[0].clientX + e.touches[1].clientX + e.touches[2].clientX) / 3,
                y: (e.touches[0].clientY + e.touches[1].clientY + e.touches[2].clientY) / 3
            };
        } else if (e.touches.length === 4) {
            clearTimeout(dragTimer);
            if (isDragging) {
                sendCmd({ action: 'mouse_up' });
                isDragging = false;
            }
            lastTouch = touchCenter(e.touches);
        }
    }, { passive: false });

    trackpad.addEventListener('touchmove', (e) => {
        e.preventDefault();
        renderTouchFeedback(e.touches);
        if (!lastTouch) return;
        gestureTouches.observe(e.touches.length);

        isMoved = true;
        clearTimeout(dragTimer);

        // A four-finger gesture remains four-finger-only while fingers are
        // lifted one by one, so it cannot turn into a three-finger command.
        if (gestureTouches.max >= 4 && e.touches.length < 4) {
            lastTouch = touchCenter(e.touches);
            return;
        }

        if (e.touches.length === 1) {
            const currentTouch = { x: e.touches[0].clientX, y: e.touches[0].clientY };
            const dx = currentTouch.x - lastTouch.x;
            const dy = currentTouch.y - lastTouch.y;
            const moveX = bounded(dx * ctx.settings.settings.pointerSensitivity, 500);
            const moveY = bounded(dy * ctx.settings.settings.pointerSensitivity, 500);
            if (isDragging) {
                sendCmd({ action: 'mouse_drag', dx: moveX, dy: moveY });
            } else {
                sendCmd({ action: 'move', dx: moveX, dy: moveY });
            }
            lastTouch = currentTouch;

        } else if (e.touches.length === 2) {
            const currentTouch = {
                x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
                y: (e.touches[0].clientY + e.touches[1].clientY) / 2
            };
            const dy = currentTouch.y - lastTouch.y;
            const direction = ctx.settings.settings.naturalScroll ? 1 : -1;
            sendCmd({ action: 'scroll', dy: bounded(dy * ctx.settings.settings.scrollSpeed * direction, 1000) });
            lastTouch = currentTouch;

        } else if (e.touches.length === 3) {
            if (isThreeFingerSwiped) return;

            const currentTouch = {
                x: (e.touches[0].clientX + e.touches[1].clientX + e.touches[2].clientX) / 3,
                y: (e.touches[0].clientY + e.touches[1].clientY + e.touches[2].clientY) / 3
            };

            const dx = currentTouch.x - lastTouch.x;
            const dy = currentTouch.y - lastTouch.y;
            const swipeThreshold = 40;

            if (Math.abs(dx) > swipeThreshold || Math.abs(dy) > swipeThreshold) {
                if (Math.abs(dy) > Math.abs(dx) && dy < -swipeThreshold) {
                    sendCmd({ action: ctx.settings.settings.threeFingerUp });
                    isThreeFingerSwiped = true;
                    showGestureFeedback(ctx.settings.settings.threeFingerUp === 'mission_control' ? t('toastMission') : t('toastApps'));
                    if (navigator.vibrate) navigator.vibrate(15);
                } else if (Math.abs(dx) > Math.abs(dy)) {
                    if (dx < -swipeThreshold) {
                        sendCmd({ action: 'space_right' });
                        isThreeFingerSwiped = true;
                        showGestureFeedback(t('toastNextSpace'));
                        if (navigator.vibrate) navigator.vibrate(15);
                    } else if (dx > swipeThreshold) {
                        sendCmd({ action: 'space_left' });
                        isThreeFingerSwiped = true;
                        showGestureFeedback(t('toastPreviousSpace'));
                        if (navigator.vibrate) navigator.vibrate(15);
                    }
                }
            }
        } else if (e.touches.length === 4) {
            const currentTouch = touchCenter(e.touches);
            const dx = currentTouch.x - lastTouch.x;
            const dy = currentTouch.y - lastTouch.y;
            if (ctx.settings.settings.fourFingerUp !== 'disabled' && fourFingerAppGesture.detect(e.touches.length, dx, dy)) {
                sendCmd({ action: ctx.settings.settings.fourFingerUp });
                showGestureFeedback(ctx.settings.settings.fourFingerUp === 'app_launcher' ? t('toastApps') : t('toastMission'));
                if (navigator.vibrate) navigator.vibrate([15, 25, 15]);
            }
        }
    }, { passive: false });

    trackpad.addEventListener('touchend', (e) => {
        e.preventDefault();
        renderTouchFeedback(e.touches);
        clearTimeout(dragTimer);
        const touchDuration = Date.now() - lastTouchTime;
        const completedTouchCount = gestureTouches.finish(e.touches.length);

        // Wait for the final finger before classifying the gesture. This avoids
        // a two-finger tap becoming a right-click followed by a left-click.
        if (e.touches.length === 1) {
            lastTouch = { x: e.touches[0].clientX, y: e.touches[0].clientY };
        } else if (e.touches.length === 2) {
            lastTouch = {
                x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
                y: (e.touches[0].clientY + e.touches[1].clientY) / 2
            };
        } else if (e.touches.length > 0) {
            lastTouch = {
                x: Array.from(e.touches).reduce((sum, touch) => sum + touch.clientX, 0) / e.touches.length,
                y: Array.from(e.touches).reduce((sum, touch) => sum + touch.clientY, 0) / e.touches.length
            };
        } else {
            if (isDragging) {
                isDragging = false;
                sendCmd({ action: 'mouse_up' });
                if (navigator.vibrate) navigator.vibrate(15);
                triggerAutoCopy();
            } else if (!isMoved && !isThreeFingerSwiped) {
                if (touchDuration < 500 && completedTouchCount === 1) {
                    if (!isDoubleTap) {
                        sendCmd({ action: 'click', button: 'left' });
                        if (navigator.vibrate) navigator.vibrate(15);
                    } else {
                        isDoubleTap = false;
                    }
                } else if (touchDuration < 500 && completedTouchCount === 2) {
                    sendCmd({ action: 'click', button: 'right' });
                    if (navigator.vibrate) navigator.vibrate(15);
                } else if (touchDuration >= 500 && completedTouchCount === 1) {
                    sendCmd({ action: 'click', button: 'right' });
                    if (navigator.vibrate) navigator.vibrate(15);
                }
            }
            lastTouch = null;
            isThreeFingerSwiped = false;
            fourFingerAppGesture.reset();
        }
    }, { passive: false });

    trackpad.addEventListener('touchcancel', (e) => {
        e.preventDefault();
        renderTouchFeedback([]);
        clearTimeout(dragTimer);
        if (isDragging) {
            isDragging = false;
            sendCmd({ action: 'mouse_up' });
        }
        lastTouch = null;
        gestureTouches.reset();
        fourFingerAppGesture.reset();
    }, { passive: false });

    // --- Quick Deck controls ---
    document.getElementById('quick-deck').addEventListener('airmac-command', (event) => {
        const sent = sendCmd(event.detail);
        showGestureFeedback(sent ? t('toastCommandSent') : t('toastWaitingConnection'));
        if (navigator.vibrate) navigator.vibrate(15);
    });


    return {};

});
