import QtQuick
import QtQuick.Controls

TextField {
    property bool timeOnly: true
    property var controller: null
    property bool compactEntry: false
    inputMask: timeOnly ? "99:99;_" : ""
    readonly property string enteredText: {
        if (!timeOnly) return text
        if (text === ":") return ""
        return compactEntry && /^(?:__:_\d|__:\d{2}|_\d:\d{2})$/.test(displayText) ? text.replace(":", "") : text
    }

    function replacingTime() {
        return (text === ":" && selectionStart === 0) || selectionEnd - selectionStart === length
    }

    function appendingDigits() {
        return compactEntry && !selectedText && cursorPosition === length
    }

    function setCompactTime(digits) {
        compactEntry = true
        remove(0, length)
        if (digits) {
            // Skip the separator when counting backwards from the last digit.
            const start = digits.length <= 2 ? 5 - digits.length : 4 - digits.length
            insert(start, digits)
        }
        select(length, length)
    }

    function typeStart(value) {
        if (timeOnly && !/^[0-9:]$/.test(value)) return
        if (timeOnly && value !== ":") {
            setCompactTime(value)
        } else {
            text = value
            const position = timeOnly ? 3 : length
            select(position, position)
        }
    }

    Keys.onPressed: function(event) {
        if (!timeOnly) return
        const modified = event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
        if (controller && event.matches(StandardKey.Paste)) {
            event.accepted = true
            const value = controller.clipboardText()
            if (!/^(?:[0-9]{1,4}|[0-9]{2}:[0-9]{2})$/.test(value)) return
            if (replacingTime() && value.indexOf(":") === -1) {
                setCompactTime(value)
            } else {
                compactEntry = false
                paste()
            }
        } else if (event.key === Qt.Key_Backspace && !modified && appendingDigits()) {
            event.accepted = true
            setCompactTime(text.replace(":", "").slice(0, -1))
        } else if (event.key === Qt.Key_Delete || event.key === Qt.Key_Backspace
                   || event.matches(StandardKey.Cut)) {
            if (event.key !== Qt.Key_Delete || !appendingDigits()) compactEntry = false
        } else if (event.text && !modified) {
            if (/^[0-9]$/.test(event.text)) {
                const replace = replacingTime()
                if (replace || appendingDigits()) {
                    const digits = replace ? "" : text.replace(":", "")
                    if (digits.length < 4) setCompactTime(digits + event.text)
                    event.accepted = true
                } else {
                    compactEntry = false
                }
            } else if (event.text === ":") {
                if (appendingDigits()) {
                    const digits = text.replace(":", "")
                    if (digits.length <= 2) {
                        remove(0, length)
                        insert(0, digits)
                        select(3, 3)
                    }
                    event.accepted = true
                }
                compactEntry = false
            } else if (event.text.charCodeAt(0) >= 32) {
                event.accepted = true
            }
        }
    }
}
