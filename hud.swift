import Cocoa

class HUDWindow: NSWindow {
    init(at point: NSPoint, text: String) {
        let styleMask: NSWindow.StyleMask = [.borderless, .nonactivatingPanel]
        
        let label = NSTextField(labelWithString: text)
        label.font = NSFont.systemFont(ofSize: 14, weight: .medium)
        label.textColor = NSColor.white
        label.alignment = .center
        label.sizeToFit()
        
        let padding: CGFloat = 16
        let width = label.frame.width + padding * 2
        let height: CGFloat = 36
        
        let rect = NSRect(x: point.x + 15, y: point.y - 30, width: width, height: height)
        super.init(contentRect: rect, styleMask: styleMask, backing: .buffered, defer: false)
        
        self.isOpaque = false
        self.backgroundColor = NSColor.clear
        self.level = .floating
        self.ignoresMouseEvents = true
        
        let visualEffect = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: width, height: height))
        visualEffect.material = .hudWindow
        visualEffect.state = .active
        visualEffect.blendingMode = .behindWindow
        visualEffect.wantsLayer = true
        visualEffect.layer?.cornerRadius = 18
        
        label.frame = NSRect(x: 0, y: 9, width: width, height: 20)
        
        visualEffect.addSubview(label)
        self.contentView = visualEffect
    }
}

let app = NSApplication.shared
let mouseLocation = NSEvent.mouseLocation
let text = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "✅ 已复制"

let hud = HUDWindow(at: mouseLocation, text: text)
hud.orderFront(nil)

DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
    NSAnimationContext.runAnimationGroup({ context in
        context.duration = 0.3
        hud.animator().alphaValue = 0
    }) {
        app.terminate(nil)
    }
}

app.run()
