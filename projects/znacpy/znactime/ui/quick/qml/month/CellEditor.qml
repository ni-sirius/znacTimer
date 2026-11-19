import QtQuick
import ".."

Loader {
    id: cellEditorLoader
    required property var session
    required property var colors
    required property var appearance
    required property var interruptionTarget
    required property int columnIndex
    required property real bodyHeight
    required property real badgeWidth
    required property real badgeHeight
    required property real timeBadgeWidth
    required property string initialValue
    required property string initialText
    required property string editValue
    signal editorOpened(var editor)
    signal editorClosed(var editor)
    signal closeRequested()
    signal initialTextConsumed()
    signal valueCommitted(string value)
    readonly property bool clockEdit: columnIndex === 2 || columnIndex === 3
    focus: true
    x: clockEdit ? (parent.width - width) / 2 : 5
    y: (cellEditorLoader.bodyHeight - height) / 2
    width: clockEdit ? badgeWidth : parent.width - 10
    height: badgeHeight + (clockEdit ? 0 : 2)
    sourceComponent: cellEditorLoader.columnIndex === 4 ? periodEditor : lineEditor
    onLoaded: {
        editorOpened(item)
        session.begin(cellEditorLoader, function() {
            if (item) item.save()
            cellEditorLoader.closeRequested()
        })
        item.focusStart()
        if (cellEditorLoader.initialText !== "") {
            item.typeStart(cellEditorLoader.initialText)
            initialTextConsumed()
        }
    }
    Component.onDestruction: {
        editorClosed(item)
        if (session) session.end(cellEditorLoader)
    }
    TableView.onCommit: { if (item) item.save() }
    Component {
        id: lineEditor
        ClockTextField {
            objectName: cellEditorLoader.columnIndex === 1 ? "specialCellEditor" : "timeCellEditor"
            timeOnly: cellEditorLoader.columnIndex !== 1
            Component.onCompleted: text = cellEditorLoader.initialValue
            selectByMouse: true
            font.pointSize: 10; font.bold: true
            horizontalAlignment: Text.AlignHCenter
            color: timeOnly ? (cellEditorLoader.appearance.textColor || cellEditorLoader.colors.table.empty_text)
                            : cellEditorLoader.colors.model.editing_text
            background: Rectangle { radius: 6; color: cellEditorLoader.appearance.fillColor || cellEditorLoader.colors.table.empty_fill; border.color: cellEditorLoader.colors.primary; border.width: 2 }
            Accessible.name: cellEditorLoader.columnIndex === 1 ? "Special day" : cellEditorLoader.columnIndex === 2 ? "Start time" : "End time"
            function focusStart() { forceActiveFocus(); selectAll() }
            function save() { cellEditorLoader.valueCommitted(text) }
        }
    }
    Component {
        id: periodEditor
        InlineInterruptionEditor {
            colors: cellEditorLoader.colors
            value: cellEditorLoader.editValue
            target: cellEditorLoader.interruptionTarget
            timeBadgeWidth: cellEditorLoader.timeBadgeWidth
            function save() {
                const value = resolvedValue()
                if (value !== null) cellEditorLoader.valueCommitted(value)
            }
            onFinishRequested: { save(); cellEditorLoader.closeRequested() }
        }
    }
}
