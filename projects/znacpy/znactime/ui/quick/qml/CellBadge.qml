import QtQuick
import QtQuick.Controls

Rectangle {
    id: badge
    required property var colors
    required property var appearance
    property string text: ""
    property bool plain: false
    property bool outlined: false
    property bool interactive: true
    property bool editing: false
    property bool hovered: mouse.containsMouse && interactive && !plain
    property bool fullWidth: false
    property var editSession: null
    property var tableNavigation: null
    property string tooltipText: ""
    readonly property QtObject tooltipPopup: badgeTip
    signal clicked(int modifiers)
    signal pointerPressed(int modifiers)
    signal pointerDragged(point scenePosition)
    activeFocusOnTab: interactive && !plain && !editing
    Accessible.role: interactive && !plain ? Accessible.Button : Accessible.StaticText
    Accessible.name: text
    Accessible.onPressAction: activate()
    function activate() {
        if (!interactive || plain || editing) return
        if (editSession && editSession.finishActive()) return
        clicked(Qt.NoModifier)
    }
    Keys.onReturnPressed: function(event) {
        if (tableNavigation && event.modifiers & Qt.ControlModifier) tableNavigation.handleTableKey(event)
        else activate()
    }
    Keys.onEnterPressed: function(event) {
        if (tableNavigation && event.modifiers & Qt.ControlModifier) tableNavigation.handleTableKey(event)
        else activate()
    }
    Keys.onSpacePressed: activate()
    Keys.onPressed: function(event) {
        if (tableNavigation) tableNavigation.handleTableKey(event)
        else event.accepted = false
    }
    implicitWidth: Math.max(text === "+" ? 28 : 44, Math.ceil(label.implicitWidth) + 16)
    implicitHeight: metrics.height + 8
    radius: 6
    color: plain ? "transparent" : hovered ? colors.primary : (appearance.fillColor || colors.table.empty_fill)
    border.width: activeFocus || outlined && !plain ? 2 : 0
    border.color: activeFocus ? colors.primary : (appearance.borderColor || colors.primary)
    HoverHandler { id: tooltipHover }
    AppToolTip {
        id: badgeTip
        colors: badge.colors
        text: badge.tooltipText
        hoverRequested: tooltipHover.hovered && text !== "" && !badge.editing
    }
    FontMetrics { id: metrics; font: label.font }
    Text {
        id: label
        visible: badge.text !== "+" && !badge.editing
        anchors.fill: parent
        anchors.leftMargin: 8; anchors.rightMargin: 8
        text: badge.text
        font.pointSize: 10
        font.bold: true
        color: badge.hovered ? badge.colors.on_primary : (badge.appearance.textColor || badge.colors.table.empty_text)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    Item {
        objectName: "addInterruptionIcon"
        visible: badge.text === "+" && !badge.editing
        x: (badge.width - width) / 2
        y: (badge.height - height) / 2
        width: 10; height: 10
        Rectangle {
            anchors.centerIn: parent
            width: parent.width; height: 2
            color: label.color
        }
        Rectangle {
            anchors.centerIn: parent
            width: 2; height: parent.height
            color: label.color
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: badge.interactive && !badge.plain && !badge.editing
        cursorShape: Qt.PointingHandCursor
        property bool dismissOnly: false
        property point pressPosition
        property bool dragging: false
        onPressed: function(mouse) {
            dismissOnly = badge.editSession ? badge.editSession.finishActive() : false
            pressPosition = Qt.point(mouse.x, mouse.y)
            dragging = false
            if (!dismissOnly) badge.pointerPressed(mouse.modifiers)
        }
        onPositionChanged: function(mouse) {
            if (!pressed || dismissOnly) return
            if (Math.abs(mouse.x - pressPosition.x) + Math.abs(mouse.y - pressPosition.y) > Qt.styleHints.startDragDistance)
                dragging = true
            if (dragging) badge.pointerDragged(mapToItem(null, mouse.x, mouse.y))
        }
        onClicked: function(mouse) { if (!dismissOnly && !dragging) badge.clicked(mouse.modifiers) }
    }
}
