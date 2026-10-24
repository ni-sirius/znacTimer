import QtQuick
import QtQuick.Controls

TextField {
    id: control
    required property var colors
    implicitHeight: 31
    leftPadding: 8; rightPadding: 8
    selectByMouse: true
    color: enabled ? colors.header.text : colors.palette.text_disabled
    placeholderTextColor: colors.header.muted
    selectionColor: colors.primary
    selectedTextColor: colors.on_primary
    background: Rectangle {
        radius: 6
        color: control.enabled ? control.colors.header.control : control.colors.palette.base_disabled
        border.color: control.activeFocus ? control.colors.primary : control.colors.header.border
        border.width: control.activeFocus ? 2 : 1
    }
}
