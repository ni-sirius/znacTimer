import QtQuick
import ".."

Rectangle {
    id: cell
    // Read the view-owned layout/palette through its QObject. Forwarding these
    // large QVariant maps into each pooled cell duplicates data and work.
    required property QtObject tableContext
    required property TableView view
    required property Item dividerLayer
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
    property var rowLayout: cell.tableContext.layoutInfo.rows[row] || ({height: 35, gap: 0, badges: []})
    property real bodyHeight: height - rowLayout.gap
    property real dividerBottom: column === 0 ? cell.tableContext.dividerY(cell.y - cell.view.contentY + cell.height) : 0
    property real dividerGap: Math.round(rowLayout.gap * Screen.devicePixelRatio) / Screen.devicePixelRatio
    property bool expected: cellBadge.state === "expected"
    property bool pooled: false
    property var dateInfo: dateLoader.item ? dateLoader.item.infoButton : null
    function navigationBadges() {
        if (column > 0 && column < 4) return cell.editing || !mainBadgeLoader.item ? [] : [mainBadgeLoader.item]
        return column === 4 && pauseLoader.item ? pauseLoader.item.navigationBadges() : []
    }
    TableView.onPooled: pooled = true
    TableView.onReused: pooled = false
    objectName: "monthCell_" + row + "_" + column
    implicitWidth: 100
    implicitHeight: rowLayout.height
    color: cell.tableContext.colors.table.background
    Accessible.role: Accessible.Cell
    Accessible.name: dayWeekday + " " + (column === 0 ? editValue : display)
    Accessible.description: dayProblem

    MouseArea {
        anchors.fill: parent
        property bool dismissOnly: false
        property point pressPosition
        property bool dragging: false
        onPressed: function(mouse) {
            dismissOnly = cell.tableContext.editSession.finishActive()
            pressPosition = Qt.point(mouse.x, mouse.y)
            dragging = false
            if (!dismissOnly) cell.tableContext.pointerSelect(cell.row, cell.column, mouse.modifiers)
        }
        onPositionChanged: function(mouse) {
            if (!pressed || dismissOnly) return
            if (Math.abs(mouse.x - pressPosition.x) + Math.abs(mouse.y - pressPosition.y) > Qt.styleHints.startDragDistance)
                dragging = true
            if (dragging) cell.tableContext.dragSelect(mapToItem(null, mouse.x, mouse.y))
        }
        onClicked: function(mouse) {
            if (dismissOnly || dragging) return
            if (!mouse.modifiers && cell.editableCell)
                cell.tableContext.editSelected()
        }
    }
    Loader {
        id: dateLoader
        active: cell.column === 0
        width: cell.width; height: cell.bodyHeight
        sourceComponent: Component {
            DateCell {
                colors: cell.tableContext.colors
                dark: cell.tableContext.ui.dark
                ink: cell.tableContext.ink
                rowIndex: cell.row
                display: cell.display
                fullDate: cell.editValue
                weekday: cell.dayWeekday
                week: cell.dayWeek
                dayState: cell.dayState
                dayProblem: cell.dayProblem
                isToday: cell.isToday
                dateSize: cell.tableContext.layoutInfo.dateSize
                weekdaySize: cell.tableContext.layoutInfo.weekdaySize
                ruleLayer: cell.dividerLayer
                ruleVisible: cell.column === 0 && !cell.pooled && cell.visible
                ruleWidth: cell.view.width
                ruleBottom: cell.dividerBottom
                ruleTop: cell.column === 0 && cell.isToday ? cell.tableContext.dividerY(cell.y - cell.view.contentY) : 0
                ruleGap: cell.dividerGap
                rowGap: cell.rowLayout.gap
            }
        }
    }
    Loader {
        id: mainBadgeLoader
        active: cell.column > 0 && cell.column < 4
        sourceComponent: Component {
            CellBadge {
                id: mainBadge
                objectName: "tableBadge_" + cell.row + "_" + cell.column
                tableNavigation: cell.tableContext
                onActiveFocusChanged: if (activeFocus) cell.tableContext.badgeFocused(mainBadge, cell.row, cell.column)
                editSession: cell.tableContext.editSession
                visible: cell.column > 0 && cell.column < 4 && !cell.editing
                x: (cell.width - width) / 2; y: (cell.bodyHeight - height) / 2
                width: cell.column === 1 ? cell.width - 10 : Math.max(implicitWidth, cell.tableContext.layoutInfo.timeBadgeWidth)
                height: cell.tableContext.layoutInfo.badgeHeight
                colors: cell.tableContext.colors
                appearance: cell.cellBadge
                text: cell.cellBadge.texts ? cell.cellBadge.texts[0] : cell.display
                plain: cell.tableContext.ui.closed
                outlined: cell.expected
                interactive: cell.editableCell
                onPointerPressed: function(modifiers) { cell.tableContext.pointerSelect(cell.row, cell.column, modifiers) }
                onPointerDragged: function(position) { cell.tableContext.dragSelect(position) }
                onClicked: function(modifiers) {
                    if (!modifiers) { cell.tableContext.selectCell(cell.row, cell.column, false); cell.tableContext.editSelected() }
                }
            }
        }
    }
    Loader {
        id: pauseLoader
        active: cell.column === 4
        visible: !cell.editing
        width: cell.width
        height: item ? item.implicitHeight : 0
        y: (cell.bodyHeight - height) / 2
        sourceComponent: Component {
            PauseCell {
                rows: cell.rowLayout.badges
                colors: cell.tableContext.colors
                editSession: cell.tableContext.editSession
                tableNavigation: cell.tableContext
                rowIndex: cell.row
                badgeHeight: cell.tableContext.layoutInfo.badgeHeight
                closed: cell.tableContext.ui.closed
                editable: cell.editableCell
            }
        }
    }
    Loader {
        active: cell.column > 4
        width: cell.width; height: cell.bodyHeight
        sourceComponent: Component {
            Text {
                width: cell.width; height: cell.bodyHeight
                text: cell.display
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font.pointSize: 10; font.bold: true
                color: cell.display.indexOf("-") === 0 ? cell.tableContext.colors.model.overtime_negative
                       : cell.display !== "00:00" && cell.display !== "" ? cell.tableContext.colors.model.overtime_positive : cell.tableContext.colors.model.read_only_text
            }
        }
    }
    Rectangle {
        anchors.fill: parent
        anchors.bottomMargin: cell.rowLayout.gap
        visible: cell.column === 0 && cell.view.activeFocus && cell.tableContext.selectedRow === cell.row && cell.tableContext.selectedColumn === 0
        color: "transparent"
        radius: 6
        border.width: 2
        border.color: cell.tableContext.colors.primary
    }
    TableView.editDelegate: CellEditor {
        session: cell.tableContext.editSession
        colors: cell.tableContext.colors
        appearance: cell.cellBadge
        interruptionTarget: cell.tableContext.interruptionTarget
        columnIndex: cell.column
        bodyHeight: cell.bodyHeight
        badgeWidth: mainBadgeLoader.item ? mainBadgeLoader.item.width : cell.width - 10
        badgeHeight: cell.tableContext.layoutInfo.badgeHeight
        timeBadgeWidth: cell.tableContext.layoutInfo.timeBadgeWidth
        initialValue: cell.column === 4 ? "" : cell.tableContext.controller.initialCellValue(cell.row, cell.column)
        initialText: cell.tableContext.initialEditText
        editValue: cell.editValue
        onEditorOpened: function(editor) { cell.tableContext.editorOpened(editor) }
        onEditorClosed: function(editor) { if (cell && cell.tableContext) cell.tableContext.editorClosed(editor) }
        onCloseRequested: cell.view.closeEditor()
        onInitialTextConsumed: cell.tableContext.consumeInitialEditText()
        onValueCommitted: function(value) { cell.tableContext.controller.editCell(cell.row, cell.column, value) }
    }
}
