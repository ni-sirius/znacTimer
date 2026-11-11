import QtQuick
import QtQuick.Controls

Rectangle {
    id: badge
    required property var colors
    required property var appearance
    property string text: ""
    property bool plain: false
    property bool outlined: false
    property bool interactive: true
    property bool hovered: mouse.containsMouse && interactive && !plain
    property bool fullWidth: false
    property var editSession: null
    signal clicked()
    implicitWidth: Math.max(text === "+" ? 28 : 44, Math.ceil(label.implicitWidth) + 16)
    implicitHeight: metrics.height + 8
    radius: 6
    color: plain ? "transparent" : hovered ? colors.primary : (appearance.fillColor || colors.table.empty_fill)
    border.width: outlined && !plain ? 2 : 0
    border.color: appearance.borderColor || colors.primary
    FontMetrics { id: metrics; font: label.font }
    Text {
        id: label
        visible: badge.text !== "+"
        anchors.fill: parent
        anchors.leftMargin: 8; anchors.rightMargin: 8
        text: badge.text
        font.pointSize: 10
        font.bold: true
        color: badge.hovered ? badge.colors.on_primary : (badge.appearance.textColor || badge.colors.table.empty_text)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    Item {
        objectName: "addInterruptionIcon"
        visible: badge.text === "+"
        x: (badge.width - width) / 2
        y: (badge.height - height) / 2
        width: 10; height: 10
        Rectangle {
            anchors.centerIn: parent
            width: parent.width; height: 2
            color: label.color
        }
        Rectangle {
            anchors.centerIn: parent
            width: 2; height: parent.height
            color: label.color
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: badge.interactive && !badge.plain
        cursorShape: Qt.PointingHandCursor
        property bool dismissOnly: false
        onPressed: dismissOnly = badge.editSession ? badge.editSession.finishActive() : false
        onClicked: { if (!dismissOnly) badge.clicked() }
    }
}
