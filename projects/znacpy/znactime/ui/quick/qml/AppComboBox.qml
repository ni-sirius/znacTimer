import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    required property var colors
    implicitHeight: 35
    implicitWidth: 170
    leftPadding: 8
    rightPadding: 36
    font.weight: Font.DemiBold
    hoverEnabled: true
    contentItem: TextField {
        text: control.editable ? control.editText : control.displayText
        readOnly: !control.editable
        enabled: control.editable
        selectByMouse: control.editable
        color: control.enabled ? control.colors.header.text : control.colors.palette.text_disabled
        font: control.font
        verticalAlignment: Text.AlignVCenter
        padding: 0
        background: null
        onTextEdited: control.editText = text
    }
    background: Rectangle {
        radius: 8
        color: !control.enabled ? control.colors.palette.base_disabled : control.hovered ? control.colors.header.control_hover : control.colors.header.control
        border.color: control.activeFocus || control.hovered ? control.colors.primary : control.colors.header.border
    }
    indicator: Rectangle {
        x: control.width - width - 1
        y: 1
        width: 28
        height: control.height - 2
        radius: 7
        color: control.pressed ? control.colors.primary : control.colors.header.control_hover
        Rectangle { width: 7; height: parent.height; color: parent.color }
        Rectangle { width: 1; height: parent.height; color: control.colors.header.border }
        Chevron { anchors.centerIn: parent; color: control.pressed ? control.colors.on_primary : control.colors.primary }
    }
    delegate: ItemDelegate {
        required property int index
        required property var modelData
        width: control.width
        height: 30
        highlighted: control.highlightedIndex === index
        contentItem: Text { text: parent.modelData; font: control.font; color: parent.highlighted ? control.colors.primary : control.colors.header.text; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { radius: 5; color: parent.highlighted ? control.colors.header.badge : "transparent" }
    }
    popup: Popup {
        y: control.height + 3
        width: control.width
        implicitHeight: Math.min(contentItem.implicitHeight + 8,
                                 Math.max(160, (control.ApplicationWindow.window ? control.ApplicationWindow.window.height : 600) - control.height - 120))
        padding: 4
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator { }
        }
        background: Rectangle { color: control.colors.header.surface; border.color: control.colors.header.border; radius: 8 }
    }
}
