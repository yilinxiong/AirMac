on containsAny(valueText, targetNames)
    repeat with targetName in targetNames
        if valueText contains (targetName as text) then return true
    end repeat
    return false
end containsAny

on elementMatches(uiElement, targetNames)
    tell application "System Events"
        try
            if my containsAny(name of uiElement as text, targetNames) then return true
        end try
        try
            if my containsAny(description of uiElement as text, targetNames) then return true
        end try
        try
            if my containsAny(value of uiElement as text, targetNames) then return true
        end try
    end tell
    return false
end elementMatches

on pressMatching(uiElements, targetNames)
    tell application "System Events"
        repeat with uiElement in uiElements
            if my elementMatches(uiElement, targetNames) then
                try
                    perform action "AXPress" of uiElement
                    return true
                end try
                try
                    click uiElement
                    return true
                end try
            end if
        end repeat
    end tell
    return false
end pressMatching

on run argv
    set targetKey to item 1 of argv
    if targetKey is "wifi" then
        set targetNames to {"Wi-Fi", "Wi‑Fi", "无线局域网"}
    else if targetKey is "bluetooth" then
        set targetNames to {"Bluetooth", "蓝牙"}
    else if targetKey is "airdrop" then
        set targetNames to {"AirDrop", "隔空投送"}
    else
        error "Unsupported Control Center target"
    end if

    -- The caller sends the global Fn-C shortcut first. Only inspect the
    -- resulting panel here: scanning or focusing the menu bar is both slower
    -- and unreliable while another application owns a full-screen Space.
    repeat 10 times
        tell application "System Events"
            tell process "ControlCenter"
                try
                    set panelElements to entire contents of window 1
                    if my pressMatching(panelElements, targetNames) then return "opened"
                end try
            end tell
        end tell
        delay 0.03
    end repeat
    error "Control Center target not found"
end run
