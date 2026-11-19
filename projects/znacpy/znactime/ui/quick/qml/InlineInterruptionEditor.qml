import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

FocusScope {
    id: editor
    required property var colors
    required property string value
    required property var target
    required property real timeBadgeWidth
    readonly property real fieldWidth: Math.max(timeBadgeWidth, Math.ceil(clockMetrics.advanceWidth) + 16)
    property bool removed: false
    signal finishRequested()
    objectName: "inlineInterruptionEditor"

    TextMetrics { id: clockMetrics; font: start.font; text: "00:00" }

    function focusStart() { start.forceActiveFocus(); start.selectAll() }
    function advanceField(reverse) {
        if (start.activeFocus && !reverse) { end.forceActiveFocus(); end.selectAll(); return true }
        if (end.activeFocus && reverse) { start.forceActiveFocus(); start.selectAll(); return true }
        return false
    }
    function typeStart(value) { start.typeStart(value) }
    function resolvedValue() {
        if (!removed && start.text.trim() === "" && end.text.trim() === "") return null
        let parts = value.indexOf("-") >= 0 ? value.split(";") : []
        let index = target.period_index
        if (removed) {
            if (target.action === "edit" && index >= 0 && index < parts.length) parts.splice(index, 1)
            else if (target.action === "replace") parts = []
        } else {
            let period = start.text.trim() + "-" + (end.text.trim() || "...")
            if (target.action === "edit" && index >= 0 && index < parts.length) parts[index] = period
            else if (target.action === "add") parts.push(period)
            else parts = [period]
        }
        return parts.join(";") || "00:00"
    }
    Component.onCompleted: {
        if (target.action === "edit" && value.indexOf("-") >= 0) {
            let part = value.split(";")[target.period_index]
            if (part) {
                let times = part.split("-")
                start.text = times[0]
                end.text = times[1] === "..." ? "" : times[1]
            }
        }
    }
    RowLayout {
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(implicitWidth, parent.width)
        height: parent.height
        spacing: 2
        ClockTextField {
            id: start
            objectName: "pauseStartEditor"
            Layout.fillWidth: true
            Layout.preferredWidth: editor.fieldWidth
            Layout.fillHeight: true
            placeholderText: "Start"
            selectByMouse: true
            font.pointSize: 10; font.bold: true
            color: editor.colors.table.interval_text
            horizontalAlignment: Text.AlignHCenter
            background: Rectangle { radius: 6; color: editor.colors.table.interval_background; border.width: 2; border.color: editor.colors.primary }
            Keys.onTabPressed: function(event) { end.forceActiveFocus(); end.selectAll(); event.accepted = true }
            Keys.onBacktabPressed: function(event) { end.forceActiveFocus(); end.selectAll(); event.accepted = true }
            Accessible.name: "Pause start"
        }
        Label { text: "-"; color: editor.colors.table.interval_separator; font.bold: true }
        ClockTextField {
            id: end
            objectName: "pauseEndEditor"
            Layout.fillWidth: true
            Layout.preferredWidth: editor.fieldWidth
            Layout.fillHeight: true
            placeholderText: "End"
            selectByMouse: true
            font.pointSize: 10; font.bold: true
            color: editor.colors.table.interval_text
            horizontalAlignment: Text.AlignHCenter
            background: Rectangle { radius: 6; color: editor.colors.table.interval_background; border.width: 2; border.color: editor.colors.primary }
            Keys.onTabPressed: function(event) { start.forceActiveFocus(); start.selectAll(); event.accepted = true }
            Keys.onBacktabPressed: function(event) { start.forceActiveFocus(); start.selectAll(); event.accepted = true }
            Accessible.name: "Pause end, or blank for active pause"
        }
        ToolButton {
            id: removeButton
            objectName: "removeInlinePause"
            visible: editor.target.action === "edit" || editor.target.action === "replace"
            hoverEnabled: true
            display: AbstractButton.IconOnly
            icon.source: "icons/minus.svg"
            icon.width: 16; icon.height: 16
            icon.color: hovered ? editor.colors.on_primary : editor.colors.table.interval_text
            padding: 0
            Layout.preferredWidth: 28
            Layout.fillHeight: true
            implicitWidth: 28
            background: Rectangle {
                radius: 6
                color: removeButton.hovered ? editor.colors.primary : editor.colors.table.interval_background
                border.width: 2
                border.color: editor.colors.primary
            }
            Accessible.name: "Remove pause period"
            Keys.onReturnPressed: removeButton.clicked()
            Keys.onEnterPressed: removeButton.clicked()
            onClicked: { editor.removed = true; editor.finishRequested() }
        }
    }
}
