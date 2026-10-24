import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs as FileDialogs
import QtCore

ApplicationWindow {
    id: window
    required property var controller
    property var ui: controller.state
    objectName: "mainWindow"
    title: ui.title
    width: 1250
    height: 900
    minimumWidth: 800
    minimumHeight: 500
    visible: false
    color: ui.colors.shell.background
    palette.window: ui.colors.palette.window
    palette.windowText: ui.colors.palette.window_text
    palette.base: ui.colors.palette.base
    palette.text: ui.colors.palette.text
    palette.button: ui.colors.palette.button
    palette.buttonText: ui.colors.palette.button_text
    palette.highlight: ui.colors.primary
    palette.highlightedText: ui.colors.on_primary
    font.pointSize: 10
    Component.onCompleted: {
        width = ui.initialWidth
        height = ui.initialHeight
    }

    onClosing: function(event) {
        if (ui.busy) {
            event.accepted = false
            controller.cancelTask()
        }
    }
    function openExport(kind) {
        exportDialog.kind = kind
        exportDialog.title = kind === "backup" ? "Back up database" : "Export month " + kind.toUpperCase()
        exportDialog.nameFilters = kind === "csv" ? ["CSV files (*.csv)"]
                                   : kind === "pdf" ? ["PDF files (*.pdf)"] : ["SQLite databases (*.db)"]
        exportDialog.defaultSuffix = kind === "backup" ? "db" : kind
        exportDialog.selectedFile = StandardPaths.writableLocation(StandardPaths.DocumentsLocation)
                                    + "/" + controller.suggestedFile(kind)
        exportDialog.open()
    }

    menuBar: MenuBar {
        implicitHeight: 40
        spacing: 4
        leftPadding: 10; rightPadding: 10
        topPadding: 5; bottomPadding: 5
        background: Rectangle {
            color: window.ui.colors.menu.surface
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: window.ui.colors.menu.border }
        }
        delegate: MenuBarItem {
            id: menuItem
            topPadding: 6; bottomPadding: 6; leftPadding: 12; rightPadding: 12
            contentItem: Text { text: menuItem.text.replace(/&/g, ""); font: menuItem.font; color: menuItem.highlighted ? window.ui.colors.primary : window.ui.colors.menu.text; verticalAlignment: Text.AlignVCenter }
            background: Rectangle { radius: 7; color: menuItem.highlighted ? window.ui.colors.menu.surface_hover : "transparent" }
        }
        AppMenu {
            colors: window.ui.colors
            title: "&Data"
            enabled: !window.ui.busy
            Action { text: "Import CSV Data…"; onTriggered: importDialog.open() }
            MenuSeparator { }
            Action { text: "Export Month CSV"; onTriggered: window.openExport("csv") }
            Action { text: "Export PDF"; onTriggered: window.openExport("pdf") }
            Action { text: "Back Up Database"; onTriggered: window.openExport("backup") }
            MenuSeparator { }
            Action { text: "Exit"; shortcut: StandardKey.Quit; onTriggered: window.close() }
        }
        AppMenu {
            colors: window.ui.colors
            title: "&Approvals"
            enabled: !window.ui.busy
            Action { text: "Close Month"; enabled: !window.ui.closed; onTriggered: window.controller.closeMonth() }
            Action { text: "Reopen Month"; enabled: window.ui.closed; onTriggered: window.controller.reopenMonth() }
        }
        AppMenu {
            colors: window.ui.colors
            title: "&Settings"
            enabled: !window.ui.busy
            Action { text: "Appearance"; onTriggered: settingsDialog.showSection(0) }
            Action { text: "Work schedule"; onTriggered: settingsDialog.showSection(1) }
        }
        AppMenu {
            colors: window.ui.colors
            title: "&Help"
            Action { text: "About znacTime"; onTriggered: aboutDialog.open() }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 16; anchors.rightMargin: 16
        anchors.topMargin: 14; anchors.bottomMargin: 16
        spacing: 10
        MonthHeader {
            controller: window.controller
            ui: window.ui
            Layout.fillWidth: true
            Layout.preferredHeight: 69
        }
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            MonthTable {
                id: monthTable
                anchors.fill: parent
                anchors.topMargin: 6; anchors.bottomMargin: 12
                controller: window.controller
                ui: window.ui
                enabled: !window.ui.busy
                onEditRequested: function(row, column) { cellEditor.edit(row, column) }
            }
        }
        WorkdayBar {
            controller: window.controller
            ui: window.ui
            Layout.fillWidth: true
            Layout.preferredHeight: 53
            onEditRequested: function(row, column) { monthTable.editDayBadge(row) }
        }
    }

    SettingsDialog { id: settingsDialog; controller: window.controller; ui: window.ui; ownerWindow: window }
    InterruptionEditor { id: cellEditor; controller: window.controller; ownerWindow: window }

    AppDialog {
        id: notificationDialog
        objectName: "notificationDialog"
        ownerWindow: window
        property var messages: []
        property string message: ""
        width: Math.min(590, window.width - 32)
        modal: true
        standardButtons: Dialog.Ok
        footer: DialogButtonBox {
            standardButtons: Dialog.Ok
            delegate: AppButton { colors: window.ui.colors }
        }
        function next() {
            if (messages.length === 0) return
            let nextMessage = messages[0]
            messages = messages.slice(1)
            title = nextMessage.title
            message = nextMessage.text
            open()
        }
        onClosed: Qt.callLater(next)
        contentItem: ScrollView {
            id: noticeScroll
            implicitHeight: Math.min(noticeText.implicitHeight, window.height - 180)
            contentWidth: availableWidth
            Label { id: noticeText; width: noticeScroll.availableWidth; text: notificationDialog.message; wrapMode: Text.WordWrap; textFormat: Text.PlainText }
        }
    }
    AppDialog {
        id: confirmationDialog
        objectName: "confirmationDialog"
        ownerWindow: window
        property int token: -1
        property string message: ""
        width: Math.min(610, window.width - 32)
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        footer: DialogButtonBox {
            standardButtons: Dialog.Yes | Dialog.No
            delegate: AppButton { colors: window.ui.colors }
        }
        onAccepted: window.controller.answerConfirmation(token, true)
        onRejected: window.controller.answerConfirmation(token, false)
        onOpened: standardButton(Dialog.No).forceActiveFocus()
        contentItem: ScrollView {
            id: confirmScroll
            implicitHeight: Math.min(confirmText.implicitHeight, window.height - 180)
            contentWidth: availableWidth
            Label { id: confirmText; width: confirmScroll.availableWidth; text: confirmationDialog.message; wrapMode: Text.WordWrap; textFormat: Text.PlainText }
        }
    }
    AppDialog {
        id: taskDialog
        objectName: "taskProgressDialog"
        ownerWindow: window
        width: Math.min(500, window.width - 32)
        title: window.ui.progress.title
        modal: true
        closePolicy: Popup.NoAutoClose
        onNativeCloseRequested: window.controller.cancelTask()
        contentItem: ColumnLayout {
            Label { text: window.ui.progress.phase; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            ProgressBar {
                Layout.fillWidth: true
                indeterminate: window.ui.progress.total <= 0
                from: 0; to: Math.max(1, window.ui.progress.total)
                value: window.ui.progress.completed
            }
            AppButton { colors: window.ui.colors; text: "Cancel"; Layout.alignment: Qt.AlignRight; enabled: window.ui.progress.phase !== "Cancelling…"; onClicked: window.controller.cancelTask() }
        }
    }
    AppDialog {
        id: aboutDialog
        objectName: "aboutDialog"
        ownerWindow: window
        title: "About znacTime"
        width: Math.min(430, window.width - 32)
        modal: true
        standardButtons: Dialog.Ok
        footer: DialogButtonBox {
            standardButtons: Dialog.Ok
            delegate: AppButton { colors: window.ui.colors }
        }
        contentItem: ColumnLayout {
            spacing: 12
            Image { source: "../../qt/assets/app_icon.png"; Layout.preferredWidth: 72; Layout.preferredHeight: 72; Layout.alignment: Qt.AlignHCenter; fillMode: Image.PreserveAspectFit }
            Label { text: "znacTime " + window.ui.version; font.pixelSize: 22; Layout.alignment: Qt.AlignHCenter }
            Label { text: "Track workdays, interruptions, and overtime.\n\nLicense: MIT\nBuilt with PySide6 / Qt Quick — LGPL v3"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { text: '<a href="https://znac.org">znac.org</a> · <a href="mailto:znacompany@gmail.com">Contact</a>'; onLinkActivated: function(link) { Qt.openUrlExternally(link) } }
        }
    }
    FileDialogs.FileDialog {
        id: exportDialog
        property string kind: "csv"
        fileMode: FileDialogs.FileDialog.SaveFile
        onAccepted: window.controller.exportFile(kind, selectedFile)
    }
    FileDialogs.FolderDialog {
        id: importDialog
        title: "Select legacy CSV data folder"
        onAccepted: window.controller.importFolder(selectedFolder)
    }
    Connections {
        target: window.controller
        function onNotification(title, text) {
            notificationDialog.messages = notificationDialog.messages.concat([{title: title, text: text}])
            if (!notificationDialog.visible) notificationDialog.next()
        }
        function onConfirmation(title, text, token) {
            confirmationDialog.title = title
            confirmationDialog.message = text
            confirmationDialog.token = token
            // A confirmation may lead to another confirmation. Let the old
            // popup finish closing before opening the next one.
            Qt.callLater(confirmationDialog.open)
        }
        function onScrollToToday(row) { monthTable.showRow(row) }
        function onChanged() {
            if (window.controller.state.busy) taskDialog.open()
            else taskDialog.close()
        }
    }
}
