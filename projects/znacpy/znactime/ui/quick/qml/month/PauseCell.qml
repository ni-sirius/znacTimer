import QtQuick
import ".."

Column {
    id: pauseRows
    required property var rows
    required property var colors
    required property var editSession
    required property var tableNavigation
    required property int rowIndex
    required property real badgeHeight
    required property bool closed
    required property bool editable
    function navigationBadges() {
        let badges = []
        for (let row = 0; row < pauseRowRepeater.count; ++row) {
            const line = pauseRowRepeater.itemAt(row)
            for (let index = 0; index < line.chips.count; ++index)
                badges.push(line.chips.itemAt(index))
        }
        return badges
    }
    width: parent.width
    spacing: 4
    Repeater {
        id: pauseRowRepeater
        model: pauseRows.rows
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
                    objectName: "pauseBadge_" + pauseRows.rowIndex + "_" + editTarget.action + "_" + (editTarget.period_index ?? "new")
                    tableNavigation: pauseRows.tableNavigation
                    onActiveFocusChanged: if (activeFocus) pauseRows.tableNavigation.badgeFocused(pauseBadge, pauseRows.rowIndex, 4, pauseRows.navigationBadges().indexOf(pauseBadge))
                    editSession: pauseRows.editSession
                    colors: pauseRows.colors
                    appearance: modelData.item
                    text: modelData.item.text
                    tooltipText: modelData.item.tooltip || ""
                    width: Math.max(implicitWidth, modelData.width)
                    height: pauseRows.badgeHeight
                    plain: pauseRows.closed
                    interactive: pauseRows.editable
                    onPointerPressed: function(modifiers) { pauseRows.tableNavigation.pointerSelect(pauseRows.rowIndex, 4, modifiers) }
                    onPointerDragged: function(position) { pauseRows.tableNavigation.dragSelect(position) }
                    onClicked: function(modifiers) { if (!modifiers) pauseRows.tableNavigation.editInterruption(pauseRows.rowIndex, modelData.item.target) }
                }
            }
        }
    }
}
