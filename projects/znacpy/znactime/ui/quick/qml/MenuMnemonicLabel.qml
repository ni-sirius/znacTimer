import QtQuick

Item {
    id: control
    property string text: ""
    property bool mnemonicVisible: false
    property alias font: label.font
    property alias color: label.color
    property alias verticalAlignment: label.verticalAlignment
    implicitWidth: label.implicitWidth
    implicitHeight: label.implicitHeight
    baselineOffset: label.baselineOffset

    readonly property var caption: {
        let plain = ""
        let mnemonic = -1
        for (let index = 0; index < text.length; ++index) {
            if (text[index] !== "&") {
                plain += text[index]
            } else if (text[index + 1] === "&") {
                plain += "&"
                ++index
            } else if (index + 1 < text.length && mnemonic < 0) {
                mnemonic = plain.length
            }
        }
        return { text: plain, mnemonic: mnemonic }
    }
    property point sceneOrigin: Qt.point(0, 0)
    function updateSceneOrigin() {
        if (visible) sceneOrigin = mapToItem(null, 0, 0)
    }
    // Menu popup placement finishes after its delegates have been laid out.
    onVisibleChanged: Qt.callLater(updateSceneOrigin)
    onXChanged: Qt.callLater(updateSceneOrigin)
    onYChanged: Qt.callLater(updateSceneOrigin)
    onWidthChanged: Qt.callLater(updateSceneOrigin)
    onHeightChanged: Qt.callLater(updateSceneOrigin)
    Component.onCompleted: Qt.callLater(updateSceneOrigin)

    Text {
        id: label
        objectName: "menuMnemonicText"
        anchors.fill: parent
        text: control.caption.text
        textFormat: Text.PlainText
        renderType: Text.NativeRendering
    }
    FontMetrics { id: metrics; font: label.font }
    TextMetrics {
        id: prefix
        font: label.font
        renderType: label.renderType
        text: control.caption.text.slice(0, Math.max(0, control.caption.mnemonic))
    }
    TextMetrics {
        id: throughMnemonic
        font: label.font
        renderType: label.renderType
        text: control.caption.text.slice(0, control.caption.mnemonic + 1)
    }
    Item {
        readonly property real ratio: Screen.devicePixelRatio
        readonly property real start: Math.round((control.sceneOrigin.x + prefix.advanceWidth) * ratio)
        readonly property real end: Math.round((control.sceneOrigin.x + throughMnemonic.advanceWidth) * ratio)
        visible: control.mnemonicVisible && control.caption.mnemonic >= 0
        x: start / ratio - control.sceneOrigin.x
        y: Math.round((control.sceneOrigin.y + label.baselineOffset + metrics.underlinePosition) * ratio) / ratio - control.sceneOrigin.y
        // Integer local dimensions avoid fractional coverage in the software renderer.
        width: Math.max(1, end - start)
        height: Math.max(1, Math.round(Math.max(1, metrics.lineWidth) * ratio))
        scale: 1 / ratio
        transformOrigin: Item.TopLeft
        Rectangle {
            objectName: "menuMnemonicUnderline"
            anchors.fill: parent
            color: control.color
            antialiasing: false
        }
    }
}
