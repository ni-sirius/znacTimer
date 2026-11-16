import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models
import "month" as MonthParts

Surface {
    id: root
    required property var controller
    required property var ui
    required property var editSession
    dark: ui.dark
    radius: 10
    surfaceColor: colors.table.background
    border.color: colors.table.border
    property var layoutInfo: { let refresh = ui; return controller.tableLayout(table.width, table.height, Screen.devicePixelRatio) }
    colors: ui.colors
    readonly property int selectedRow: selection.currentIndex.valid ? selection.currentIndex.row : 0
    readonly property int selectedColumn: selection.currentIndex.valid ? selection.currentIndex.column : 2
    property int anchorRow: 0
    property int anchorColumn: 2
    property bool changingSelection: false
    property var interruptionTarget: ({action: "add", period_index: null})
    property string initialEditText: ""
    readonly property alias focusItem: table
    readonly property int tabRow: ui.currentMonth ? Math.min(ui.todayRow, table.rows - 1) : 0
    property int navigationPauseIndex: 0
    property var activeEditor: null
    property var focusedBadge: null
    property int focusRequest: 0
    property color ink: colors.model.text
    property color muted: colors.header.muted
    signal editRequested(int row, int column)
    objectName: "monthTableSurface"

    function columnWidth(column) {
        return layoutInfo.widths[column] || 72
    }
    function dividerY(viewportY) {
        const sceneY = table.mapToItem(null, 0, 0).y
        const ratio = Screen.devicePixelRatio
        return Math.round((sceneY + viewportY) * ratio) / ratio - sceneY
    }
    function selectCell(row, column, extend, toggle = false) {
        setCurrentCell(row, column, extend, toggle, true)
    }
    function setCurrentCell(row, column, extend, toggle, takeFocus) {
        row = Math.max(0, Math.min(table.rows - 1, row))
        column = Math.max(0, Math.min(6, column))
        changingSelection = true
        selection.setCurrentIndex(controller.monthModel.index(row, column), ItemSelectionModel.NoUpdate)
        if (!extend) { anchorRow = row; anchorColumn = column }
        controller.selectCells(selection, anchorRow, anchorColumn, row, column, toggle)
        changingSelection = false
        table.positionViewAtCell(Qt.point(selectedColumn, selectedRow), TableView.Contain)
        if (takeFocus) focusTable()
    }
    function focusTable(reverse = false) {
        // A focus scope otherwise restores its previously focused child badge.
        for (let item = focusedBadge; item && item !== table; item = item.parent)
            item.focus = false
        focusedBadge = null
        table.forceActiveFocus(reverse ? Qt.BacktabFocusReason : Qt.TabFocusReason)
    }
    function pauseBadges(row) {
        const cell = table.itemAtCell(Qt.point(4, row))
        return cell ? cell.navigationBadges() : []
    }
    function badgeFocused(badge, row, column, pauseIndex = 0) {
        focusedBadge = badge
        navigationPauseIndex = Math.max(0, pauseIndex)
        setCurrentCell(row, column, false, false, false)
    }
    function focusPosition(row, column, pauseIndex = 0, add = false, reverse = false) {
        setCurrentCell(row, column, false, false, false)
        const request = ++focusRequest
        function applyFocus(retry) {
            if (request !== root.focusRequest) return
            const cell = table.itemAtCell(Qt.point(column, row))
            const badges = cell ? cell.navigationBadges() : []
            const index = add ? badges.length - 1 : Math.min(pauseIndex, badges.length - 1)
            if (column > 0 && column < 5 && index >= 0) {
                root.navigationPauseIndex = index
                badges[index].forceActiveFocus(reverse ? Qt.BacktabFocusReason : Qt.TabFocusReason)
            } else if (column > 0 && column < 5 && retry) {
                Qt.callLater(function() { applyFocus(false) })
            } else root.focusTable(reverse)
        }
        applyFocus(true)
    }
    function enterTab(reverse) {
        if (reverse) focusPosition(tabRow, 4, 0, true, true)
        else focusPosition(tabRow, 0)
    }
    function cancelPendingFocus() { ++focusRequest }
    function navigationPosition() {
        const pauses = pauseBadges(selectedRow)
        let index = navigationPauseIndex
        if (activeEditor && selectedColumn === 4) {
            const edited = pauses.findIndex(badge => badge.editTarget.action === interruptionTarget.action
                && badge.editTarget.period_index === interruptionTarget.period_index)
            if (edited >= 0) index = edited
        }
        return { row: selectedRow, column: selectedColumn, pauseIndex: index,
                 add: selectedColumn === 4 && pauses[index] && pauses[index].text === "+" }
    }
    function advanceEditorField(reverse) {
        return activeEditor && typeof activeEditor.advanceField === "function" && activeEditor.advanceField(reverse)
    }
    function navigateTab(reverse, position) {
        if (position.row !== tabRow) {
            focusPosition(tabRow, 1, 0, false, reverse)
            return true
        }
        const column = position.column
        if (column === 0 && reverse) return false
        if (column === 4) {
            const count = pauseBadges(tabRow).length
            const index = position.pauseIndex + (reverse ? -1 : 1)
            if (index >= 0 && index < count) focusPosition(tabRow, 4, index, false, reverse)
            else if (reverse) focusPosition(tabRow, 3, 0, false, true)
            else return false
        } else if (column > 4) {
            if (reverse) focusPosition(tabRow, 4, 0, true, true)
            else return false
        } else focusPosition(tabRow, column + (reverse ? -1 : 1), 0, false, reverse)
        return true
    }
    function navigateArrow(key, modifiers) {
        const horizontal = key === Qt.Key_Left || key === Qt.Key_Right
        const delta = key === Qt.Key_Left || key === Qt.Key_Up ? -1 : 1
        if (modifiers & Qt.ShiftModifier) {
            selectCell(selectedRow + (horizontal ? 0 : delta), selectedColumn + (horizontal ? delta : 0), true)
            return
        }
        const position = navigationPosition()
        if (!horizontal) {
            const row = Math.max(0, Math.min(table.rows - 1, position.row + delta))
            focusPosition(row, position.column, position.pauseIndex, position.add)
        } else if (position.column === 4) {
            const index = position.pauseIndex + delta
            if (index < 0) focusPosition(position.row, 3)
            else if (index < pauseBadges(position.row).length) focusPosition(position.row, 4, index)
        } else if (position.column > 4) {
            if (delta < 0) focusPosition(position.row, 4, 0, true)
        } else {
            focusPosition(position.row, Math.max(0, position.column + delta))
        }
    }
    function handleTableKey(event) {
        if (activeEditor && [Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down].indexOf(event.key) >= 0) {
            event.accepted = true
            return
        }
        if (event.matches(StandardKey.Copy)) {
            controller.copySelection(selection)
        } else if (event.matches(StandardKey.Paste)) {
            controller.pasteCells(selectedRow, selectedColumn)
        } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && event.modifiers & Qt.ControlModifier && selectedColumn === 4) {
            editRequested(selectedRow, 4)
        } else if (selectedColumn === 0 && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space)) {
            const dateCell = table.itemAtCell(Qt.point(0, selectedRow))
            if (dateCell && dateCell.dateInfo && dateCell.dateInfo.visible) dateCell.dateInfo.showInfo()
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_F2) {
            editSelected()
        } else if ([Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down].indexOf(event.key) >= 0) {
            navigateArrow(event.key, event.modifiers)
        } else if (event.key === Qt.Key_Delete || event.key === Qt.Key_Backspace) {
            controller.editCell(selectedRow, selectedColumn, "")
        } else if (event.text.length > 0 && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))
                   && !ui.closed && selectedColumn >= 1 && selectedColumn <= 4) {
            editSelected(event.text)
        } else {
            event.accepted = false
            return
        }
        event.accepted = true
    }
    function pointerSelect(row, column, modifiers) {
        selectCell(row, column, !!(modifiers & Qt.ShiftModifier), !!(modifiers & Qt.ControlModifier))
    }
    function dragSelect(scenePosition) {
        const point = table.mapFromItem(null, scenePosition.x, scenePosition.y)
        const target = table.cellAtPosition(Qt.point(point.x + table.contentX, point.y + table.contentY), true)
        if (target.x >= 0 && target.y >= 0) selectCell(target.y, target.x, true)
    }
    function editorOpened(editor) { activeEditor = editor }
    function editorClosed(editor) {
        if (activeEditor === editor) activeEditor = null
    }
    function consumeInitialEditText() { initialEditText = "" }
    function editSelected(initialText = "") {
        if (ui.closed || selectedColumn < 1 || selectedColumn > 4)
            return
        if (selectedColumn === 4) {
            let value = controller.cellValue(selectedRow, 4)
            const badges = pauseBadges(selectedRow)
            interruptionTarget = badges[navigationPauseIndex] ? badges[navigationPauseIndex].editTarget
                                : value.indexOf("-") >= 0 ? {action: "edit", period_index: 0}
                                : {action: value === "00:00" || value === "" ? "add" : "replace", period_index: null}
        }
        initialEditText = initialText
        table.edit(controller.monthModel.index(selectedRow, selectedColumn))
    }
    function editInterruption(row, target) {
        selectCell(row, 4, false)
        interruptionTarget = target || {action: "add", period_index: null}
        table.edit(controller.monthModel.index(row, 4))
    }
    function showRow(row) {
        selectCell(row, 2, false)
    }
    function revealToday() {
        if (!ui.currentMonth) return
        table.forceLayout()
        table.positionViewAtCell(Qt.point(0, ui.todayRow), TableView.Contain)
    }
    Component.onCompleted: Qt.callLater(revealToday)

    Rectangle {
        x: 1; y: 1; width: parent.width - 2; height: 36
        radius: 9
        color: root.colors.table.header_background
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 18; color: parent.color }
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 1
        spacing: 0
        HorizontalHeaderView {
            id: header
            syncView: table
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            clip: true
            interactive: false
            delegate: Rectangle {
                required property string display
                implicitWidth: 100
                implicitHeight: 36
                color: "transparent"
                Label {
                    anchors.centerIn: parent
                    text: parent.display
                    color: root.colors.table.header_text
                    font.pointSize: 10
                    font.bold: true
                }
            }
        }
        TableView {
            id: table
            objectName: "monthTable"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.controller.monthModel
            // Row heights include variable week gaps and wrapped interruptions.
            // An estimated extent can leave empty space after the final row.
            contentHeight: root.layoutInfo.rows.reduce((total, row) => total + row.height, 0)
            selectionModel: ItemSelectionModel {
                id: selection
                model: root.controller.monthModel
                onCurrentChanged: function(current, previous) {
                    if (current.valid && !root.changingSelection) {
                        root.anchorRow = current.row
                        root.anchorColumn = current.column
                        selection.select(current, ItemSelectionModel.ClearAndSelect)
                    }
                }
            }
            columnWidthProvider: root.columnWidth
            rowHeightProvider: function(row) {
                return root.layoutInfo.rows[row] ? root.layoutInfo.rows[row].height : 35
            }
            boundsBehavior: Flickable.StopAtBounds
            // Logical pixel alignment alone does not align rules at fractional DPI.
            pixelAligned: true
            editTriggers: TableView.EditKeyPressed | TableView.AnyKeyPressed
            keyNavigationEnabled: false
            activeFocusOnTab: false
            ScrollBar.vertical: ScrollBar {
                id: scrollbar
                objectName: "monthScrollBar"
                z: 2
                width: 10
                minimumSize: Math.min(1, 28 / table.height)
                contentItem: Rectangle { implicitWidth: 6; radius: 3; color: scrollbar.hovered ? root.colors.table.scrollbar_hover : root.colors.table.scrollbar_handle }
                background: Item { }
            }
            ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AlwaysOff }
            Item {
                id: dividerOverlay
                parent: table
                anchors.fill: parent
                z: 1
            }
            onWidthChanged: forceLayout()
            onHeightChanged: forceLayout()
            onRowsChanged: {
                root.anchorRow = Math.min(root.anchorRow, Math.max(0, rows - 1))
            }
            Keys.onPressed: function(event) { root.handleTableKey(event) }
            delegate: MonthParts.CellDelegate {
                tableContext: root
                view: table
                dividerLayer: dividerOverlay
            }
        }
    }
    Connections {
        target: root.controller
        function onChanged() { Qt.callLater(table.forceLayout) }
        function onMonthLoaded() { Qt.callLater(root.revealToday) }
    }
}
