import QtQuick

Canvas {
    property color color: "black"
    property bool closed: false
    implicitWidth: 20
    implicitHeight: 20
    onColorChanged: requestPaint()
    onClosedChanged: requestPaint()
    onPaint: {
        let ctx = getContext("2d")
        ctx.reset()
        ctx.strokeStyle = color
        ctx.lineWidth = 1.6
        ctx.lineCap = "round"
        ctx.lineJoin = "round"
        ctx.beginPath()
        ctx.moveTo(7, 9)
        ctx.lineTo(7, closed ? 6 : 5)
        if (closed) { ctx.bezierCurveTo(7, 2, 13, 2, 13, 6); ctx.lineTo(13, 9) }
        else { ctx.bezierCurveTo(7, 1, 14, 1, 14, 5); ctx.lineTo(14, 6) }
        ctx.stroke()
        ctx.beginPath()
        ctx.roundedRect(5, 9, 10, 9, 2, 2)
        ctx.stroke()
        ctx.beginPath(); ctx.moveTo(10, 13); ctx.lineTo(10, 15); ctx.stroke()
    }
}
