import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

FocusScope {
    id: editor
    required property var colors
    required property string value
    required property var target
    property bool removed: false
    signal finishRequested()
    objectName: "inlineInterruptionEditor"

    function focusStart() { start.forceActiveFocus(); start.selectAll() }
    function resolvedValue() {
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
        anchors.fill: parent
        spacing: 4
        TextField {
            id: start
            objectName: "pauseStartEditor"
            Layout.fillWidth: true
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
        TextField {
            id: end
            objectName: "pauseEndEditor"
            Layout.fillWidth: true
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
        AppButton {
            colors: editor.colors
            visible: editor.target.action === "edit" || editor.target.action === "replace"
            text: "−"
            font.pixelSize: 18
            Layout.preferredWidth: 28
            Layout.fillHeight: true
            implicitWidth: 28
            background: Rectangle { radius: 6; color: editor.colors.table.interval_background; border.width: 2; border.color: editor.colors.primary }
            Accessible.name: "Remove pause period"
            onClicked: { editor.removed = true; editor.finishRequested() }
        }
    }
}
