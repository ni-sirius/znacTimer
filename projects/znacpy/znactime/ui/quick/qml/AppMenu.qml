import QtQuick
import QtQuick.Controls

Menu {
    id: control
    required property var colors
    property bool showMnemonics: false
    padding: 6
    implicitWidth: {
        let widest = 200
        for (let index = 0; index < count; ++index) {
            let item = itemAt(index)
            if (item)
                widest = Math.max(widest, item.implicitWidth + leftPadding + rightPadding)
        }
        return Math.ceil(widest)
    }
    delegate: MenuItem {
        id: item
        implicitHeight: 31
        leftPadding: 12; rightPadding: 28
        contentItem: MenuMnemonicLabel {
            objectName: "menuMnemonicLabel"
            text: item.text
            mnemonicVisible: control.showMnemonics
            font: item.font
            color: !item.enabled ? control.colors.menu.muted : item.highlighted ? control.colors.primary : control.colors.menu.text
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle { radius: 6; color: item.highlighted ? control.colors.menu.surface_hover : "transparent" }
    }
    background: Rectangle { radius: 9; color: control.colors.menu.surface; border.color: control.colors.menu.border }
}
