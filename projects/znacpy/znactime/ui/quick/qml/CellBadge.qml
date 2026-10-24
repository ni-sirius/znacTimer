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
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: badge.interactive && !badge.plain
        cursorShape: Qt.PointingHandCursor
        onClicked: badge.clicked()
    }
}
