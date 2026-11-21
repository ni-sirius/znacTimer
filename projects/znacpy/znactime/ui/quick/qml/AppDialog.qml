import QtQuick
import QtQuick.Controls

Dialog {
    id: dialog
    required property Window ownerWindow
    readonly property QtObject dialogWindow: host
    signal nativeCloseRequested()
    signal copyRequested(string text)
    property bool copyMessageEnabled: false
    property string copyMessageText: ""
    property real preferredWidth: implicitWidth
    property real preferredHeight: implicitHeight
    property rect clientArea: Qt.rect(0, 0, 16777215, 16777215)
    readonly property var screenMetrics: [host.screen, host.Screen.devicePixelRatio,
                                          host.Screen.desktopAvailableWidth, host.Screen.desktopAvailableHeight]
    property int defaultStandardButton: standardButtons & Dialog.No ? Dialog.No
                                        : standardButtons & Dialog.Ok ? Dialog.Ok
                                        : standardButtons & Dialog.Save ? Dialog.Save
                                        : standardButtons & Dialog.Close ? Dialog.Close : Dialog.NoButton

    parent: host.contentItem
    popupType: Popup.Item
    x: 0; y: 0
    width: Math.min(preferredWidth, clientArea.width)
    height: Math.min(preferredHeight, clientArea.height)
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape
    font: ownerWindow.font
    palette: ownerWindow.palette
    // The operating system supplies the title bar.
    header: null

    function messageButtons() {
        let buttons = []
        for (const kind of [Dialog.Ok, Dialog.Save, Dialog.Yes, Dialog.No, Dialog.Cancel, Dialog.Close]) {
            const button = standardButton(kind)
            if (button) buttons.push(button)
        }
        return buttons
    }
    function activateDefaultButton() {
        const focused = messageButtons().find(button => button.activeFocus && button.enabled)
        const button = focused || standardButton(defaultStandardButton)
        if (button && button.enabled) button.clicked()
    }
    function fullMessageText() {
        const separator = "---------------------------\n"
        const buttons = messageButtons().map(button => button.text.replace(/&/g, "")).join("   ")
        return separator + title + "\n" + separator + copyMessageText + "\n" + separator + buttons + "\n" + separator
    }

    Item {
        id: keyboardHandler
        parent: host.contentItem
        Keys.onPressed: function(event) {
            if (event.matches(StandardKey.Copy) && dialog.copyMessageEnabled) {
                dialog.copyRequested(dialog.fullMessageText())
                event.accepted = true
            } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && !event.modifiers) {
                dialog.activateDefaultButton()
                event.accepted = true
            } else event.accepted = false
        }
    }

    function layoutHost(centre) {
        clientArea = ownerWindow.controller.dialogClientArea(host)
        const clientWidth = Math.ceil(dialog.width)
        const clientHeight = Math.ceil(dialog.height)
        // Release the old limits before resizing. Updating live fixed-size
        // bindings separately makes Windows reject intermediate geometries.
        if (host.minimumWidth !== clientWidth || host.minimumHeight !== clientHeight) {
            host.minimumWidth = 0
            host.minimumHeight = 0
            host.maximumWidth = 16777215
            host.maximumHeight = 16777215
            host.width = clientWidth
            host.height = clientHeight
            host.minimumWidth = clientWidth
            host.minimumHeight = clientHeight
            host.maximumWidth = clientWidth
            host.maximumHeight = clientHeight
        }
        const x = centre ? ownerWindow.x + (ownerWindow.width - clientWidth) / 2 : host.x
        const y = centre ? ownerWindow.y + (ownerWindow.height - clientHeight) / 2 : host.y
        host.x = Math.round(Math.max(clientArea.x, Math.min(x, clientArea.x + clientArea.width - clientWidth)))
        host.y = Math.round(Math.max(clientArea.y, Math.min(y, clientArea.y + clientArea.height - clientHeight)))
    }
    function updateVisibleHost() {
        if (host.visible) layoutHost(false)
    }
    onWidthChanged: Qt.callLater(updateVisibleHost)
    onHeightChanged: Qt.callLater(updateVisibleHost)
    onScreenMetricsChanged: Qt.callLater(updateVisibleHost)

    onAboutToShow: {
        // Content and footer share this popup item. Focused controls get the
        // first chance to handle a key before it reaches the dialog fallback.
        if (contentItem && contentItem.parent) contentItem.parent.Keys.forwardTo = [keyboardHandler]
        layoutHost(true)
    }

    ApplicationWindow {
        id: host
        objectName: dialog.objectName + "Window"
        transientParent: dialog.ownerWindow
        screen: dialog.ownerWindow.screen
        flags: Qt.Dialog | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint
        // Application modality also keeps macOS dialogs free-standing rather
        // than presenting them as sheets attached to the owner.
        modality: dialog.modal ? Qt.ApplicationModal : Qt.NonModal
        title: dialog.title
        visible: dialog.visible && dialog.ownerWindow.visible
        palette: dialog.palette
        font: dialog.font
        color: palette.window
        onVisibleChanged: {
            if (visible) {
                requestActivate()
                Qt.callLater(dialog.updateVisibleHost)
            }
        }
        onClosing: function(event) {
            // Keep the reusable host alive and route the native X through the
            // same rejection path as Cancel and Escape.
            event.accepted = false
            dialog.nativeCloseRequested()
            if (dialog.closePolicy & Popup.CloseOnEscape)
                dialog.reject()
        }
    }
}
