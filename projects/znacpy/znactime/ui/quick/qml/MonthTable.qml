import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models

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
                property real dividerBottom: column === 0 ? root.dividerY(cell.y - table.contentY + cell.height) : 0
                property real dividerGap: Math.round(rowLayout.gap * Screen.devicePixelRatio) / Screen.devicePixelRatio
                property bool expected: cellBadge.state === "expected"
                property bool pooled: false
                property var dateInfo: dateLoader.item ? dateLoader.item.infoButton : null
                function navigationBadges() {
                    if (column > 0 && column < 4) return cell.editing ? [] : [mainBadge]
                    return column === 4 && pauseLoader.item ? pauseLoader.item.navigationBadges() : []
                }
                TableView.onPooled: pooled = true
                TableView.onReused: pooled = false
                objectName: "monthCell_" + row + "_" + column
                implicitWidth: 100
                implicitHeight: rowLayout.height
                color: root.colors.table.background
                Accessible.role: Accessible.Cell
                Accessible.name: dayWeekday + " " + (column === 0 ? editValue : display)
                Accessible.description: dayProblem

                MouseArea {
                    anchors.fill: parent
                    property bool dismissOnly: false
                    property point pressPosition
                    property bool dragging: false
                    onPressed: function(mouse) {
                        dismissOnly = root.editSession.finishActive()
                        pressPosition = Qt.point(mouse.x, mouse.y)
                        dragging = false
                        if (!dismissOnly) root.pointerSelect(cell.row, cell.column, mouse.modifiers)
                    }
                    onPositionChanged: function(mouse) {
                        if (!pressed || dismissOnly) return
                        if (Math.abs(mouse.x - pressPosition.x) + Math.abs(mouse.y - pressPosition.y) > Qt.styleHints.startDragDistance)
                            dragging = true
                        if (dragging) root.dragSelect(mapToItem(null, mouse.x, mouse.y))
                    }
                    onClicked: function(mouse) {
                        if (dismissOnly || dragging) return
                        if (!mouse.modifiers && cell.editableCell)
                            root.editSelected()
                    }
                }
                Loader {
                    id: dateLoader
                    active: cell.column === 0
                    width: cell.width; height: cell.bodyHeight
                    sourceComponent: Component {
                        Item {
                            property alias infoButton: dayInfo
                            anchors.fill: parent
                            HoverHandler { id: dateHover }
                            AppToolTip {
                                colors: root.colors
                                text: cell.editValue
                                hoverRequested: dateHover.hovered && !dayInfo.hovered
                            }
                            Rectangle {
                                id: dateGlow
                                visible: cell.dayState !== ""
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
                                InfoButton {
                                    id: dayInfo
                                    objectName: "dateInfoIcon_" + cell.row
                                    visible: cell.dayProblem !== ""
                                    anchors.right: parent.right; anchors.rightMargin: 60; anchors.verticalCenter: parent.verticalCenter
                                    width: 16; height: 16
                                    colors: root.colors
                                    message: cell.dayProblem
                                    Accessible.name: "Day information"
                                }
                            }
                        }
                    }
                }
                CellBadge {
                    id: mainBadge
                    objectName: "tableBadge_" + cell.row + "_" + cell.column
                    tableNavigation: root
                    onActiveFocusChanged: if (activeFocus) root.badgeFocused(mainBadge, cell.row, cell.column)
                    editSession: root.editSession
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
                    onPointerPressed: function(modifiers) { root.pointerSelect(cell.row, cell.column, modifiers) }
                    onPointerDragged: function(position) { root.dragSelect(position) }
                    onClicked: function(modifiers) {
                        if (!modifiers) { root.selectCell(cell.row, cell.column, false); root.editSelected() }
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
                        Column {
                            id: pauseRows
                            function navigationBadges() {
                                let badges = []
                                for (let row = 0; row < pauseRowRepeater.count; ++row) {
                                    const line = pauseRowRepeater.itemAt(row)
                                    for (let index = 0; index < line.chips.count; ++index)
                                        badges.push(line.chips.itemAt(index))
                                }
                                return badges
                            }
                            width: cell.width
                            spacing: 4
                            Repeater {
                                id: pauseRowRepeater
                                model: cell.rowLayout.badges
                                delegate: Row {
                                    required property var modelData
                                    property alias chips: pauseBadgeRepeater
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    spacing: 4
                                    Repeater {
                                        id: pauseBadgeRepeater
                                        model: parent.modelData
                                        delegate: CellBadge {
                                            id: pauseBadge
                                            required property var modelData
                                            readonly property var editTarget: modelData.item.target || ({action: "readonly", period_index: null})
                                            objectName: "pauseBadge_" + cell.row + "_" + editTarget.action + "_" + (editTarget.period_index ?? "new")
                                            tableNavigation: root
                                            onActiveFocusChanged: if (activeFocus) root.badgeFocused(pauseBadge, cell.row, 4, pauseRows.navigationBadges().indexOf(pauseBadge))
                                            editSession: root.editSession
                                            colors: root.colors
                                            appearance: modelData.item
                                            text: modelData.item.text
                                            tooltipText: modelData.item.tooltip || ""
                                            width: Math.max(implicitWidth, modelData.width)
                                            height: root.layoutInfo.badgeHeight
                                            plain: root.ui.closed
                                            interactive: cell.editableCell
                                            onPointerPressed: function(modifiers) { root.pointerSelect(cell.row, cell.column, modifiers) }
                                            onPointerDragged: function(position) { root.dragSelect(position) }
                                            onClicked: function(modifiers) { if (!modifiers) root.editInterruption(cell.row, modelData.item.target) }
                                        }
                                    }
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
                Rectangle {
                    anchors.fill: parent
                    anchors.bottomMargin: cell.rowLayout.gap
                    visible: cell.column === 0 && table.activeFocus && root.selectedRow === cell.row && root.selectedColumn === 0
                    color: "transparent"
                    radius: 6
                    border.width: 2
                    border.color: root.colors.primary
                }
                // Draw one continuous rule per loaded row outside the moving
                // content. Snap after its scroll/scene transforms, so fractional
                // DPI and fractional delegate positions cannot change coverage.
                // Use integer local sizes scaled back to device pixels: the
                // software renderer rounds fractional Rectangle dimensions.
                // Include the week gap in the same band to avoid seams.
                Item {
                    parent: dividerOverlay
                    objectName: cell.column === 0 ? "rowDivider_" + cell.row : ""
                    visible: cell.column === 0 && !cell.pooled && cell.visible
                    y: cell.dividerBottom - cell.dividerGap - 1 / Screen.devicePixelRatio
                    width: table.width * Screen.devicePixelRatio
                    height: Math.round(cell.rowLayout.gap * Screen.devicePixelRatio) + 1
                    scale: 1 / Screen.devicePixelRatio
                    transformOrigin: Item.TopLeft
                    Rectangle {
                        width: parent.width; height: 1
                        color: cell.isToday ? root.colors.primary : root.colors.table.divider
                    }
                    Rectangle {
                        y: 1; width: parent.width; height: parent.height - 1
                        color: root.colors.table.divider
                    }
                }
                Rectangle {
                    parent: dividerOverlay
                    visible: cell.column === 0 && !cell.pooled && cell.visible && cell.isToday
                    z: 1
                    y: cell.column === 0 && cell.isToday ? root.dividerY(cell.y - table.contentY) : 0
                    width: table.width * Screen.devicePixelRatio
                    height: 1
                    scale: 1 / Screen.devicePixelRatio
                    transformOrigin: Item.TopLeft
                    color: root.colors.primary
                }
                TableView.editDelegate: Loader {
                    id: cellEditorLoader
                    property var session: root.editSession
                    focus: true
                    x: 5; width: parent.width - 10
                    y: (cell.bodyHeight - height) / 2
                    height: root.layoutInfo.badgeHeight + 2
                    sourceComponent: cell.column === 4 ? periodEditor : lineEditor
                    onLoaded: {
                        root.activeEditor = item
                        session.begin(cellEditorLoader, function() {
                            if (item) item.save()
                            table.closeEditor()
                        })
                        item.focusStart()
                        if (root.initialEditText !== "") {
                            item.typeStart(root.initialEditText)
                            root.initialEditText = ""
                        }
                    }
                    Component.onDestruction: {
                        if (root.activeEditor === item) root.activeEditor = null
                        if (session) session.end(cellEditorLoader)
                    }
                    TableView.onCommit: { if (item) item.save() }
                    Component {
                        id: lineEditor
                        ClockTextField {
                            objectName: cell.column === 1 ? "specialCellEditor" : "timeCellEditor"
                            timeOnly: cell.column !== 1
                            Component.onCompleted: text = root.controller.initialCellValue(cell.row, cell.column)
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
                            function save() {
                                const value = resolvedValue()
                                if (value !== null) root.controller.editCell(cell.row, 4, value)
                            }
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
        function onMonthLoaded() { Qt.callLater(root.revealToday) }
    }
}
