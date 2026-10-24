import QtQuick
import QtQuick.Controls

Dialog {
    id: dialog
    required property Window ownerWindow
    readonly property QtObject dialogWindow: host
    signal nativeCloseRequested()

    parent: host.contentItem
    popupType: Popup.Item
    x: 0; y: 0
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape
    font: ownerWindow.font
    palette: ownerWindow.palette
    // The operating system supplies the title bar.
    header: null

    onAboutToShow: {
        // Position once per opening so moving the dialog or its owner does not
        // snap the dialog back to the centre.
        let screen = ownerWindow.screen
        let centredX = ownerWindow.x + (ownerWindow.width - host.width) / 2
        let centredY = ownerWindow.y + (ownerWindow.height - host.height) / 2
        host.x = Math.round(Math.max(screen.virtualX + 8,
                                    Math.min(centredX, screen.virtualX + screen.width - host.width - 8)))
        host.y = Math.round(Math.max(screen.virtualY + 32,
                                    Math.min(centredY, screen.virtualY + screen.height - host.height - 32)))
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
        width: Math.ceil(dialog.width)
        height: Math.ceil(dialog.height)
        minimumWidth: Math.ceil(dialog.width); maximumWidth: Math.ceil(dialog.width)
        minimumHeight: Math.ceil(dialog.height); maximumHeight: Math.ceil(dialog.height)
        visible: dialog.visible && dialog.ownerWindow.visible
        palette: dialog.palette
        font: dialog.font
        color: palette.window
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
