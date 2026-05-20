// DropdownCascade.qml — Orbit360 v4.0
//
// Catppuccin Mocha styled hierarchy cascade.
// All levels for the current system are shown side-by-side at equal widths
// as soon as the system is selected.  Levels that have no options yet are
// dimmed (opacity 0.35) and their combo is disabled.  No visibility-change
// layout tricks — widths are stable once the system loads.
//
// Context properties:
//   cascadeModel  : CascadeModel  — QAbstractListModel (label / options / selectedIndex)
//   cascadeBridge : CascadeBridge — QObject bridge for user selections

import QtQuick
import QtQuick.Controls

Item {
    id: root

    // ── Background ────────────────────────────────────────────────────────
    Rectangle {
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: 60
        color: "#1e1e2e"
    }

    // ── Horizontal cascade ────────────────────────────────────────────────
    Row {
        id: mainRow
        spacing: 8
        anchors {
            left:  parent.left
            right: parent.right
            top:   parent.top
        }

        Repeater {
            id: levelRepeater
            model: cascadeModel

            delegate: Column {
                id: levelCol
                spacing: 4

                // Capture model roles
                property string rowLabel:    model.label
                property var    rowOptions:  model.options
                property int    rowSelected: model.selectedIndex
                property int    rowIdx:      index

                property bool hasOptions: rowOptions.length > 1

                // Always visible — width is a fixed equal share of the row.
                // Levels without options yet are dimmed instead of hidden so
                // the layout never reshuffles and no RowLayout/visible-change
                // bug can affect width distribution.
                visible: true
                width: levelRepeater.count > 0
                       ? (mainRow.width - (levelRepeater.count - 1) * mainRow.spacing) / levelRepeater.count
                       : 0

                // I: Fade in from dim when options arrive. Keep dim levels
                // legible so the row reads as four deliberate columns instead
                // of one combo with empty space next to it.
                opacity: hasOptions ? 1.0 : 0.55
                Behavior on opacity {
                    NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
                }

                // Python → QML sync: when selectedIndex changes, update combo
                onRowSelectedChanged: {
                    if (levelCombo.currentIndex !== rowSelected) {
                        levelCombo.currentIndex = rowSelected
                    }
                }

                // ── Label ────────────────────────────────────────────────
                Text {
                    width:  parent.width
                    height: 16
                    text:   levelCol.rowLabel
                    color:  "#a6adc8"
                    font.family:    "Segoe UI"
                    font.pixelSize: 11
                    verticalAlignment: Text.AlignVCenter
                    clip: true
                }

                // ── Combo box ────────────────────────────────────────────
                ComboBox {
                    id:      levelCombo
                    width:   parent.width
                    height:  32
                    model:   levelCol.rowOptions
                    enabled: levelCol.hasOptions

                    Component.onCompleted: currentIndex = levelCol.rowSelected

                    // onActivated fires ONLY on user interaction, not on
                    // programmatic currentIndex changes — no feedback loop.
                    onActivated: (idx) => {
                        cascadeBridge.selectLevel(levelCol.rowIdx, idx)
                    }

                    // ── Content ──────────────────────────────────────────
                    contentItem: Text {
                        leftPadding:  10
                        rightPadding: levelCombo.indicator.width + 6
                        // Show an em-dash placeholder when the level has no
                        // options yet so the column doesn't look like an
                        // empty void next to a populated combo.
                        text:  levelCombo.enabled ? levelCombo.displayText : "—"
                        color: levelCombo.enabled ? "#cdd6f4" : "#6c7086"
                        font.family:    "Segoe UI"
                        font.pixelSize: 13
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }

                    // ── Background ───────────────────────────────────────
                    background: Rectangle {
                        color: !levelCombo.enabled  ? "#1e1e2e"
                             : levelCombo.pressed   ? "#45475a"
                             : levelCombo.hovered   ? "#3d3f52"
                             : "#313244"
                        radius: 6
                        border.color: levelCombo.hovered && levelCombo.enabled ? "#89b4fa" : "#45475a"
                        border.width: 1
                        Behavior on color        { ColorAnimation { duration: 80 } }
                        Behavior on border.color { ColorAnimation { duration: 80 } }
                    }

                    // ── Dropdown arrow ───────────────────────────────────
                    // H: rotates 180° when popup is open.
                    indicator: Canvas {
                        x: levelCombo.width - width - 10
                        y: (levelCombo.height - height) / 2
                        width: 10; height: 6
                        transformOrigin: Item.Center
                        rotation: levelCombo.popup.visible ? 180 : 0
                        Behavior on rotation {
                            NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
                        }

                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.reset()
                            ctx.strokeStyle = levelCombo.enabled ? "#6c7086" : "#3d3f52"
                            ctx.lineWidth   = 1.5
                            ctx.lineJoin    = "round"
                            ctx.beginPath()
                            ctx.moveTo(0, 0)
                            ctx.lineTo(width / 2, height)
                            ctx.lineTo(width, 0)
                            ctx.stroke()
                        }
                    }

                    // ── Popup ────────────────────────────────────────────
                    popup: Popup {
                        id: levelPopup
                        y:       parent.height + 2
                        width:   levelCombo.width
                        padding: 4

                        onOpened: cascadeBridge.notifyPopupOpened(levelPopup.implicitHeight)
                        onClosed: cascadeBridge.notifyPopupClosed()

                        // J: fade + 4px drop on open
                        enter: Transition {
                            ParallelAnimation {
                                NumberAnimation {
                                    property: "opacity"
                                    from: 0; to: 1
                                    duration: 120; easing.type: Easing.OutCubic
                                }
                                NumberAnimation {
                                    property: "y"
                                    from: -4; to: 0
                                    duration: 120; easing.type: Easing.OutCubic
                                }
                            }
                        }
                        exit: Transition {
                            NumberAnimation {
                                property: "opacity"
                                from: 1; to: 0
                                duration: 80
                            }
                        }

                        background: Rectangle {
                            color:  "#1e1e2e"
                            radius: 8
                            border.color: "#45475a"
                            border.width: 1
                        }

                        contentItem: ListView {
                            clip:           true
                            model:          levelCombo.delegateModel
                            implicitHeight: Math.min(contentHeight, 200)
                            currentIndex:   levelCombo.highlightedIndex

                            ScrollBar.vertical: ScrollBar {
                                contentItem: Rectangle {
                                    implicitWidth: 4
                                    radius: 2
                                    color:  "#45475a"
                                }
                                background: Rectangle { color: "transparent" }
                            }
                        }
                    }

                    // ── Item delegate ────────────────────────────────────
                    delegate: ItemDelegate {
                        width:   levelCombo.width - 8
                        height:  28
                        padding: 0

                        contentItem: Text {
                            leftPadding: 10
                            text:  modelData
                            color: "#cdd6f4"
                            font.family:    "Segoe UI"
                            font.pixelSize: 13
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }

                        background: Rectangle {
                            radius: 5
                            color: highlighted ? "#45475a" : "transparent"
                            Behavior on color { ColorAnimation { duration: 60 } }
                        }

                        highlighted: levelCombo.highlightedIndex === index
                    }
                }
            }
        }
    }
}
