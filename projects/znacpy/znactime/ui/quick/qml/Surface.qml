import QtQuick

// Shared surface boundary for platform-specific materials.
Rectangle {
    property bool dark: false
    property bool translucent: false
    required property var colors
    property color surfaceColor: colors.header.surface
    radius: 12
    color: Qt.rgba(surfaceColor.r, surfaceColor.g, surfaceColor.b, translucent ? 0.95 : 1)
    border.color: colors.header.border
    border.width: 1
}
