// ScreenshotStrip.qml — Orbit360 v4.1
// Collapsible horizontal strip of PNG thumbnails for the current run.
//
// Context properties required:
//   appBackend : AppBackend — .screenshotModel (QAbstractListModel, role: imagePath)
//                           — .screenshotCount (int, notifies screenshotCountChanged)

import QtQuick
import QtQuick.Controls

Item {
    id: root

    // Collapsed to zero when there are no screenshots; animates open/shut otherwise.
    height: appBackend && appBackend.screenshotCount > 0
            ? (expanded ? 148 : 26)
            : 0
    clip: true

    Behavior on height { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

    property bool expanded: false

    // ── Toggle header ─────────────────────────────────────────────────────
    Rectangle {
        id: header
        width:  parent.width
        height: 26
        color:  headerArea.containsMouse ? "#252536" : "#1e1e2e"
        Behavior on color { ColorAnimation { duration: 80 } }

        Row {
            anchors {
                verticalCenter: parent.verticalCenter
                left:  parent.left;  leftMargin: 10
                right: parent.right; rightMargin: 10
            }
            spacing: 6

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text:  "◈"
                color: "#89b4fa"
                font.pixelSize: 11
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text:  "Screenshots (" + (appBackend ? appBackend.screenshotCount : 0) + ")"
                color: "#89b4fa"
                font.family:   "Segoe UI"
                font.pixelSize: 11
                font.weight: Font.Medium
            }

            Item { width: 1; height: 1 }   // spacer

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text:  root.expanded ? "▲" : "▼"
                color: "#585b70"
                font.pixelSize: 9
            }
        }

        MouseArea {
            id: headerArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.expanded = !root.expanded
        }
    }

    // ── Thumbnail strip ───────────────────────────────────────────────────
    ListView {
        id: stripList
        anchors {
            top:    header.bottom
            left:   parent.left
            right:  parent.right
            bottom: parent.bottom
            topMargin: 2; leftMargin: 4; rightMargin: 4; bottomMargin: 4
        }
        orientation:  ListView.Horizontal
        model:        appBackend ? appBackend.screenshotModel : null
        clip:         true
        spacing:      4

        add: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200 }
            NumberAnimation { property: "scale";   from: 0.9; to: 1; duration: 200; easing.type: Easing.OutBack }
        }

        delegate: Item {
            id: thumbItem
            height: stripList.height
            width:  thumb.implicitWidth > 0 ? thumb.implicitWidth : 120

            Image {
                id: thumb
                height:   parent.height
                width:    sourceSize.width > 0
                          ? Math.min(sourceSize.width * height / sourceSize.height, 200)
                          : 120
                source:   {
                    var p = model.imagePath.replace(/\\/g, '/')
                    return p.charAt(0) === '/' ? ("file://" + p) : ("file:///" + p)
                }
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                smooth: true
                cache: false

                // Placeholder while loading
                Rectangle {
                    anchors.fill: parent
                    color:  "#252536"
                    radius: 3
                    visible: thumb.status !== Image.Ready

                    Text {
                        anchors.centerIn: parent
                        text:  "⏳"
                        color: "#585b70"
                        font.pixelSize: 14
                    }
                }

                // Hover border + tooltip
                Rectangle {
                    anchors.fill:  parent
                    radius:        3
                    color:         "transparent"
                    border.color:  thumbArea.containsMouse ? "#89b4fa" : "transparent"
                    border.width:  1
                    Behavior on border.color { ColorAnimation { duration: 80 } }
                }
            }

            ToolTip.visible: thumbArea.containsMouse
            ToolTip.delay:   400
            ToolTip.text:    {
                var parts = model.imagePath.split("/")
                return parts[parts.length - 1]
            }

            MouseArea {
                id: thumbArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape:  Qt.PointingHandCursor
                onClicked: {
                    var p = model.imagePath.replace(/\\/g, '/')
                    Qt.openUrlExternally(p.charAt(0) === '/' ? ("file://" + p) : ("file:///" + p))
                }
            }
        }

        ScrollBar.horizontal: ScrollBar {
            id: hBar
            policy: ScrollBar.AsNeeded
            contentItem: Rectangle {
                implicitWidth:  40
                implicitHeight: hBar.hovered ? 6 : 4
                radius:         2
                color:          hBar.pressed ? "#585b70" : "#45475a"
                opacity:        hBar.active ? 1.0 : 0.0
                Behavior on implicitHeight { NumberAnimation { duration: 100 } }
                Behavior on opacity        { NumberAnimation { duration: 150 } }
            }
            background: Rectangle { color: "transparent" }
        }
    }
}
