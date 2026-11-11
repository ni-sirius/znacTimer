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
    objectName: "cellEditorDialog"
    title: editColumn === 1 ? "Special day" : "Interruption"
    modal: true
    width: Math.min(610, ownerWindow.width - 32)
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
        special.currentIndex = Math.max(0, special.find(value))
        special.editText = value
        raw.text = value
        periods = []
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
        open()
    }

    function periodText() {
        let result = []
        for (let i = 0; i < periodRows.count; ++i) {
            let item = periodRows.itemAt(i)
            result.push(item.startValue.text.trim() + "-" + (item.endValue.text.trim() || "..."))
        }
        return result.join(";")
    }

    onAccepted: {
        let value = editColumn === 1 ? special.editText
                                    : (mode.currentIndex === 1 ? periodText() : raw.text)
        controller.commitCellEdit(editTarget, value)
    }

    contentItem: ColumnLayout {
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
                            dialog.periods = values
                        }
                    }
                }
            }
            AppButton {
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
