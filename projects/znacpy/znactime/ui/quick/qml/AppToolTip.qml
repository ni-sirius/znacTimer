import QtQuick
import QtQuick.Controls

ToolTip {
    id: control
    required property var colors
    popupType: Popup.Item
    implicitWidth: Math.min(420, implicitContentWidth + leftPadding + rightPadding)
    leftPadding: 12; rightPadding: 12
    topPadding: 8; bottomPadding: 8
    x: parent ? Math.round((parent.width - width) / 2) : 0
    y: -height - 8
    transformOrigin: Item.Bottom
    contentItem: Text {
        text: control.text
        font: control.font
        color: control.colors.tokens.panel_text
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
    }
    background: Rectangle {
        radius: 10
        color: control.colors.tokens.panel_surface
        border.width: 1
        border.color: control.colors.tokens.panel_border
    }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 140; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: 140; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; to: 0; duration: 90; easing.type: Easing.InCubic }
    }
}
