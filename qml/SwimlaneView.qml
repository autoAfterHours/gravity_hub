// SwimlaneView.qml — Orbit360 v4.1
// Parallel execution view: one column per concurrently-running script.
//
// Context properties required:
//   appBackend : AppBackend — .lanes (QVariantList of SwimlaneLane)
//                             SwimlaneLane exposes: name (str), dotColor (str),
//                             lineAdded(text: str, color: str) signal

import QtQuick
import QtQuick.Controls

Item {
    id: root

    // ── Horizontal scroll container ───────────────────────────────────────
    ScrollView {
        anchors.fill:   parent
        contentWidth:   laneRow.implicitWidth + 8
        contentHeight:  height

        ScrollBar.horizontal.policy: ScrollBar.AsNeeded
        ScrollBar.vertical.policy:   ScrollBar.AlwaysOff

        ScrollBar.horizontal.contentItem: Rectangle {
            implicitHeight: 6
            radius: 3
            color: parent.pressed ? "#585b70" : "#45475a"
            opacity: parent.active ? 1.0 : 0.0
            Behavior on opacity { NumberAnimation { duration: 150 } }
        }
        ScrollBar.horizontal.background: Rectangle { color: "transparent" }

        Row {
            id: laneRow
            spacing: 3
            height:  root.height - 10
            topPadding: 4
            leftPadding: 4

            Repeater {
                model: appBackend ? appBackend.lanes : []

                delegate: Rectangle {
                    id: lanePanel
                    width:  240
                    height: laneRow.height
                    color:  "#1e1e2e"
                    border.color: "#313244"
                    border.width: 1
                    radius: 4
                    clip: true

                    // ── Header ────────────────────────────────────────────
                    Rectangle {
                        id: laneHeader
                        width:  parent.width
                        height: 28
                        color:  "#252536"
                        radius: 4

                        // Mask bottom corners so only top is rounded
                        Rectangle {
                            anchors {
                                left: parent.left; right: parent.right; bottom: parent.bottom
                            }
                            height: parent.radius
                            color:  parent.color
                        }

                        Row {
                            anchors {
                                verticalCenter: parent.verticalCenter
                                left:  parent.left;  leftMargin: 8
                                right: parent.right; rightMargin: 8
                            }
                            spacing: 6

                            // Pulsing status dot
                            Rectangle {
                                id: laneDot
                                width: 8; height: 8; radius: 4
                                anchors.verticalCenter: parent.verticalCenter
                                color: modelData.dotColor

                                Behavior on color { ColorAnimation { duration: 300 } }

                                SequentialAnimation {
                                    running: modelData.dotColor === "#89b4fa"
                                    loops:   Animation.Infinite
                                    onStopped: laneDot.opacity = 1.0
                                    NumberAnimation {
                                        target: laneDot; property: "opacity"
                                        to: 0.15; duration: 600
                                        easing.type: Easing.InOutSine
                                    }
                                    NumberAnimation {
                                        target: laneDot; property: "opacity"
                                        to: 1.0; duration: 600
                                        easing.type: Easing.InOutSine
                                    }
                                }
                            }

                            Text {
                                width: parent.width - 22
                                text:  modelData.name
                                color: "#cdd6f4"
                                font.family:   "Segoe UI"
                                font.pixelSize: 11
                                font.weight:    Font.DemiBold
                                elide: Text.ElideRight
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }

                    // ── Per-lane log ListModel + connection ───────────────
                    ListModel { id: lineModel }

                    Connections {
                        target: modelData
                        function onLineAdded(text, color) {
                            if (lineModel.count >= 5000)
                                lineModel.remove(0, 1)
                            lineModel.append({ lineText: text, lineColor: color })
                        }
                    }

                    // ── Log ListView ──────────────────────────────────────
                    ListView {
                        id: laneLog
                        anchors {
                            top:    laneHeader.bottom
                            left:   parent.left;   leftMargin:   4
                            right:  parent.right;  rightMargin:  4
                            bottom: parent.bottom; bottomMargin: 4
                        }
                        model:   lineModel
                        clip:    true
                        spacing: 1

                        property bool _pinned: false

                        onCountChanged: {
                            if (!_pinned) Qt.callLater(positionViewAtEnd)
                        }
                        onMovementStarted: {
                            if (!atYEnd) _pinned = true
                        }
                        onAtYEndChanged: {
                            if (atYEnd) _pinned = false
                        }

                        add: Transition {
                            NumberAnimation {
                                property: "opacity"
                                from: 0; to: 1; duration: 120
                            }
                        }

                        delegate: Text {
                            width:    laneLog.width
                            text:     model.lineText
                            color:    model.lineColor
                            font.family:   "JetBrains Mono, Fira Code, Cascadia Code, Consolas, Courier New"
                            font.pixelSize: 10
                            wrapMode: Text.WrapAnywhere
                            leftPadding: 2
                            renderType: Text.NativeRendering
                        }

                        ScrollBar.vertical: ScrollBar {
                            id: vBar
                            policy: ScrollBar.AsNeeded
                            contentItem: Rectangle {
                                implicitWidth:  vBar.hovered ? 5 : 3
                                implicitHeight: 20
                                radius: 2
                                color:  vBar.pressed ? "#585b70" : "#45475a"
                                opacity: vBar.active ? 0.8 : 0.0
                                Behavior on implicitWidth { NumberAnimation { duration: 100 } }
                                Behavior on opacity       { NumberAnimation { duration: 120 } }
                            }
                            background: Rectangle { color: "transparent" }
                        }
                    }
                }
            }
        }
    }

    // ── Empty state ───────────────────────────────────────────────────────
    Text {
        anchors.centerIn: parent
        text:    "Parallel mode — lanes appear when scripts start"
        color:   "#45475a"
        font.family:    "Segoe UI"
        font.pixelSize: 12
        visible: !appBackend || appBackend.lanes.length === 0
    }
}
