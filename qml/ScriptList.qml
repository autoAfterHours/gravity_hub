// ScriptList.qml — Orbit360 v4.0
// Catppuccin Mocha styled script list. Embedded via QQuickWidget in main_window.py.
//
// Context properties required (set on QQuickWidget.rootContext()):
//   scriptModel     : TestScriptModel  — roles: name, scriptStatus, scriptDuration, scriptTags, scriptHistory
//   selectionBridge : SelectionBridge  — QObject bridge for selection events
//   tagsBridge      : TagsBridge       — QObject; tagsBridge.tags is a QVariantList of tag strings

import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    color: "#181825"
    border.color: "#313244"
    border.width: 1
    radius: 5

    // Active tag filter — JS array of selected tag strings.
    // Cleared when the model is replaced.
    property var selectedTags: []

    // Returns true if the script's tag list overlaps the selected tags.
    function hasMatchingTag(scriptTagsRaw, selTags) {
        var scriptTags = scriptTagsRaw || []
        for (var i = 0; i < selTags.length; i++) {
            for (var j = 0; j < scriptTags.length; j++) {
                if (scriptTags[j] === selTags[i]) return true
            }
        }
        return false
    }

    // ── Filter bar ────────────────────────────────────────────────────────
    Rectangle {
        id: filterBar
        anchors {
            top:   parent.top
            left:  parent.left
            right: parent.right
            margins: 6
        }
        height: listView.count > 0 ? 26 : 0
        visible: height > 0
        Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

        color: "#1e1e2e"
        border.color: filterInput.activeFocus ? "#89b4fa" : "#313244"
        border.width: 1
        radius: 4
        Behavior on border.color { ColorAnimation { duration: 120 } }

        Text {
            anchors { verticalCenter: parent.verticalCenter; left: parent.left; leftMargin: 7 }
            text: "⌕"
            color: "#585b70"
            font.pixelSize: 13
        }

        TextInput {
            id: filterInput
            anchors {
                verticalCenter: parent.verticalCenter
                left: parent.left; leftMargin: 22
                right: clearBtn.left; rightMargin: 4
            }
            color: "#cdd6f4"
            selectionColor: "#45475a"
            font.family: "Segoe UI"
            font.pixelSize: 12
            clip: true

            // Placeholder — TextInput has no placeholderText in Qt < 6.7
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "Filter scripts…"
                color: "#45475a"
                font: parent.font
                visible: parent.text === "" && !parent.activeFocus
            }

            Connections {
                target: scriptModel
                function onModelReset() {
                    filterInput.text = ""
                    root.selectedTags = []
                }
            }
        }

        Text {
            id: clearBtn
            anchors { verticalCenter: parent.verticalCenter; right: parent.right; rightMargin: 7 }
            text: "×"
            color: clearBtnArea.containsMouse ? "#cdd6f4" : "#585b70"
            font.pixelSize: 14
            visible: filterInput.text !== ""
            Behavior on color { ColorAnimation { duration: 80 } }
            MouseArea {
                id: clearBtnArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: filterInput.text = ""
            }
        }
    }

    // ── Tag chip row ──────────────────────────────────────────────────────
    // Renders one pill per unique tag across all loaded scripts.
    // Active (selected) chips filter the list to matching scripts.
    // Text filter and tag filter combine with AND logic.
    Item {
        id: tagChipRow
        anchors {
            top:   filterBar.bottom
            left:  parent.left
            right: parent.right
            topMargin: filterBar.visible ? 4 : 0
            leftMargin: 6; rightMargin: 6
        }
        // Auto-size to the Flow's wrapped height
        height: visible ? (tagFlow.implicitHeight + 8) : 0
        visible: tagsBridge && tagsBridge.tags && tagsBridge.tags.length > 0
        clip: true
        Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

        Flow {
            id: tagFlow
            anchors { fill: parent; topMargin: 3; bottomMargin: 3 }
            spacing: 4

            Repeater {
                model: tagsBridge ? tagsBridge.tags : []
                delegate: Rectangle {
                    readonly property bool selected: root.selectedTags.indexOf(modelData) >= 0

                    height: 18
                    radius: 9
                    width: chipLabel.implicitWidth + 14

                    color:        selected ? "#89b4fa" : "transparent"
                    border.color: selected ? "#89b4fa" : "#45475a"
                    border.width: 1
                    Behavior on color        { ColorAnimation { duration: 110 } }
                    Behavior on border.color { ColorAnimation { duration: 110 } }

                    Text {
                        id: chipLabel
                        anchors.centerIn: parent
                        text: modelData
                        color: selected ? "#1e1e2e" : "#6c7086"
                        font.family: "Segoe UI"
                        font.pixelSize: 10
                        Behavior on color { ColorAnimation { duration: 110 } }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            var tags = root.selectedTags.slice()
                            var idx  = tags.indexOf(modelData)
                            if (idx >= 0) tags.splice(idx, 1)
                            else          tags.push(modelData)
                            root.selectedTags = tags
                        }
                    }
                }
            }
        }
    }

    // ── Script list ───────────────────────────────────────────────────────
    ListView {
        id: listView
        anchors {
            top: tagChipRow.visible
                 ? tagChipRow.bottom
                 : (filterBar.visible ? filterBar.bottom : parent.top)
            topMargin:    4
            left:         parent.left
            right:        parent.right
            bottom:       parent.bottom
            leftMargin:   4
            rightMargin:  4
            bottomMargin: 4
        }
        model: scriptModel
        clip: true
        focus: true
        currentIndex: -1
        spacing: 1

        add: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 150; easing.type: Easing.OutCubic }
        }

        Connections {
            target: scriptModel
            function onModelReset() {
                listView.currentIndex = -1
                selectionBridge.notifyRow(-1)
            }
        }

        // ── Delegate ─────────────────────────────────────────────────────
        delegate: Rectangle {
            id: delegateRoot
            width: listView.width

            // Capture scriptHistory so nested Repeaters can access it safely.
            // model.scriptHistory is a ListView delegate context var — it
            // cannot be accessed via delegateRoot.model (that returns undefined).
            property var _history: model.scriptHistory || []

            // Combined text + tag filter — collapses row height to 0 for non-matches.
            readonly property bool matchesFilter: {
                var textOk = filterInput.text === "" ||
                    model.name.toLowerCase().indexOf(filterInput.text.toLowerCase()) >= 0
                var tagOk  = root.selectedTags.length === 0 ||
                    root.hasMatchingTag(model.scriptTags, root.selectedTags)
                return textOk && tagOk
            }

            height:  matchesFilter ? 28 : 0
            visible: matchesFilter
            clip: true
            Behavior on height { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }

            radius: 3
            color: {
                if (ListView.isCurrentItem)  return "#45475a"
                if (hoverArea.containsMouse) return "#313244"
                return "transparent"
            }
            Behavior on color { ColorAnimation { duration: 80 } }

            // Row flash on completion
            property string trackedStatus: model.scriptStatus
            property string prevStatus: ""
            onTrackedStatusChanged: {
                var finished = (trackedStatus === "passed" || trackedStatus === "failed" || trackedStatus === "error")
                if (prevStatus === "running" && finished) {
                    rowFlash.color = statusDot.color
                    rowFlashAnim.start()
                }
                prevStatus = trackedStatus
            }
            Rectangle {
                id: rowFlash
                anchors.fill: parent; radius: parent.radius
                color: "transparent"; opacity: 0
                NumberAnimation {
                    id: rowFlashAnim; target: rowFlash; property: "opacity"
                    from: 0.2; to: 0; duration: 500; easing.type: Easing.OutCubic
                }
            }

            // ── Script name ───────────────────────────────────────────────
            Text {
                anchors {
                    verticalCenter: parent.verticalCenter
                    left: parent.left; leftMargin: 8
                    right: sparklineRow.left; rightMargin: 4
                }
                text: model.name
                color: "#cdd6f4"
                font.family: "Segoe UI"
                font.pixelSize: 12
                elide: Text.ElideRight
            }

            // ── Sparkline + flaky badge + duration + status dot ───────────
            // Right-aligned cluster: [sparkline dots] [⚡] [dur] [●]
            Row {
                id: sparklineRow
                anchors {
                    verticalCenter: parent.verticalCenter
                    right: durationLabel.left; rightMargin: 4
                }
                spacing: 2
                visible: delegateRoot._history.length > 0 && model.scriptStatus !== "running"

                // Sparkline: up to 7 dots, each 4px wide, coloured by outcome
                Repeater {
                    model: {
                        var h = delegateRoot._history
                        return h.length > 7 ? h.slice(h.length - 7) : h
                    }
                    delegate: Rectangle {
                        width: 4; height: 4; radius: 2
                        anchors.verticalCenter: parent.verticalCenter
                        color: {
                            switch (modelData) {
                                case "passed": return "#a6e3a1"
                                case "failed": return "#f38ba8"
                                default:       return "#fab387"
                            }
                        }
                        opacity: 0.75
                    }
                }

                // Flaky badge — shown when history has both passes and failures
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "~"
                    color: "#f9e2af"    // Catppuccin Yellow
                    font.pixelSize: 11
                    font.bold: true
                    visible: {
                        var h = delegateRoot._history
                        if (h.length < 3) return false
                        var hasPass = false, hasFail = false
                        for (var i = 0; i < h.length; i++) {
                            if (h[i] === "passed") hasPass = true
                            else                   hasFail = true
                        }
                        return hasPass && hasFail
                    }
                    ToolTip.visible:  hoverArea.containsMouse && visible
                    ToolTip.text:     "Flaky — mixed results in recent runs"
                    ToolTip.delay:    500
                }
            }

            // ── Duration label ────────────────────────────────────────────
            Text {
                id: durationLabel
                anchors {
                    verticalCenter: parent.verticalCenter
                    right: statusGlow.left; rightMargin: 4
                }
                text: model.scriptDuration
                color: "#585b70"
                font.family: "JetBrains Mono, Fira Code, Consolas, Courier New"
                font.pixelSize: 10
                visible: model.scriptDuration !== "" && model.scriptStatus !== "running"
                opacity: visible ? 1.0 : 0.0
                Behavior on opacity { NumberAnimation { duration: 200 } }
            }

            // ── Status glow halo ──────────────────────────────────────────
            Rectangle {
                id: statusGlow
                width: 16; height: 16; radius: 8
                anchors { right: parent.right; rightMargin: 7; verticalCenter: parent.verticalCenter }
                color: statusDot.color
                opacity: model.scriptStatus !== "" ? 0.28 : 0
                Behavior on opacity { NumberAnimation { duration: 250 } }
                Behavior on color   { ColorAnimation  { duration: 200 } }
            }

            // ── Status dot ────────────────────────────────────────────────
            Rectangle {
                id: statusDot
                width: 8; height: 8; radius: 4
                anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                visible: model.scriptStatus !== ""
                scale: 1.0
                color: {
                    switch (model.scriptStatus) {
                        case "running": return "#89b4fa"
                        case "passed":  return "#a6e3a1"
                        case "failed":  return "#f38ba8"
                        case "error":   return "#fab387"
                        default:        return "#45475a"
                    }
                }
                Behavior on color { ColorAnimation { duration: 200 } }

                NumberAnimation {
                    id: dotPopAnim; target: statusDot; property: "scale"
                    from: 1.4; to: 1.0; duration: 200; easing.type: Easing.OutBack
                }
                onVisibleChanged: { if (visible) dotPopAnim.start() }

                SequentialAnimation {
                    id: pulseAnim
                    running: model.scriptStatus === "running"
                    loops: Animation.Infinite
                    onStopped: statusDot.opacity = 1.0
                    NumberAnimation { target: statusDot; property: "opacity"; to: 0.15; duration: 550; easing.type: Easing.InOutSine }
                    NumberAnimation { target: statusDot; property: "opacity"; to: 1.0;  duration: 550; easing.type: Easing.InOutSine }
                }
            }

            MouseArea {
                id: hoverArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: {
                    listView.currentIndex = index
                    selectionBridge.notifyRow(index)
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
            background: Rectangle { color: "transparent" }
        }
    }

    // ── Empty state ───────────────────────────────────────────────────────
    Text {
        anchors.centerIn: parent
        text: "Select a test set to load scripts"
        color: "#6c7086"
        font.family: "Segoe UI"
        font.pixelSize: 12
        visible: listView.count === 0
    }
}
