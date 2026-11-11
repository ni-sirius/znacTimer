import QtQuick
import QtQuick.Controls

Button {
    id: control
    required property var colors
    required property string message
    readonly property QtObject informationPopup: informationTip
    implicitWidth: 16
    implicitHeight: 16
    padding: 0
    hoverEnabled: true
    Accessible.name: "Information"
    Accessible.description: message
    Accessible.onPressAction: showInfo()
    function showInfo() { informationTip.open() }
    onClicked: showInfo()
    Keys.onReturnPressed: showInfo()
    Keys.onEnterPressed: showInfo()
    contentItem: Text {
        text: "i"
        font.pixelSize: 12; font.bold: true
        color: control.colors.model.overtime_negative
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: width / 2
        color: "transparent"
        border.width: control.activeFocus ? 2 : 1.2
        border.color: control.activeFocus ? control.colors.primary : control.colors.model.overtime_negative
    }
    AppToolTip {
        id: informationTip
        colors: control.colors
        objectName: control.objectName + "Tooltip"
        text: control.message
        hoverRequested: control.hovered
        timeout: 20000
    }
}
