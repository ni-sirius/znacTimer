import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AppDialog {
    id: dialog
    required property var controller
    property int editRow: -1
    property int editColumn: 4
    property var editTarget: ({})
    property var periods: []
    property bool loading: false
    property bool periodsRemoved: false
    property string originalValue: ""
    objectName: "cellEditorDialog"
    title: editColumn === 1 ? "Special day" : "Interruption"
    modal: true
    preferredWidth: Math.min(610, ownerWindow.width - 32)
    standardButtons: Dialog.Save | Dialog.Cancel
    footer: DialogButtonBox {
        standardButtons: Dialog.Save | Dialog.Cancel
        delegate: AppButton { colors: dialog.controller.state.colors }
    }

    function edit(row, column) {
        loading = true
        editRow = row
        editColumn = column
        editTarget = controller.beginCellEdit(row, column)
        let value = controller.cellValue(row, column)
        originalValue = value
        special.currentIndex = Math.max(0, special.find(value))
        special.editText = value
        raw.text = value
        periods = []
        periodsRemoved = false
        if (column === 4 && value.indexOf("-") >= 0) {
            periods = value.split(";").map(function(part) {
                let ends = part.trim().split("-")
                return {start: ends[0].trim(), end: ends[1].trim()}
            })
            mode.currentIndex = 1
        } else {
            mode.currentIndex = 0
        }
        loading = false
        viewport.contentY = 0
        open()
    }

    function periodText() {
        let result = []
        for (let i = 0; i < periodRows.count; ++i) {
            let item = periodRows.itemAt(i)
            let start = item.startValue.text.trim()
            let end = item.endValue.text.trim()
            if (start === "" && end === "") continue
            result.push(start + "-" + (end || "..."))
        }
        return result.length ? result.join(";") : (periodsRemoved && periodRows.count === 0 ? "00:00" : null)
    }

    onAccepted: {
        let value = editColumn === 1 ? special.editText
                                    : (mode.currentIndex === 1 ? periodText() : raw.text)
        if (editColumn === 4 && (value === null || value.trim() === "" || value === originalValue)) return
        controller.commitCellEdit(editTarget, value)
    }

    contentItem: Flickable {
        id: viewport
        objectName: "interruptionViewport"
        implicitHeight: form.implicitHeight
        contentWidth: width
        contentHeight: form.height
        flickableDirection: Flickable.VerticalFlick
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        ScrollBar.vertical: ScrollBar { id: scrollbar }

        function revealFocusedControl() {
            const item = dialog.dialogWindow.activeFocusItem
            for (let parent = item; parent; parent = parent.parent) {
                if (parent !== form) continue
                const top = item.mapToItem(contentItem, 0, 0).y
                const bottom = top + item.height
                if (top < contentY || bottom > contentY + height) {
                    const target = top < contentY ? top : bottom - height
                    contentY = Math.max(0, Math.min(target, contentHeight - height))
                }
                break
            }
        }
        Connections {
            target: dialog.dialogWindow
            function onActiveFocusItemChanged() { Qt.callLater(viewport.revealFocusedControl) }
        }

        ColumnLayout {
            id: form
            width: viewport.width - (viewport.contentHeight > viewport.height ? scrollbar.width + 4 : 0)
            height: implicitHeight
            spacing: 14
            AppComboBox {
                colors: dialog.controller.state.colors
                id: special
                objectName: "specialDayInput"
                visible: dialog.editColumn === 1
                Layout.fillWidth: true
                editable: true
                model: ["Normal day", "Weekend", "Vacation", "Sick", "Public holiday", "No data"]
                Accessible.name: "Special day"
            }
            AppComboBox {
                colors: dialog.controller.state.colors
                id: mode
                objectName: "interruptionMode"
                visible: dialog.editColumn === 4
                Layout.fillWidth: true
                model: ["Duration or text", "Individual periods"]
                Accessible.name: "Interruption entry mode"
            }
            AppTextField {
                colors: dialog.controller.state.colors
                id: raw
                objectName: "interruptionInput"
                visible: dialog.editColumn === 4 && mode.currentIndex === 0
                Layout.fillWidth: true
                placeholderText: "00:30 or 12:00-12:30;15:00-..."
                selectByMouse: true
                Accessible.name: "Interruption duration or periods"
            }
            ColumnLayout {
                visible: dialog.editColumn === 4 && mode.currentIndex === 1
                Layout.fillWidth: true
                Repeater {
                    id: periodRows
                    model: dialog.periods
                    delegate: RowLayout {
                        id: periodRow
                        required property var modelData
                        required property int index
                        property alias startValue: startInput
                        property alias endValue: endInput
                        AppTextField {
                            colors: dialog.controller.state.colors
                            id: startInput
                            objectName: "pauseStart_" + periodRow.index
                            Layout.fillWidth: true
                            text: periodRow.modelData.start
                            placeholderText: "12:00"
                            Accessible.name: "Pause start"
                        }
                        Label { text: "–" }
                        AppTextField {
                            colors: dialog.controller.state.colors
                            id: endInput
                            Layout.fillWidth: true
                            text: periodRow.modelData.end
                            placeholderText: "..."
                            Accessible.name: "Pause end, or blank for an active pause"
                        }
                        AppButton {
                            objectName: "removePausePeriod_" + periodRow.index
                            colors: dialog.controller.state.colors
                            text: "Remove"
                            Accessible.name: "Remove pause period"
                            onClicked: {
                                let values = []
                                for (let i = 0; i < periodRows.count; ++i) {
                                    let item = periodRows.itemAt(i)
                                    if (i !== periodRow.index)
                                        values.push({start: item.startValue.text, end: item.endValue.text})
                                }
                                dialog.periodsRemoved = true
                                dialog.periods = values
                            }
                        }
                    }
                }
                AppButton {
                    objectName: "addPausePeriod"
                    colors: dialog.controller.state.colors
                    text: "Add period"
                    onClicked: {
                        let values = []
                        for (let i = 0; i < periodRows.count; ++i) {
                            let item = periodRows.itemAt(i)
                            values.push({start: item.startValue.text, end: item.endValue.text})
                        }
                        values.push({start: "", end: ""})
                        dialog.periods = values
                        Qt.callLater(function() {
                            const row = periodRows.itemAt(periodRows.count - 1)
                            if (row && dialog.visible) row.startValue.forceActiveFocus()
                        })
                    }
                }
            }
            Label {
                visible: dialog.editColumn === 4
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: "Use HH:MM for a duration. Periods use start–end times; leave the end blank or use ... for an active pause."
            }
        }
    }
}
