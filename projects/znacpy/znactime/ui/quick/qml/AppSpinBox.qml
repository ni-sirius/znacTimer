import QtQuick
import QtQuick.Controls

SpinBox {
    id: control
    required property var colors
    implicitWidth: 79
    implicitHeight: 35
    leftPadding: 9
    rightPadding: 30
    font.weight: Font.DemiBold
    hoverEnabled: true
    editable: true
    contentItem: TextInput {
        text: control.textFromValue(control.value, control.locale)
        font: control.font
        color: control.enabled ? control.colors.header.text : control.colors.palette.text_disabled
        verticalAlignment: Text.AlignVCenter
        readOnly: !control.editable
        selectByMouse: true
        validator: control.validator
        onEditingFinished: {
            let next = control.valueFromText(text, control.locale)
            if (next !== control.value) { control.value = next; control.valueModified() }
        }
    }
    background: Rectangle {
        radius: 8
        color: !control.enabled ? control.colors.palette.base_disabled : control.hovered ? control.colors.header.control_hover : control.colors.header.control
        border.width: control.activeFocus || control.contentItem.activeFocus ? 2 : 1
        border.color: control.activeFocus || control.contentItem.activeFocus || control.hovered ? control.colors.primary : control.colors.header.border
    }
    up.indicator: Rectangle {
        x: control.width - width - 1; y: 1
        width: 24; height: (control.height - 2) / 2
        radius: 7
        color: control.up.pressed ? control.colors.primary : control.up.hovered ? control.colors.header.badge : control.colors.header.control_hover
        Rectangle { width: 7; height: parent.height; color: parent.color }
        Rectangle { anchors.bottom: parent.bottom; height: 7; width: parent.width; color: parent.color }
        Rectangle { width: 1; height: parent.height; color: control.colors.header.border }
        Rectangle { anchors.bottom: parent.bottom; height: 1; width: parent.width; color: control.colors.header.border }
        Chevron { anchors.centerIn: parent; up: true; color: control.up.pressed ? control.colors.on_primary : control.colors.primary }
    }
    down.indicator: Rectangle {
        x: control.width - width - 1; y: control.height / 2
        width: 24; height: (control.height - 2) / 2
        radius: 7
        color: control.down.pressed ? control.colors.primary : control.down.hovered ? control.colors.header.badge : control.colors.header.control_hover
        Rectangle { width: 7; height: parent.height; color: parent.color }
        Rectangle { height: 7; width: parent.width; color: parent.color }
        Rectangle { width: 1; height: parent.height; color: control.colors.header.border }
        Chevron { anchors.centerIn: parent; color: control.down.pressed ? control.colors.on_primary : control.colors.primary }
    }
}
