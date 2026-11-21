import QtQuick
import QtQuick.Controls

Button {
    id: control
    required property var colors
    property string tone: "neutral"
    property bool outlined: false
    property bool dark: false
    property color normalFill: tone === "primary" ? colors.primary
                               : tone === "stop" ? colors.player.stop
                               : tone === "badge" ? colors.header.badge : colors.header.control
    property color ink: !enabled ? colors.player.disabled_text
                        : tone === "primary" ? colors.on_primary
                        : tone === "badge" || outlined ? colors.primary : colors.header.text
    implicitWidth: Math.max(60, implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: 35
    leftPadding: 12
    rightPadding: 12
    topPadding: 6
    bottomPadding: 6
    font.weight: tone === "primary" || tone === "stop" ? Font.Bold : Font.DemiBold
    palette.buttonText: ink
    icon.color: ink
    icon.width: 18
    icon.height: 18
    hoverEnabled: true
    Keys.onReturnPressed: control.clicked()
    Keys.onEnterPressed: control.clicked()
    background: Rectangle {
        radius: control.tone === "primary" || control.tone === "stop" ? 9 : 8
        color: !control.enabled ? control.colors.player.disabled
               : control.down ? (control.tone === "primary"
                   ? (control.dark ? Qt.lighter(control.normalFill, 1.12) : Qt.darker(control.normalFill, 1.12))
                   : control.tone === "stop" ? control.colors.player.stop_hover : control.colors.header.control)
               : control.hovered ? (control.tone === "primary"
                   ? (control.dark ? Qt.lighter(control.normalFill, 1.12) : Qt.darker(control.normalFill, 1.12))
                   : control.tone === "stop" ? control.colors.player.stop_hover : control.colors.header.control_hover)
               : control.normalFill
        border.width: control.activeFocus ? 2 : control.outlined || control.tone === "neutral" ? 1 : 0
        border.color: control.activeFocus && control.tone === "primary" ? control.colors.on_primary
                      : control.outlined || control.activeFocus ? control.colors.primary : control.colors.header.border
    }
}
