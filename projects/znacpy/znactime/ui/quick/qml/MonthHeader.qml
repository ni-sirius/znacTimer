import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Surface {
    id: root
    required property var controller
    required property var ui
    readonly property list<Item> tabStops: [yearSelector, monthSelector, todayButton, monthAction]
    readonly property bool popupVisible: monthSelector.popup.visible
    colors: ui.colors
    objectName: "monthHeader"
    implicitHeight: 69
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16; anchors.rightMargin: 16
        anchors.topMargin: 8; anchors.bottomMargin: 8
        spacing: 8
        ColumnLayout {
            id: period
            Layout.preferredWidth: 255
            Layout.minimumWidth: 200
            Layout.maximumWidth: Layout.preferredWidth
            Layout.alignment: Qt.AlignTop
            spacing: 3
            RowLayout {
                spacing: 6
                AppSpinBox {
                    id: yearSelector
                    objectName: "yearSelector"
                    colors: root.colors
                    from: 2000; to: 2100; value: root.ui.year
                    Layout.preferredWidth: 79
                    Layout.preferredHeight: 35
                    enabled: !root.ui.busy
                    textFromValue: function(value) { return value.toString() }
                    valueFromText: function(text) { return parseInt(text, 10) || root.ui.year }
                    Accessible.name: "Year"
                    onValueModified: root.controller.selectMonth(value, root.ui.month)
                }
                AppComboBox {
                    id: monthSelector
                    objectName: "monthSelector"
                    colors: root.colors
                    Layout.fillWidth: true
                    Layout.preferredHeight: 35
                    model: root.ui.months
                    currentIndex: root.ui.month - 1
                    enabled: !root.ui.busy
                    Accessible.name: "Month"
                    onActivated: root.controller.selectMonth(root.ui.year, currentIndex + 1)
                }
            }
            RowLayout {
                spacing: 0
                Layout.fillWidth: true
                Repeater {
                    model: root.ui.calendarWeek.split(", ")
                    delegate: Label {
                        required property string modelData
                        Layout.fillWidth: true
                        text: modelData
                        font.pixelSize: 11
                        color: root.colors.header.muted
                        elide: Text.ElideRight
                    }
                }
            }
        }
        AppButton {
            id: todayButton
            objectName: "todayButton"
            colors: root.colors
            tone: "badge"
            text: "Today"
            Layout.preferredWidth: 60
            Layout.preferredHeight: 35
            Layout.alignment: Qt.AlignTop
            enabled: !root.ui.busy
            onClicked: root.controller.showToday()
        }
        Item { Layout.fillWidth: true }
        Rectangle {
            id: carry
            objectName: "carryOverBadge"
            radius: 8
            color: root.colors.header.badge
            Layout.preferredWidth: carryContents.implicitWidth + 20
            Layout.minimumWidth: Layout.preferredWidth
            Layout.fillHeight: true
            RowLayout {
                id: carryContents
                anchors.fill: parent; anchors.margins: 10; spacing: 6
                Label {
                    id: carryText
                    objectName: "carryOverText"
                    text: root.ui.previousUnclosed ? "Last month is not closed" : "Last Month: " + root.ui.carry
                    color: root.ui.previousUnclosed ? root.colors.model.overtime_negative : root.colors.primary
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                InfoButton {
                    id: carryInfo
                    objectName: "carryOverInfo"
                    visible: root.ui.previousUnclosed
                    colors: root.colors
                    message: "Close last month to carry its time balance over to this month."
                    Accessible.name: "Why last month must be closed"
                    Layout.preferredWidth: 20; Layout.preferredHeight: 20
                }
            }
            HoverHandler { id: carryHover }
            AppToolTip {
                colors: root.colors
                hoverRequested: carryHover.hovered && root.ui.previousUnclosed && !carryInfo.hovered
                text: "Close last month to carry its time balance over to this month."
            }
        }
        AppButton {
            id: monthAction
            objectName: "monthActionButton"
            colors: root.colors
            tone: "badge"
            outlined: true
            text: "This Month: " + root.ui.balance
            Layout.preferredWidth: monthValue.implicitWidth + 50 + (root.ui.carryDiscontinuity ? warning.implicitWidth + 6 : 0)
            Layout.fillHeight: true
            enabled: !root.ui.busy
            contentItem: RowLayout {
                spacing: 6
                Label { id: monthValue; text: monthAction.text; color: root.colors.primary; font.weight: Font.DemiBold }
                LockIcon { closed: root.ui.closed; color: closed ? root.colors.tokens.danger_text : root.colors.primary }
                Label { id: warning; visible: root.ui.carryDiscontinuity; text: root.width < 1100 ? "!" : "carry-over discontinuity"; color: root.colors.tokens.danger_text }
            }
            onClicked: root.ui.closed ? root.controller.reopenMonth() : root.controller.closeMonth()
            AppToolTip {
                colors: root.colors
                hoverRequested: monthAction.hovered
                text: root.ui.carryDiscontinuity ? "The previous closing balance changed. This closed month's opening balance is preserved."
                                               : root.ui.closed ? "This month is closed. Click to reopen it for corrections." : "This month is open. Click to review and close it."
            }
        }
    }
}
