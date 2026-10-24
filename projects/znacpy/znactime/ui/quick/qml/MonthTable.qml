import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models

Surface {
    id: root
    required property var controller
    required property var ui
    dark: ui.dark
    radius: 10
    surfaceColor: colors.table.background
    border.color: colors.table.border
    property var layoutInfo: { let refresh = ui; return controller.tableLayout(table.width, table.height, Screen.devicePixelRatio) }
    colors: ui.colors
    property int selectedRow: 0
    property int selectedColumn: 2
    property int anchorRow: 0
    property int anchorColumn: 2
    property var interruptionTarget: ({action: "add", period_index: null})
    property color ink: colors.model.text
    property color muted: colors.header.muted
    signal editRequested(int row, int column)
    objectName: "monthTableSurface"

    Rectangle { z: -2; x: -6; y: 1; width: parent.width + 12; height: parent.height + 10; radius: 15; color: root.colors.table.shadow; opacity: 0.15 }
    Rectangle { z: -1; x: -3; y: 3; width: parent.width + 6; height: parent.height + 6; radius: 12; color: root.colors.table.shadow; opacity: 0.35 }

    function columnWidth(column) {
        return layoutInfo.widths[column] || 72
    }
    function selectCell(row, column, extend) {
        selectedRow = Math.max(0, Math.min(table.rows - 1, row))
        selectedColumn = Math.max(0, Math.min(6, column))
        if (!extend) {
            anchorRow = selectedRow
            anchorColumn = selectedColumn
        }
        selection.setCurrentIndex(controller.monthModel.index(selectedRow, selectedColumn), ItemSelectionModel.NoUpdate)
        table.positionViewAtCell(Qt.point(selectedColumn, selectedRow), TableView.Contain)
        table.forceActiveFocus()
    }
    function editSelected() {
        if (ui.closed || selectedColumn < 1 || selectedColumn > 4)
            return
        if (selectedColumn === 4) {
            let value = controller.cellValue(selectedRow, 4)
            interruptionTarget = value.indexOf("-") >= 0 ? {action: "edit", period_index: 0}
                                : {action: value === "00:00" || value === "" ? "add" : "replace", period_index: null}
        }
        table.edit(controller.monthModel.index(selectedRow, selectedColumn))
    }
    function editInterruption(row, target) {
        selectCell(row, 4, false)
        interruptionTarget = target || {action: "add", period_index: null}
        table.edit(controller.monthModel.index(row, 4))
    }
    function editDayBadge(row) { selectCell(row, 1, false); editSelected() }
    function showRow(row) {
        selectCell(row, 2, false)
    }

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
            selectionModel: ItemSelectionModel {
                id: selection
                model: root.controller.monthModel
            }
            columnWidthProvider: root.columnWidth
            rowHeightProvider: function(row) {
                return root.layoutInfo.rows[row] ? root.layoutInfo.rows[row].height : 35
            }
            boundsBehavior: Flickable.StopAtBounds
            editTriggers: TableView.EditKeyPressed
            keyNavigationEnabled: false
            activeFocusOnTab: root.selectedColumn !== 4
            ScrollBar.vertical: ScrollBar {
                id: scrollbar
                width: 10
                minimumSize: Math.min(1, 28 / table.height)
                contentItem: Rectangle { implicitWidth: 6; radius: 3; color: scrollbar.hovered ? root.colors.table.scrollbar_hover : root.colors.table.scrollbar_handle }
                background: Rectangle { color: root.colors.table.background }
            }
            ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AlwaysOff }
            onWidthChanged: forceLayout()
            onHeightChanged: forceLayout()
            onRowsChanged: {
                root.selectedRow = Math.min(root.selectedRow, Math.max(0, rows - 1))
                root.anchorRow = Math.min(root.anchorRow, Math.max(0, rows - 1))
            }
            Keys.onPressed: function(event) {
                if (event.matches(StandardKey.Copy)) {
                    root.controller.copyCells(root.anchorRow, root.anchorColumn, root.selectedRow, root.selectedColumn)
                } else if (event.matches(StandardKey.Paste)) {
                    root.controller.pasteCells(root.selectedRow, root.selectedColumn)
                } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && event.modifiers & Qt.ControlModifier && root.selectedColumn === 4) {
                    root.editRequested(root.selectedRow, 4)
                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_F2) {
                    root.editSelected()
                } else if (event.key === Qt.Key_Left) {
                    root.selectCell(root.selectedRow, root.selectedColumn - 1, event.modifiers & Qt.ShiftModifier)
                } else if (event.key === Qt.Key_Tab) {
                    root.selectCell(root.selectedRow + (root.selectedColumn === 6 ? 1 : 0), (root.selectedColumn + 1) % 7, false)
                } else if (event.key === Qt.Key_Backtab) {
                    root.selectCell(root.selectedRow - (root.selectedColumn === 0 ? 1 : 0), (root.selectedColumn + 6) % 7, false)
                } else if (event.key === Qt.Key_Right) {
                    root.selectCell(root.selectedRow, root.selectedColumn + 1, event.modifiers & Qt.ShiftModifier)
                } else if (event.key === Qt.Key_Up) {
                    root.selectCell(root.selectedRow - 1, root.selectedColumn, event.modifiers & Qt.ShiftModifier)
                } else if (event.key === Qt.Key_Down) {
                    root.selectCell(root.selectedRow + 1, root.selectedColumn, event.modifiers & Qt.ShiftModifier)
                } else if (event.key === Qt.Key_Delete || event.key === Qt.Key_Backspace) {
                    root.controller.editCell(root.selectedRow, root.selectedColumn, "")
                } else {
                    return
                }
                event.accepted = true
            }
            delegate: Rectangle {
                id: cell
                required property int row
                required property int column
                required property string display
                required property string editValue
                required property bool editableCell
                required property var cellBadge
                required property string dayState
                required property string dayProblem
                required property string dayWeek
                required property string dayWeekday
                required property bool isToday
                required property string rowStatus
                required property bool editing
                property var rowLayout: root.layoutInfo.rows[row] || ({height: 35, gap: 0, badges: []})
                property real bodyHeight: height - rowLayout.gap
                property bool expected: cellBadge.state === "expected"
                objectName: "monthCell_" + row + "_" + column
                implicitWidth: 100
                implicitHeight: rowLayout.height
                color: root.colors.table.background
                Accessible.role: Accessible.Cell
                Accessible.name: dayWeekday + " " + (column === 0 ? editValue : display)
                Accessible.description: dayProblem

                MouseArea {
                    anchors.fill: parent
                    onClicked: function(mouse) {
                        root.selectCell(cell.row, cell.column, mouse.modifiers & Qt.ShiftModifier)
                        if (!(mouse.modifiers & Qt.ShiftModifier) && cell.editableCell)
                            root.editSelected()
                    }
                }
                Rectangle {
                    id: dateGlow
                    visible: cell.column === 0 && cell.dayState !== ""
                    width: parent.width; height: cell.bodyHeight - 2; y: 1
                    property color accent: cell.dayState === "closed" ? (root.ui.dark ? root.colors.table.texture_closed : Qt.darker(root.colors.table.texture_closed, 3.5))
                                           : cell.dayState === "valid" ? root.colors.model.overtime_positive
                                           : cell.dayState === "invalid" ? root.colors.model.overtime_negative : root.colors.primary
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Qt.rgba(dateGlow.accent.r, dateGlow.accent.g, dateGlow.accent.b, 0.24) }
                        GradientStop { position: 0.35; color: Qt.rgba(dateGlow.accent.r, dateGlow.accent.g, dateGlow.accent.b, 0.14) }
                        GradientStop { position: 0.7; color: Qt.rgba(dateGlow.accent.r, dateGlow.accent.g, dateGlow.accent.b, 0.05) }
                        GradientStop { position: 1; color: "transparent" }
                    }
                }
                Item {
                    visible: cell.column === 0
                    width: parent.width; height: cell.bodyHeight
                    Item {
                        id: dateBlock
                        anchors.left: parent.left; anchors.leftMargin: 10
                        height: parent.height
                        property var dateBounds: dateMetrics.tightBoundingRect(dateText.text)
                        property var weekdayBounds: weekdayMetrics.tightBoundingRect(weekdayText.text)
                        property real textTop: Math.round((height - dateBounds.height - weekdayBounds.height - 1) / 2)
                        FontMetrics { id: dateMetrics; font: dateText.font }
                        FontMetrics { id: weekdayMetrics; font: weekdayText.font }
                        Text {
                            id: dateText
                            y: dateBlock.textTop - dateBlock.dateBounds.y - baselineOffset
                            text: cell.display; color: root.ink
                            font.family: Qt.application.font.family
                            font.pixelSize: root.layoutInfo.dateSize; font.bold: true
                        }
                        Text {
                            id: weekdayText
                            y: dateBlock.textTop + dateBlock.dateBounds.height + 1 - dateBlock.weekdayBounds.y - baselineOffset
                            text: cell.dayWeekday; color: root.ink
                            font.family: Qt.application.font.family
                            font.pixelSize: root.layoutInfo.weekdaySize
                        }
                    }
                    Text { anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; text: cell.dayWeek; color: root.ink; font.pointSize: 10 }
                    Label {
                        visible: cell.dayProblem !== ""
                        anchors.right: parent.right; anchors.rightMargin: 60; anchors.verticalCenter: parent.verticalCenter
                        text: "?"; color: root.colors.model.overtime_negative
                        HoverHandler { id: problemHover }
                        ToolTip.visible: problemHover.hovered
                        ToolTip.text: cell.dayProblem
                    }
                }
                CellBadge {
                    visible: cell.column > 0 && cell.column < 4 && !cell.editing
                    x: (cell.width - width) / 2; y: (cell.bodyHeight - height) / 2
                    width: cell.column === 1 ? cell.width - 10 : Math.max(implicitWidth, root.layoutInfo.timeBadgeWidth)
                    height: root.layoutInfo.badgeHeight
                    colors: root.colors
                    appearance: cell.cellBadge
                    text: cell.cellBadge.texts ? cell.cellBadge.texts[0] : cell.display
                    plain: root.ui.closed
                    outlined: cell.expected
                    interactive: cell.editableCell
                    onClicked: { root.selectCell(cell.row, cell.column, false); root.editSelected() }
                }
                Column {
                    visible: cell.column === 4 && !cell.editing
                    width: cell.width
                    y: (cell.bodyHeight - height) / 2
                    spacing: 4
                    Repeater {
                        model: cell.rowLayout.badges
                        delegate: Row {
                            required property var modelData
                            anchors.horizontalCenter: parent.horizontalCenter
                            spacing: 4
                            Repeater {
                                model: parent.modelData
                                delegate: CellBadge {
                                    required property var modelData
                                    colors: root.colors
                                    appearance: modelData.item
                                    text: modelData.item.text
                                    width: Math.max(implicitWidth, modelData.width)
                                    height: root.layoutInfo.badgeHeight
                                    plain: root.ui.closed
                                    interactive: cell.editableCell
                                    onClicked: root.editInterruption(cell.row, modelData.item.target)
                                }
                            }
                        }
                    }
                }
                Text {
                    visible: cell.column > 4
                    width: parent.width; height: cell.bodyHeight
                    text: cell.display
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.pointSize: 10; font.bold: true
                    color: cell.display.indexOf("-") === 0 ? root.colors.model.overtime_negative
                           : cell.display !== "00:00" && cell.display !== "" ? root.colors.model.overtime_positive : root.colors.model.read_only_text
                }
                Rectangle { y: cell.bodyHeight - 1; width: parent.width; height: 1; color: cell.isToday ? root.colors.primary : root.colors.table.divider }
                Rectangle { visible: cell.isToday; width: parent.width; height: 1; color: root.colors.primary }
                Rectangle { visible: cell.rowLayout.gap > 0; y: cell.bodyHeight; width: parent.width; height: cell.rowLayout.gap; color: root.colors.table.divider }
                TableView.editDelegate: Loader {
                    focus: true
                    x: 5; width: parent.width - 10
                    y: (cell.bodyHeight - height) / 2
                    height: root.layoutInfo.badgeHeight + 2
                    sourceComponent: cell.column === 4 ? periodEditor : lineEditor
                    onLoaded: Qt.callLater(item.focusStart)
                    TableView.onCommit: { if (item) item.save() }
                    Component {
                        id: lineEditor
                        TextField {
                            objectName: cell.column === 1 ? "specialCellEditor" : "timeCellEditor"
                            text: cell.editValue === "--:--" ? "" : cell.editValue
                            selectByMouse: true
                            font.pointSize: 10; font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            color: root.colors.model.editing_text
                            background: Rectangle { radius: 6; color: cell.cellBadge.fillColor || root.colors.table.empty_fill; border.color: root.colors.primary; border.width: 2 }
                            Accessible.name: cell.column === 1 ? "Special day" : cell.column === 2 ? "Start time" : "End time"
                            function focusStart() { forceActiveFocus(); selectAll() }
                            function save() { root.controller.editCell(cell.row, cell.column, text) }
                        }
                    }
                    Component {
                        id: periodEditor
                        InlineInterruptionEditor {
                            colors: root.colors
                            value: cell.editValue
                            target: root.interruptionTarget
                            function save() { root.controller.editCell(cell.row, 4, resolvedValue()) }
                            onFinishRequested: { save(); table.closeEditor() }
                        }
                    }
                }
            }
        }
    }
    Connections {
        target: root.controller
        function onChanged() { Qt.callLater(table.forceLayout) }
    }
}
