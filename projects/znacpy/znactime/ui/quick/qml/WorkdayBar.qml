import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Surface {
    id: root
    required property var controller
    required property var ui
    required property var editSession
    readonly property list<Item> tabStops: [todayBadge, primaryButton, stopButton]
    property bool badgeEditing: false
    property var badgeTarget: ({})
    function editDayBadge() {
        if (ui.closed || ui.busy || !ui.todayBadge.texts) return
        badgeTarget = controller.beginCellEdit(ui.todayRow, 1)
        dayEditor.text = controller.cellValue(ui.todayRow, 1)
        badgeEditing = true
        editSession.begin(dayEditor, finishDayBadge)
        dayEditor.forceActiveFocus()
        dayEditor.selectAll()
    }
    function finishDayBadge() {
        if (!badgeEditing) return
        const value = dayEditor.text
        badgeEditing = false
        editSession.end(dayEditor)
        controller.commitCellEdit(badgeTarget, value)
    }
    function cancelDayBadge() {
        badgeEditing = false
        editSession.end(dayEditor)
    }
    onUiChanged: {
        if (badgeEditing && (ui.closed || ui.busy || controller.beginCellEdit(ui.todayRow, 1).date !== badgeTarget.date))
            cancelDayBadge()
    }
    colors: ui.colors
    surfaceColor: colors.player.surface
    border.color: colors.player.border
    objectName: "workdayBar"
    implicitHeight: 53
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14; anchors.rightMargin: 14
        anchors.topMargin: 10; anchors.bottomMargin: 10
        spacing: 10
        Label {
            objectName: "workdayStatus"
            text: root.ui.workStatusText
            color: root.colors.player.muted
            font.weight: Font.DemiBold
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
        CellBadge {
            id: todayBadge
            objectName: "todayBadge"
            editSession: root.editSession
            colors: root.colors
            appearance: root.ui.todayBadge
            text: root.ui.todayBadge.texts ? root.ui.todayBadge.texts[0] : ""
            plain: root.ui.closed
            visible: root.ui.todayBadge.texts !== undefined
            interactive: !root.ui.closed && !root.ui.busy
            editing: root.badgeEditing
            Accessible.name: "Today's day badge"
            Layout.preferredWidth: 170
            Layout.preferredHeight: 33
            onClicked: root.editDayBadge()
            tooltipText: "Today's day badge · Click to edit"
            ClockTextField {
                id: dayEditor
                objectName: "todayBadgeEditor"
                visible: root.badgeEditing
                anchors.fill: parent
                timeOnly: false
                selectByMouse: true
                font.pointSize: 10; font.bold: true
                horizontalAlignment: Text.AlignHCenter
                color: root.colors.model.editing_text
                background: Rectangle {
                    radius: 6
                    color: root.ui.todayBadge.fillColor || root.colors.table.empty_fill
                    border.color: root.colors.primary; border.width: 2
                }
                Accessible.name: "Today's special day"
                onAccepted: { root.finishDayBadge(); todayBadge.forceActiveFocus() }
                Keys.onEscapePressed: { root.cancelDayBadge(); todayBadge.forceActiveFocus() }
                onActiveFocusChanged: { if (!activeFocus && root.badgeEditing) root.finishDayBadge() }
            }
        }
        Item { Layout.preferredWidth: 22 }
        AppButton {
            id: primaryButton
            objectName: "primaryWorkdayButton"
            colors: root.colors
            dark: root.ui.dark
            tone: "primary"
            text: root.ui.workState === "paused" ? "Resume" : root.ui.workState === "working" ? "Pause" : "Start day"
            Layout.preferredWidth: 128
            Layout.preferredHeight: 33
            enabled: !root.ui.busy && ["idle", "working", "paused"].indexOf(root.ui.workState) >= 0
            onClicked: root.controller.primaryAction()
        }
        AppButton {
            id: stopButton
            objectName: "stopWorkdayButton"
            colors: root.colors
            tone: "stop"
            text: "Stop day"
            Layout.preferredWidth: 128
            Layout.preferredHeight: 33
            enabled: !root.ui.busy && ["working", "paused"].indexOf(root.ui.workState) >= 0
            onClicked: root.controller.stopWorkday()
        }
    }
}
