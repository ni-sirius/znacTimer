import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Surface {
    id: root
    required property var controller
    required property var ui
    signal editRequested(int row, int column)
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
            objectName: "todayBadge"
            colors: root.colors
            appearance: root.ui.todayBadge
            text: root.ui.todayBadge.texts ? root.ui.todayBadge.texts[0] : ""
            plain: root.ui.closed
            visible: root.ui.todayBadge.texts !== undefined
            interactive: !root.ui.closed && !root.ui.busy
            Layout.preferredWidth: 170
            Layout.preferredHeight: 33
            onClicked: root.editRequested(root.ui.todayRow, 1)
            ToolTip.visible: hovered
            ToolTip.text: "Today's day badge · Click to edit"
        }
        Item { Layout.preferredWidth: 22 }
        AppButton {
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
