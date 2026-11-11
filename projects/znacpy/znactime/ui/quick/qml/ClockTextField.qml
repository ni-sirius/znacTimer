import QtQuick
import QtQuick.Controls

TextField {
    property bool timeOnly: true
    validator: timeOnly ? clockValidator : null
    RegularExpressionValidator { id: clockValidator; regularExpression: /[0-9:]*/ }
    function typeStart(value) {
        if (!timeOnly || /^[0-9:]*$/.test(value)) { text = value; cursorPosition = text.length }
    }
}
