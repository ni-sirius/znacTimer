import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AppDialog {
    id: dialog
    required property var controller
    required property var ui
    property int kind: 0
    property var schedule: ({days: [480, 480, 480, 480, 480, 0, 0], special: 0})
    objectName: "settingsDialog"
    title: kind === 0 ? "Appearance" : "Work schedule"
    modal: true
    preferredWidth: Math.min(kind === 0 ? 560 : 660, ownerWindow.width - 32)
    preferredHeight: Math.min(kind === 0 ? 460 : 640, ownerWindow.height - 32)
    standardButtons: Dialog.Save | Dialog.Cancel
    background: Rectangle { color: dialog.ui.colors.header.surface; border.color: dialog.ui.colors.header.border; radius: 12 }
    footer: DialogButtonBox {
        standardButtons: Dialog.Save | Dialog.Cancel
        delegate: AppButton { colors: dialog.ui.colors }
    }

    function showSection(index) {
        kind = index
        navigation.currentIndex = 0
        schedule = controller.scheduleSettings()
        expected.checked = ui.showExpectedEnd
        fitHeight.checked = ui.fitHeight
        initialWidth.value = ui.initialWidth
        initialHeight.value = ui.initialHeight
        specialHours.value = Math.floor((schedule.special || 0) / 60)
        specialMinutes.value = (schedule.special || 0) % 60
        open()
    }
    onAccepted: {
        controller.saveWindowSettings(fitHeight.checked, initialWidth.value, initialHeight.value)
        let days = []
        for (let i = 0; i < dayInputs.count; ++i)
            days.push(dayInputs.itemAt(i).minutes)
        controller.saveSchedule(days, specialHours.value * 60 + specialMinutes.value, expected.checked)
    }

    contentItem: RowLayout {
        spacing: 12
        ListView {
            id: navigation
            Layout.preferredWidth: 145
            Layout.fillHeight: true
            clip: true
            spacing: 4
            model: dialog.kind === 0 ? ["Color scheme", "Startup window"] : ["Work schedule"]
            delegate: ItemDelegate {
                required property string modelData
                required property int index
                width: navigation.width
                height: 36
                text: modelData
                highlighted: navigation.currentIndex === index
                onClicked: navigation.currentIndex = index
                contentItem: Label { text: parent.text; color: parent.highlighted ? dialog.ui.colors.primary : dialog.ui.colors.header.text; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 6; color: parent.highlighted ? dialog.ui.colors.header.badge : parent.hovered ? dialog.ui.colors.header.control_hover : "transparent" }
            }
        }
        StackLayout {
            currentIndex: dialog.kind === 1 ? 2 : navigation.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                spacing: 12
                Label { text: "Color scheme"; font.bold: true }
                Repeater {
                    model: [{text: "System theme", value: "system"}, {text: "Light", value: "light"}, {text: "Dark", value: "dark"}]
                    delegate: RadioButton {
                        required property var modelData
                        text: modelData.text
                        checked: dialog.ui.theme === modelData.value
                        onClicked: dialog.controller.setTheme(modelData.value)
                    }
                }
                Item { Layout.fillHeight: true }
            }
            ColumnLayout {
                spacing: 12
                Label { text: "Initial window size"; font.bold: true }
                CheckBox { id: fitHeight; text: "Fit height to month rows on startup" }
                RowLayout {
                    Label { text: "Width"; Layout.preferredWidth: 60 }
                    AppSpinBox { id: initialWidth; colors: dialog.ui.colors; from: 800; to: 3840; stepSize: 50; Layout.preferredWidth: 110; Accessible.name: "Startup width" }
                    Label { text: "px" }
                }
                RowLayout {
                    Label { text: "Height"; Layout.preferredWidth: 60 }
                    AppSpinBox { id: initialHeight; colors: dialog.ui.colors; from: 500; to: 2160; stepSize: 50; Layout.preferredWidth: 110; enabled: !fitHeight.checked; Accessible.name: "Startup height" }
                    Label { text: "px" }
                }
                Label { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Window sizing applies on the next launch."; color: dialog.ui.colors.header.muted }
                Item { Layout.fillHeight: true }
            }
            ScrollView {
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    spacing: 10
                    Label { text: "Work schedule"; font.bold: true }
                    Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: dialog.ui.closed ? "Reopen this month to change its work schedule." : "Apply this schedule from the selected month onward."
                        color: dialog.ui.colors.header.muted
                    }
                    Repeater {
                        id: dayInputs
                        model: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                        delegate: RowLayout {
                            id: dayRow
                            required property int index
                            required property string modelData
                            property int minutes: hours.value * 60 + minutesInput.value
                            spacing: 6
                            Label { text: dayRow.modelData; Layout.preferredWidth: 95 }
                            AppSpinBox {
                                id: hours
                                colors: dialog.ui.colors
                                from: 0; to: 23
                                value: dialog.schedule.days ? Math.floor(dialog.schedule.days[dayRow.index] / 60) : 0
                                Layout.preferredWidth: 72
                                enabled: !dialog.ui.closed
                                Accessible.name: dayRow.modelData + " planned hours"
                            }
                            Label { text: "h" }
                            AppSpinBox {
                                id: minutesInput
                                colors: dialog.ui.colors
                                from: 0; to: 59
                                value: dialog.schedule.days ? dialog.schedule.days[dayRow.index] % 60 : 0
                                Layout.preferredWidth: 72
                                enabled: !dialog.ui.closed
                                Accessible.name: dayRow.modelData + " planned minutes"
                            }
                            Label { text: "min" }
                        }
                    }
                    RowLayout {
                        spacing: 6
                        Label { text: "Special day"; Layout.preferredWidth: 95 }
                        AppSpinBox { id: specialHours; colors: dialog.ui.colors; from: 0; to: 23; Layout.preferredWidth: 72; enabled: !dialog.ui.closed; Accessible.name: "Special-day planned hours" }
                        Label { text: "h" }
                        AppSpinBox { id: specialMinutes; colors: dialog.ui.colors; from: 0; to: 59; Layout.preferredWidth: 72; enabled: !dialog.ui.closed; Accessible.name: "Special-day planned minutes" }
                        Label { text: "min" }
                    }
                    CheckBox { id: expected; text: "Show an expected end time after the day is started" }
                    Label {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                        text: "The expected time includes the workday duration and recorded interruptions. It is only a visual suggestion and is not saved to the timesheet."
                        color: dialog.ui.colors.header.muted
                    }
                }
            }
        }
    }
}
