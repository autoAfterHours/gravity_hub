// LogConsole.qml — Orbit360 v4.0
// Catppuccin Mocha colored log viewer backed by LogEntryModel.
//
// Context properties required (set on QQuickWidget.rootContext()):
//   logModel  : LogEntryModel — roles: entryText/entryColor/entryTimestamp/entryHighlighted
//   logBridge : LogBridge     — copyText(str), setSearchText(str), matchCount, searchOpened signal

import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    color: "#1e1e2e"
    border.color: "#45475a"
    border.width: 1
    radius: 5

    // ── Search bar (slides in on Ctrl+F / logBridge.searchOpened) ─────────
    Rectangle {
        id: searchBar
        anchors {
            top:         parent.top
            left:        parent.left
            right:       parent.right
            topMargin:   height > 0 ? 6 : 0
            leftMargin:  6
            rightMargin: 6
        }
        height:  _open ? 34 : 0
        clip:    true
        radius:  4
        color:   "#252536"
        border.color: "#45475a"
        border.width: 1
        property bool _open: false

        Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

        function open() {
            _open = true
            searchField.forceActiveFocus()
        }
        function close() {
            _open = false
            searchField.text = ""
            logBridge.setSearchText("")
        }

        Row {
            anchors {
                verticalCenter: parent.verticalCenter
                left:  parent.left;  leftMargin:  10
                right: parent.right; rightMargin: 8
            }
            spacing: 8
            visible: searchBar._open

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "⌕"; color: "#585b70"; font.pixelSize: 14
            }

            TextField {
                id: searchField
                width: parent.width - matchLabel.implicitWidth - 40
                color: "#cdd6f4"
                placeholderText: "Search log…"
                placeholderTextColor: "#45475a"
                font.family: "JetBrains Mono, Fira Code, Cascadia Code, Consolas, Courier New"
                font.pixelSize: 12
                background: Rectangle { color: "transparent" }
                leftPadding: 0; rightPadding: 0; topPadding: 0; bottomPadding: 0
                Keys.onEscapePressed: searchBar.close()
                onTextChanged: logBridge.setSearchText(text)
            }

            Text {
                id: matchLabel
                anchors.verticalCenter: parent.verticalCenter
                text: searchField.text !== ""
                      ? (logBridge ? logBridge.matchCount : 0) + " match" + ((logBridge ? logBridge.matchCount : 0) !== 1 ? "es" : "")
                      : ""
                color: (logBridge && logBridge.matchCount > 0) ? "#a6e3a1" : "#f38ba8"
                font.pixelSize: 10
                font.family: "JetBrains Mono, Fira Code, Cascadia Code, Consolas, Courier New"
                visible: searchField.text !== ""
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "✕"
                color: xArea.containsMouse ? "#cdd6f4" : "#585b70"
                font.pixelSize: 12
                Behavior on color { ColorAnimation { duration: 80 } }
                MouseArea {
                    id: xArea
                    anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: searchBar.close()
                }
            }
        }
    }

    Connections {
        target: logBridge
        function onSearchOpened() { searchBar.open() }
    }

    // ── Log list ──────────────────────────────────────────────────────────
    ListView {
        id: logView
        anchors {
            top:          searchBar.bottom
            topMargin:    8
            left:         parent.left;   leftMargin:   8
            right:        parent.right;  rightMargin:  8
            bottom:       parent.bottom; bottomMargin: 8
        }
        model: logModel
        clip: true
        spacing: 1

        // Auto-scroll: lock to bottom as new entries arrive.
        // Unlocks when the user scrolls up; re-locks when they reach the bottom
        // (unless _pinned is true — see the lock button below).
        property bool _userScrolled: false

        // When _pinned is true the user has explicitly requested that auto-scroll
        // NOT re-engage even after scrolling back to the bottom.  The lock button
        // in the top-right corner toggles this.  Clicking it also jumps to the
        // bottom and clears the scroll-detached state.
        property bool _pinned: false

        onCountChanged: {
            if (!_userScrolled) {
                Qt.callLater(positionViewAtEnd)
            }
        }

        onMovementStarted: {
            if (!atYEnd) {
                _userScrolled = true
            }
        }

        onAtYEndChanged: {
            if (atYEnd && !_pinned) {
                _userScrolled = false
            }
        }

        // ── A: Enhanced row entrance — fade + 6px slide from right ────────
        add: Transition {
            ParallelAnimation {
                NumberAnimation {
                    property: "opacity"
                    from: 0; to: 1
                    duration: 180
                    easing.type: Easing.OutCubic
                }
                NumberAnimation {
                    property: "x"
                    from: 6; to: 0
                    duration: 180
                    easing.type: Easing.OutCubic
                }
            }
        }

        // ── Delegate ──────────────────────────────────────────────────────
        delegate: Rectangle {
            id: row
            width: logView.width

            // Section breaks (─── TITLE ───) get extra height and bold text.
            readonly property bool isSectionBreak: model.entryText.startsWith("─")
            readonly property bool isMilestone: isSectionBreak || model.entryColor === "#89b4fa"
            height: isSectionBreak
                    ? 30
                    : Math.max(22, entryLabel.implicitHeight + 4)

            // Search highlight (amber tint) > hover > transparent
            color: {
                if (model.entryHighlighted) return "#2a2a1a"
                if (hoverArea.containsMouse) return "#313244"
                return "transparent"
            }
            Behavior on color { ColorAnimation { duration: 60 } }

            // Left accent stripe for search matches
            Rectangle {
                width:  model.entryHighlighted ? 2 : 0
                height: parent.height
                color:  "#f9e2af"
                Behavior on width { NumberAnimation { duration: 100 } }
            }

            Row {
                anchors {
                    verticalCenter: parent.verticalCenter
                    left:  parent.left; leftMargin: model.entryHighlighted ? 6 : 4
                    right: parent.right
                }
                spacing: 2

                // ── Timestamp column ─────────────────────────────────────
                Text {
                    width: 80
                    height: row.height
                    text: model.entryTimestamp
                    color: "#585b70"
                    font.family: "JetBrains Mono, Fira Code, Cascadia Code, Consolas, Courier New"
                    font.pixelSize: 11
                    verticalAlignment: Text.AlignVCenter
                }

                // ── Log text ─────────────────────────────────────────────
                Text {
                    id: entryLabel
                    width: row.width - 82   // 80 timestamp + 2 spacing
                    text: model.entryText
                    color: model.entryColor
                    font.family: "JetBrains Mono, Fira Code, Cascadia Code, Consolas, Courier New"
                    font.pixelSize: 12
                    font.bold: row.isSectionBreak
                    wrapMode: Text.WrapAnywhere
                    renderType: Text.NativeRendering
                    verticalAlignment: Text.AlignVCenter
                }
            }

            // ── C: Milestone flash overlay ────────────────────────────────
            // Blue pulse on section breaks and blue milestone rows.
            Rectangle {
                id: milestoneFlash
                anchors.fill: parent
                radius: parent.radius
                color: "#89b4fa"
                opacity: 0

                NumberAnimation {
                    id: milestoneFlashAnim
                    target: milestoneFlash; property: "opacity"
                    from: 0.25; to: 0
                    duration: 600; easing.type: Easing.OutCubic
                }
            }

            // ── E: Copy flash overlay ─────────────────────────────────────
            // Shutter-style: bright snap → hold → fade out.
            Rectangle {
                id: copyFlashOverlay
                anchors.fill: parent
                radius: parent.radius
                color: "#89b4fa"
                opacity: 0

                SequentialAnimation {
                    id: copyFlashAnim
                    NumberAnimation {
                        target: copyFlashOverlay; property: "opacity"
                        to: 0.30; duration: 60
                    }
                    PauseAnimation { duration: 200 }
                    NumberAnimation {
                        target: copyFlashOverlay; property: "opacity"
                        to: 0; duration: 180
                        easing.type: Easing.OutCubic
                    }
                }
            }

            // ── B: Section break text draw animation ──────────────────────
            NumberAnimation {
                id: sectionFadeAnim
                target: entryLabel; property: "opacity"
                from: 0.3; to: 1.0
                duration: 400; easing.type: Easing.OutCubic
            }

            MouseArea {
                id: hoverArea
                anchors.fill: parent
                hoverEnabled: true
                onDoubleClicked: {
                    logBridge.copyText(model.entryText)
                    copyFlashAnim.start()
                }
            }

            // Trigger B and C on row creation
            Component.onCompleted: {
                if (isSectionBreak) {
                    entryLabel.opacity = 0.3
                    sectionFadeAnim.start()
                }
                if (isMilestone) {
                    milestoneFlashAnim.start()
                }
            }
        }

        // ── Scrollbar ─────────────────────────────────────────────────────
        ScrollBar.vertical: ScrollBar {
            id: vBar
            policy: ScrollBar.AsNeeded

            contentItem: Rectangle {
                implicitWidth: vBar.hovered ? 8 : 6
                implicitHeight: 30
                radius: 3
                color: vBar.pressed ? "#585b70" : "#45475a"
                opacity: vBar.active ? 1.0 : 0.0
                Behavior on implicitWidth { NumberAnimation { duration: 120 } }
                Behavior on opacity      { NumberAnimation { duration: 150 } }
            }

            background: Rectangle {
                color: "transparent"
            }
        }
    }

    // ── F: Scroll-lock toggle ─────────────────────────────────────────────
    // Shown in the top-right whenever the user has scrolled away from the
    // live tail.  Click once to pin the view (prevents re-engagement even
    // when scrolling back to the bottom).  Click again to unpin and jump
    // back to the latest entry.
    Rectangle {
        id: lockBtn
        anchors {
            top:         parent.top
            right:       parent.right
            topMargin:   8
            rightMargin: 16
        }
        width: 22; height: 22; radius: 11

        // Visible whenever the user is detached OR pinned
        opacity: (logView._userScrolled || logView._pinned) ? 1.0 : 0.0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 150 } }

        color: logView._pinned
               ? "#313244"
               : (lockBtnArea.containsMouse ? "#313244" : "transparent")
        border.color: logView._pinned ? "#89b4fa" : "#585b70"
        border.width: 1
        Behavior on color        { ColorAnimation { duration: 80 } }
        Behavior on border.color { ColorAnimation { duration: 80 } }

        // Spring pop on appearance
        property bool _bounced: false
        onOpacityChanged: {
            if (opacity > 0 && !_bounced) {
                _bounced = true
                lockBtnBounce.start()
            } else if (opacity === 0) {
                _bounced = false
            }
        }
        NumberAnimation {
            id: lockBtnBounce
            target: lockBtn; property: "scale"
            from: 1.2; to: 1.0
            duration: 200; easing.type: Easing.OutBack
        }

        Text {
            anchors.centerIn: parent
            text: logView._pinned ? "🔒" : "🔓"
            font.pixelSize: 11
        }

        ToolTip.visible: lockBtnArea.containsMouse
        ToolTip.text:    logView._pinned
                         ? "Pinned — click to unpin and jump to latest"
                         : "Pin scroll position (stop auto-scroll)"
        ToolTip.delay: 600

        MouseArea {
            id: lockBtnArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                if (logView._pinned) {
                    // Unpin: re-engage auto-scroll and jump to bottom
                    logView._pinned      = false
                    logView._userScrolled = false
                    logView.positionViewAtEnd()
                } else {
                    // Pin: freeze the current view position
                    logView._pinned = true
                }
            }
        }
    }

    // ── D: Jump-to-bottom button ──────────────────────────────────────────
    // Appears when the user has scrolled up; bounces in with a spring pop.
    Rectangle {
        id: jumpBtn
        anchors {
            right:  parent.right
            bottom: parent.bottom
            rightMargin:  16
            bottomMargin: 16
        }
        width: 28; height: 28; radius: 14
        color: jumpArea.containsMouse ? "#45475a" : "#313244"
        border.color: "#585b70"
        border.width: 1
        visible: opacity > 0
        opacity: logView._userScrolled ? 1.0 : 0.0
        scale: 1.0

        Behavior on opacity { NumberAnimation { duration: 150 } }
        Behavior on color   { ColorAnimation  { duration:  60 } }

        // Spring bounce on each appearance
        property bool _bounced: false
        onOpacityChanged: {
            if (opacity > 0 && !_bounced) {
                _bounced = true
                bounceShrink.start()
            } else if (opacity === 0) {
                _bounced = false
            }
        }

        NumberAnimation {
            id: bounceShrink
            target: jumpBtn; property: "scale"
            from: 1.2; to: 1.0
            duration: 200; easing.type: Easing.OutBack
        }

        Text {
            anchors.centerIn: parent
            text: "↓"
            color: "#89b4fa"
            font.pixelSize: 14
            font.family: "Segoe UI"
        }

        MouseArea {
            id: jumpArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                logView._pinned       = false
                logView._userScrolled = false
                logView.positionViewAtEnd()
            }
        }
    }

    // ── Empty / placeholder state ─────────────────────────────────────────
    Text {
        anchors.centerIn: parent
        text: "Select a test set and click Run to begin..."
        color: "#45475a"
        font.family: "Segoe UI"
        font.pixelSize: 12
        visible: logView.count === 0
    }
}
