import QtQuick

Canvas {
    id: icon
    property color color: "black"
    property bool up: false
    implicitWidth: 12
    implicitHeight: 12
    onColorChanged: requestPaint()
    onUpChanged: requestPaint()
    onPaint: {
        let ctx = getContext("2d")
        ctx.reset()
        ctx.strokeStyle = color
        ctx.lineWidth = 1.8
        ctx.lineCap = "round"
        ctx.lineJoin = "round"
        ctx.beginPath()
        ctx.moveTo(2.5, up ? 7.5 : 4.5)
        ctx.lineTo(6, up ? 4 : 8)
        ctx.lineTo(9.5, up ? 7.5 : 4.5)
        ctx.stroke()
    }
}
