import QtQuick
import ".."

Item {
    id: dateCell
    required property var colors
    required property bool dark
    required property color ink
    required property int rowIndex
    required property string display
    required property string fullDate
    required property string weekday
    required property string week
    required property string dayState
    required property string dayProblem
    required property bool isToday
    required property real dateSize
    required property real weekdaySize
    required property Item ruleLayer
    required property bool ruleVisible
    required property real ruleWidth
    required property real ruleBottom
    required property real ruleTop
    required property real ruleGap
    required property real rowGap
    property alias infoButton: dayInfo
    anchors.fill: parent
    // Draw one continuous rule per loaded row outside the moving
    // content. Snap after its scroll/scene transforms, so fractional
    // DPI and fractional delegate positions cannot change coverage.
    // Use integer local sizes scaled back to device pixels: the
    // software renderer rounds fractional Rectangle dimensions.
    // Include the week gap in the same band to avoid seams.
    Item {
        parent: dateCell.ruleLayer
        objectName: "rowDivider_" + dateCell.rowIndex
        visible: dateCell.ruleVisible
        y: dateCell.ruleBottom - dateCell.ruleGap - 1 / Screen.devicePixelRatio
        width: dateCell.ruleWidth * Screen.devicePixelRatio
        height: Math.round(dateCell.rowGap * Screen.devicePixelRatio) + 1
        scale: 1 / Screen.devicePixelRatio
        transformOrigin: Item.TopLeft
        Rectangle {
            width: parent.width; height: 1
            color: dateCell.isToday ? dateCell.colors.primary : dateCell.colors.table.divider
        }
        Rectangle {
            y: 1; width: parent.width; height: parent.height - 1
            color: dateCell.colors.table.divider
        }
    }
    Rectangle {
        parent: dateCell.ruleLayer
        visible: dateCell.ruleVisible && dateCell.isToday
        z: 1
        y: dateCell.ruleTop
        width: dateCell.ruleWidth * Screen.devicePixelRatio
        height: 1
        scale: 1 / Screen.devicePixelRatio
        transformOrigin: Item.TopLeft
        color: dateCell.colors.primary
    }
    HoverHandler { id: dateHover }
    AppToolTip {
        colors: dateCell.colors
        text: dateCell.fullDate
        hoverRequested: dateHover.hovered && !dayInfo.hovered
    }
    Rectangle {
        id: dateGlow
        visible: dateCell.dayState !== ""
        width: parent.width; height: dateCell.height - 2; y: 1
        property color accent: dateCell.dayState === "closed" ? (dateCell.dark ? dateCell.colors.table.texture_closed : Qt.darker(dateCell.colors.table.texture_closed, 3.5))
                               : dateCell.dayState === "valid" ? dateCell.colors.model.overtime_positive
                               : dateCell.dayState === "invalid" ? dateCell.colors.model.overtime_negative : dateCell.colors.primary
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Qt.rgba(dateGlow.accent.r, dateGlow.accent.g, dateGlow.accent.b, 0.24) }
            GradientStop { position: 0.35; color: Qt.rgba(dateGlow.accent.r, dateGlow.accent.g, dateGlow.accent.b, 0.14) }
            GradientStop { position: 0.7; color: Qt.rgba(dateGlow.accent.r, dateGlow.accent.g, dateGlow.accent.b, 0.05) }
            GradientStop { position: 1; color: "transparent" }
        }
    }
    Item {
        width: parent.width; height: dateCell.height
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
                text: dateCell.display; color: dateCell.ink
                font.family: Qt.application.font.family
                font.pixelSize: dateCell.dateSize; font.bold: true
            }
            Text {
                id: weekdayText
                y: dateBlock.textTop + dateBlock.dateBounds.height + 1 - dateBlock.weekdayBounds.y - baselineOffset
                text: dateCell.weekday; color: dateCell.ink
                font.family: Qt.application.font.family
                font.pixelSize: dateCell.weekdaySize
            }
        }
        Text { anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; text: dateCell.week; color: dateCell.ink; font.pointSize: 10 }
        InfoButton {
            id: dayInfo
            objectName: "dateInfoIcon_" + dateCell.rowIndex
            visible: dateCell.dayProblem !== ""
            anchors.right: parent.right; anchors.rightMargin: 60; anchors.verticalCenter: parent.verticalCenter
            width: 16; height: 16
            colors: dateCell.colors
            message: dateCell.dayProblem
            Accessible.name: "Day information"
        }
    }
}
