// TitleBar.qml — Orbit360 v4.0
// Corporate blue header with ORBIT360 title, subtitle, and run-state animations.
//
// Context properties required:
//   titleBridge : TitleBarBridge — exposes runActive (bool, notify=runActiveChanged)
//
// Run-state sequence:
//   1. onRunActiveChanged(true)  → flash sweeps left→right (550ms InOutCubic)
//                                → glow overlay pulses (0.04↔0.14 opacity, InOutSine, infinite)
//                                → bottom strip pulses (0.15↔1.0 opacity, InOutSine, infinite)
//   2. onRunActiveChanged(false) → all animations stop, all opacities reset to 0

import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    color: "#003087"

    // ── Idle edge vignette ───────────────────────────────────────────────
    // Semi-transparent dark gradient at the horizontal edges gives depth
    // without altering the corporate blue identity.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.00; color: "#50001a4d" }
            GradientStop { position: 0.30; color: "#00003087" }
            GradientStop { position: 0.70; color: "#00003087" }
            GradientStop { position: 1.00; color: "#50001a4d" }
        }
    }

    // ── Run-start flash ──────────────────────────────────────────────────
    // Accent-coloured panel that sweeps left → right once when a run begins.
    Rectangle {
        id: runFlash
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width
        x: -parent.width          // parked off-screen left
        color: "#89b4fa"
        opacity: 0.22

        NumberAnimation {
            id: flashAnim
            target: runFlash
            property: "x"
            from: -runFlash.width
            to:    runFlash.width
            duration: 550
            easing.type: Easing.InOutCubic
        }
    }

    // ── Run-active glow overlay ──────────────────────────────────────────
    // Subtle accent tint that breathes while a run is in progress.
    Rectangle {
        id: glowOverlay
        anchors.fill: parent
        color: "#89b4fa"
        opacity: 0

        SequentialAnimation {
            id: glowAnim
            loops: Animation.Infinite
            NumberAnimation {
                target: glowOverlay; property: "opacity"
                from: 0.04; to: 0.14
                duration: 700; easing.type: Easing.InOutSine
            }
            NumberAnimation {
                target: glowOverlay; property: "opacity"
                from: 0.14; to: 0.04
                duration: 700; easing.type: Easing.InOutSine
            }
        }
    }

    // ── Run-active indicator ─────────────────────────────────────────────
    // Fades in while a run is in progress; invisible at rest.
    Text {
        id: runLabel
        anchors {
            right: parent.right
            rightMargin: 14
            verticalCenter: parent.verticalCenter
        }
        text: "● RUNNING"
        color: "#89b4fa"
        font.family: "Segoe UI"
        font.pixelSize: 11
        font.letterSpacing: 1
        opacity: 0
        Behavior on opacity { NumberAnimation { duration: 280; easing.type: Easing.InOutSine } }
    }

    // ── Central content ──────────────────────────────────────────────────
    // ORBIT360 — orange with black outline; breathes gently at rest (G).
    Text {
        id: titleText
        anchors.centerIn: parent
        text: "ORBIT360"
        color: "#ff6600"
        style: Text.Outline
        styleColor: "#000000"
        font.family: "Segoe UI"
        font.bold: true
        font.pixelSize: 30
        font.letterSpacing: 2

        // ── G: Idle micro-breathe ─────────────────────────────────────────
        SequentialAnimation {
            id: idleBreathAnim
            running: true
            loops: Animation.Infinite
            NumberAnimation {
                target: titleText; property: "opacity"
                from: 1.0; to: 0.88
                duration: 1500; easing.type: Easing.InOutSine
            }
            NumberAnimation {
                target: titleText; property: "opacity"
                from: 0.88; to: 1.0
                duration: 1500; easing.type: Easing.InOutSine
            }
        }
    }

    // ── Bottom pulse strip ───────────────────────────────────────────────
    // Mirrors the legacy 3px #89b4fa strip; now animated in pure QML.
    Rectangle {
        id: pulseStrip
        anchors {
            bottom: parent.bottom
            left:   parent.left
            right:  parent.right
        }
        height: 3
        color: "#89b4fa"
        opacity: 0

        SequentialAnimation {
            id: stripAnim
            loops: Animation.Infinite
            NumberAnimation {
                target: pulseStrip; property: "opacity"
                from: 0.15; to: 1.0
                duration: 700; easing.type: Easing.InOutSine
            }
            NumberAnimation {
                target: pulseStrip; property: "opacity"
                from: 1.0; to: 0.15
                duration: 700; easing.type: Easing.InOutSine
            }
        }
    }

    // ── F: Run-end cooldown animations ───────────────────────────────────
    // Glow and strip fade out gracefully rather than snapping to 0.
    NumberAnimation {
        id: glowFadeOut
        target: glowOverlay; property: "opacity"
        to: 0; duration: 400; easing.type: Easing.OutCubic
    }
    NumberAnimation {
        id: stripFadeOut
        target: pulseStrip; property: "opacity"
        to: 0; duration: 400; easing.type: Easing.OutCubic
    }

    // ── Run-state controller ─────────────────────────────────────────────
    Connections {
        target: titleBridge

        function onRunActiveChanged(active) {
            if (active) {
                idleBreathAnim.stop()
                titleText.opacity = 1
                flashAnim.start()
                glowAnim.start()
                stripAnim.start()
                runLabel.opacity = 1
            } else {
                flashAnim.stop()
                glowAnim.stop()
                stripAnim.stop()
                runFlash.x       = -root.width
                runLabel.opacity = 0
                glowFadeOut.start()
                stripFadeOut.start()
                idleBreathAnim.start()
            }
        }
    }
}
