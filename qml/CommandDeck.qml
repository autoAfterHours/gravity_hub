import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: deckRoot

    readonly property var cards: [
        { screenIndex: 1, icon: "⚡", title: "LAUNCHER",  accent: "#89b4fa",
          desc: "Execute automated tests across systems and environments." },
        { screenIndex: 2, icon: "▲", title: "PULSE",     accent: "#fab387",
          desc: "View test metrics, run trends and health insights." },
        { screenIndex: 3, icon: "◈", title: "GENESIS",   accent: "#94e2d5",
          desc: "Manage test data, datasets and data configurations." },
        { screenIndex: 4, icon: "▣", title: "VAULT",     accent: "#cba6f7",
          desc: "Browse archived run history, execution logs, and result exports." },
    ]

    // ── Background ──────────────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: "#080d18"

        // Deep radial horizon glow
        Canvas {
            id: horizonGlow
            anchors.fill: parent
            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                var grad = ctx.createRadialGradient(
                    width / 2, height,      8,
                    width / 2, height * 0.4, width * 0.65
                )
                grad.addColorStop(0.0, "#003070")
                grad.addColorStop(0.25, "#001840")
                grad.addColorStop(0.55, "#000d20")
                grad.addColorStop(1.0,  "transparent")
                ctx.fillStyle = grad
                ctx.fillRect(0, 0, width, height)
            }
        }

        // Animated concentric orbit rings
        Canvas {
            id: orbitCanvas
            anchors.fill: parent
            opacity: 0.22

            property real angle: 0
            NumberAnimation on angle {
                from: 0; to: 360
                duration: 28000
                loops: Animation.Infinite
                easing.type: Easing.Linear
            }
            onAngleChanged: requestPaint()

            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                var cx = width / 2
                var cy = height * 0.92

                ctx.save()
                ctx.translate(cx, cy)
                ctx.rotate(angle * Math.PI / 180)
                ctx.strokeStyle = "#3a6a99"
                ctx.lineWidth = 1
                ctx.setLineDash([8, 14])
                ctx.beginPath()
                ctx.scale(1.0, 0.26)
                ctx.arc(0, 0, width * 0.44, 0, Math.PI * 2)
                ctx.stroke()
                ctx.restore()

                ctx.save()
                ctx.translate(cx, cy)
                ctx.rotate(-angle * 0.65 * Math.PI / 180)
                ctx.strokeStyle = "#1e4a70"
                ctx.lineWidth = 1
                ctx.setLineDash([4, 10])
                ctx.beginPath()
                ctx.scale(1.0, 0.20)
                ctx.arc(0, 0, width * 0.30, 0, Math.PI * 2)
                ctx.stroke()
                ctx.restore()
            }
        }

        // Bottom horizon arc
        Canvas {
            width: parent.width
            height: 180
            anchors.bottom: parent.bottom
            opacity: 0.55
            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                var grad = ctx.createRadialGradient(
                    width / 2, height + 10, 10,
                    width / 2, height - 60, width * 0.55
                )
                grad.addColorStop(0.0,  "#0066ff")
                grad.addColorStop(0.2,  "#0044bb")
                grad.addColorStop(0.5,  "#001840")
                grad.addColorStop(1.0,  "transparent")
                ctx.fillStyle = grad
                ctx.fillRect(0, 0, width, height)
            }
        }
    }

    // ── Title — pinned to top-center with breathing room ──────────────────
    Row {
        anchors.top: parent.top
        anchors.topMargin: 28
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 0

        Text {
            text: "ORBIT"
            font.family: "Segoe UI"
            font.pixelSize: 38
            font.bold: true
            font.letterSpacing: 7
            color: "#e8eaf6"
            SequentialAnimation on opacity {
                loops: Animation.Infinite
                NumberAnimation { to: 0.86; duration: 1500; easing.type: Easing.InOutSine }
                NumberAnimation { to: 1.0;  duration: 1500; easing.type: Easing.InOutSine }
            }
        }
        Text {
            text: "360"
            font.family: "Segoe UI"
            font.pixelSize: 38
            font.bold: true
            font.letterSpacing: 7
            color: "#ff6600"
            SequentialAnimation on opacity {
                loops: Animation.Infinite
                NumberAnimation { to: 0.86; duration: 1500; easing.type: Easing.InOutSine }
                NumberAnimation { to: 1.0;  duration: 1500; easing.type: Easing.InOutSine }
            }
        }
    }

    // ── Destination cards — independently centered so the rings fill the gap
    Row {
        anchors.centerIn: parent
        anchors.verticalCenterOffset: 40
        spacing: 18

        Repeater {
            model: deckRoot.cards.length

            delegate: Rectangle {
                property var cardData: deckRoot.cards[index]

                width:  196
                height: 248
                radius: 12
                color:  cardHover.containsMouse ? "#131e30" : "#0d1520"
                border.color: cardHover.containsMouse
                              ? (cardData ? cardData.accent : "#89b4fa")
                              : "#1e3a5f"
                border.width: cardHover.containsMouse ? 2 : 1

                Behavior on color        { ColorAnimation { duration: 100 } }
                Behavior on border.color { ColorAnimation { duration: 100 } }

                // Entrance animation
                opacity: 0
                SequentialAnimation on opacity {
                    running: true
                    PauseAnimation  { duration: index * 80 }
                    NumberAnimation { from: 0; to: 1; duration: 300; easing.type: Easing.OutCubic }
                }

                // Icon circle
                Rectangle {
                    width: 68; height: 68; radius: 34
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.top
                    anchors.topMargin: 28
                    color: "transparent"
                    border.color: cardData ? cardData.accent : "#89b4fa"
                    border.width: cardHover.containsMouse ? 2 : 1
                    opacity: cardHover.containsMouse ? 1.0 : 0.65
                    Behavior on opacity      { NumberAnimation { duration: 100 } }
                    Behavior on border.width { NumberAnimation { duration: 100 } }

                    Rectangle {
                        anchors.fill: parent
                        radius: parent.radius
                        color: cardData ? cardData.accent : "#89b4fa"
                        opacity: cardHover.containsMouse ? 0.10 : 0.0
                        Behavior on opacity { NumberAnimation { duration: 100 } }
                    }

                    Text {
                        text: cardData ? cardData.icon : ""
                        font.pixelSize: 26
                        color: cardData ? cardData.accent : "#89b4fa"
                        anchors.centerIn: parent
                    }
                }

                // Card title
                Text {
                    text: cardData ? cardData.title : ""
                    font.family: "Segoe UI"
                    font.pixelSize: 13
                    font.bold: true
                    font.letterSpacing: 2.5
                    color: cardData ? cardData.accent : "#89b4fa"
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.top
                    anchors.topMargin: 112
                }

                // Description
                Text {
                    text: cardData ? cardData.desc : ""
                    font.family: "Segoe UI"
                    font.pixelSize: 11
                    color: "#7a8faa"
                    anchors.left:   parent.left;   anchors.leftMargin:   16
                    anchors.right:  parent.right;  anchors.rightMargin:  16
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 24
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    lineHeight: 1.45
                }

                MouseArea {
                    id: cardHover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (cardData) deckNavBridge.navigate(cardData.screenIndex)
                    }
                }
            }
        }
    }
}
