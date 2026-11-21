import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs as FileDialogs
import QtCore

ApplicationWindow {
    id: window
    required property var controller
    required property var menuAccessKeys
    required property var focusNavigation
    readonly property bool focusNavigationEnabled: !ui.busy && !menuNavigationActive
        && !monthHeader.popupVisible && !settingsDialog.visible && !cellEditor.visible
        && !notificationDialog.visible && !confirmationDialog.visible && !taskDialog.visible && !aboutDialog.visible
    property bool menuNavigationActive: mainMenuBar.activeFocus || dataMenu.visible
                                       || approvalsMenu.visible || settingsMenu.visible || helpMenu.visible
    onMenuNavigationActiveChanged: menuAccessKeys.updateNavigation(menuNavigationActive)
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
    function containsFocus(item, focused) {
        for (let current = focused; current; current = current.parent) {
            if (current === item) return true
        }
        return false
    }
    function navigateFocus(reverse) {
        const focused = activeFocusItem
        const inTable = containsFocus(monthTable, focused)
        if (inTable && monthTable.advanceEditorField(reverse)) return
        const position = inTable ? monthTable.navigationPosition() : null
        badgeEditSession.finishActive()
        if (!focusNavigationEnabled) return
        if (inTable && monthTable.navigateTab(reverse, position)) return

        const header = monthHeader.tabStops.filter(item => item.visible && item.enabled)
        const footer = workdayBar.tabStops.filter(item => item.visible && item.enabled
            && (item !== workdayBar.tabStops[0] || item.interactive))
        let target = null
        if (inTable) {
            target = reverse ? header[header.length - 1] : footer[0]
            if (!target) target = reverse ? footer[footer.length - 1] : header[0]
        } else {
            const stops = header.concat([monthTable.focusItem], footer)
            const current = stops.findIndex(item => containsFocus(item, focused))
            const next = current < 0 ? (reverse ? stops.length - 1 : 0)
                : (current + (reverse ? -1 : 1) + stops.length) % stops.length
            target = stops[next]
        }
        if (target === monthTable.focusItem) monthTable.enterTab(reverse)
        else if (target) {
            monthTable.cancelPendingFocus()
            target.forceActiveFocus(reverse ? Qt.BacktabFocusReason : Qt.TabFocusReason)
        }
    }
    Connections {
        target: window.focusNavigation
        function onTabPressed(reverse) { window.navigateFocus(reverse) }
    }
    QtObject {
        id: badgeEditSession
        property var owner: null
        property var commit: null
        function begin(editor, save) { owner = editor; commit = save }
        function end(editor) { if (owner === editor) { owner = null; commit = null } }
        function finishActive() {
            if (!owner) return false
            let save = commit
            owner = null
            commit = null
            save()
            return true
        }
    }
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
        id: mainMenuBar
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
            contentItem: MenuMnemonicLabel {
                objectName: "menuMnemonicLabel"
                text: menuItem.text
                mnemonicVisible: window.menuAccessKeys.visible
                font: menuItem.font
                color: menuItem.highlighted ? window.ui.colors.primary : window.ui.colors.menu.text
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle { radius: 7; color: menuItem.highlighted ? window.ui.colors.menu.surface_hover : "transparent" }
        }
        AppMenu {
            id: dataMenu
            showMnemonics: window.menuAccessKeys.visible
            colors: window.ui.colors
            title: "&Data"
            enabled: !window.ui.busy
            Action { text: "&Import CSV Data…"; onTriggered: importDialog.open() }
            MenuSeparator { }
            Action { text: "Export Month &CSV"; onTriggered: window.openExport("csv") }
            Action { text: "Export &PDF"; onTriggered: window.openExport("pdf") }
            Action { text: "&Back Up Database"; onTriggered: window.openExport("backup") }
            MenuSeparator { }
            Action { id: quitAction; text: "E&xit"; shortcut: window.controller.quitShortcuts[0]; onTriggered: window.close() }
        }
        AppMenu {
            id: approvalsMenu
            showMnemonics: window.menuAccessKeys.visible
            colors: window.ui.colors
            title: "&Approvals"
            enabled: !window.ui.busy
            Action { text: "&Close Month"; enabled: !window.ui.closed; onTriggered: window.controller.closeMonth() }
            Action { text: "&Reopen Month"; enabled: window.ui.closed; onTriggered: window.controller.reopenMonth() }
        }
        AppMenu {
            id: settingsMenu
            showMnemonics: window.menuAccessKeys.visible
            colors: window.ui.colors
            title: "&Settings"
            enabled: !window.ui.busy
            Action { text: "&Appearance"; onTriggered: settingsDialog.showSection(0) }
            Action { text: "&Work schedule"; onTriggered: settingsDialog.showSection(1) }
        }
        AppMenu {
            id: helpMenu
            showMnemonics: window.menuAccessKeys.visible
            colors: window.ui.colors
            title: "&Help"
            Action { text: "&About znacTime"; onTriggered: aboutDialog.open() }
        }
    }

    Shortcut {
        sequences: window.controller.quitShortcuts.slice(1)
        onActivated: quitAction.trigger()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 16; anchors.rightMargin: 16
        anchors.topMargin: 14; anchors.bottomMargin: 16
        spacing: 10
        MonthHeader {
            id: monthHeader
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
                editSession: badgeEditSession
                enabled: !window.ui.busy
                onEditRequested: function(row, column) { cellEditor.edit(row, column) }
            }
        }
        WorkdayBar {
            id: workdayBar
            controller: window.controller
            ui: window.ui
            editSession: badgeEditSession
            Layout.fillWidth: true
            Layout.preferredHeight: 53
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
        copyMessageEnabled: true
        copyMessageText: message
        onCopyRequested: function(text) { window.controller.copyText(text) }
        preferredWidth: Math.min(590, window.width - 32)
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
        onOpened: standardButton(Dialog.Ok).forceActiveFocus()
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
        copyMessageEnabled: true
        copyMessageText: message
        onCopyRequested: function(text) { window.controller.copyText(text) }
        preferredWidth: Math.min(610, window.width - 32)
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
        preferredWidth: Math.min(500, window.width - 32)
        title: window.controller.progress.title
        modal: true
        closePolicy: Popup.NoAutoClose
        onNativeCloseRequested: window.controller.cancelTask()
        contentItem: ColumnLayout {
            Label { text: window.controller.progress.phase; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            ProgressBar {
                Layout.fillWidth: true
                indeterminate: window.controller.progress.total <= 0
                from: 0; to: Math.max(1, window.controller.progress.total)
                value: window.controller.progress.completed
            }
            AppButton { colors: window.ui.colors; text: "Cancel"; Layout.alignment: Qt.AlignRight; enabled: window.controller.progress.phase !== "Cancelling…"; onClicked: window.controller.cancelTask() }
        }
    }
    AppDialog {
        id: aboutDialog
        objectName: "aboutDialog"
        ownerWindow: window
        title: "About znacTime"
        copyMessageEnabled: true
        copyMessageText: "znacTime " + window.ui.version + "\n\nTrack workdays, interruptions, and overtime.\n\nLicense: MIT\nBuilt with PySide6 / Qt Quick — LGPL v3\n\nznac.org\nznacompany@gmail.com"
        onCopyRequested: function(text) { window.controller.copyText(text) }
        onOpened: standardButton(Dialog.Ok).forceActiveFocus()
        preferredWidth: Math.min(430, window.width - 32)
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
