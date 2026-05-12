import QtQuick
import QtQuick.Effects

Item {
    id: window
    // Size-agnostic root; will be sized by QQuickWidget
    width: isMini ? 85 : 240
    height: isMini ? 44 : 160

    // Self-sensing responsive property
    readonly property bool isMini: width < 150

    component GlowingItem : Item {
        id: root
        property string sourceSvg
        property real brightnessAmount: 0.0
        property real glowScale: 0.2
        property real glowOpacityMult: 1.0
        property real itemBlur: 0.0
        property real sweepPosition: -2.5
        property real baseScaleX: 1.0
        property real baseScaleY: 1.0
        property real baseRotation: 0.0
        property real translateX: 0.0
        property real translateY: 0.0

        layer.enabled: true
        layer.smooth: true
        layer.mipmap: true
        antialiasing: true

        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: "#000000"
            shadowOpacity: isMini ? 0.3 : 0.5 
            shadowBlur: isMini ? 0.4 : 0.7
            blurMax: 32
            shadowHorizontalOffset: isMini ? 1 : 8
            shadowVerticalOffset: isMini ? 2 : 12
            autoPaddingEnabled: true
        }

        Item {
            id: transformWrapper
            anchors.fill: parent
            antialiasing: true
            transform: [
                Translate { x: root.translateX; y: root.translateY },
                Scale { 
                    xScale: root.baseScaleX; yScale: root.baseScaleY 
                    origin.x: width / 2; origin.y: height / 2 
                },
                Rotation { 
                    angle: root.baseRotation 
                    origin.x: width / 2; origin.y: height / 2 
                }
            ]

            Image {
                id: src
                source: root.sourceSvg
                anchors.fill: parent
                visible: false
                mipmap: true
                smooth: true
                antialiasing: true
                // High-resolution oversampling for smoothness
                sourceSize: Qt.size(width * 4, height * 4) 
            }

            MultiEffect {
                anchors.fill: src
                source: src
                brightness: root.brightnessAmount
                blur: root.itemBlur
                blurMax: 32
                shadowEnabled: true
                shadowColor: "#FF8A00"
                shadowOpacity: root.glowOpacityMult * (root.glowScale * (isMini ? 0.8 : 1.2) + (isMini ? 0.2 : 0.3))
                shadowBlur: root.glowScale * (isMini ? 0.5 : 1.2) + (isMini ? 0.1 : 0.4)
                autoPaddingEnabled: true 
            }

            MultiEffect {
                anchors.fill: src
                source: sweepContainer
                maskEnabled: true
                maskSource: src
                opacity: (root.sweepPosition > -2.5 && root.sweepPosition < 2.5) ? 1.0 : 0.0
            }

            Item {
                id: sweepContainer
                anchors.fill: parent
                visible: false
                Rectangle {
                    width: parent.width * 2.0
                    height: parent.height * 2.0
                    y: -parent.height * 0.5
                    x: root.sweepPosition * parent.width
                    rotation: 15
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "#00FF8A00" }
                        GradientStop { position: 0.45; color: "#88FF8A00" }
                        GradientStop { position: 0.5; color: "#FFFFFFFF" }
                        GradientStop { position: 0.55; color: "#88FF8A00" }
                        GradientStop { position: 1.0; color: "#00FF8A00" }
                    }
                }
            }
        }
    }

    // Centered Master Container
    Item {
        id: logoCanvas
        width: 512; height: 512
        
        // SCALING:
        // Mini (Sidebar/Hub): 0.12 gives a perfect icon size (~31px content)
        // Splash: 0.28 balances size and impact (was 0.423, way too big)
        scale: isMini ? 0.12 : 0.28
        
        transformOrigin: Item.Center
        anchors.centerIn: parent
        
        // POSITIONING NUDGES:
        // Sidebar/Hub: +14px Right to compensate for the skew visual shift
        // About (Width 200): +18px Right
        // Splash (Width 240): +30px Right (Perfectly centers the skewed mark in the larger layout)
        anchors.horizontalCenterOffset: isMini ? 14 : (window.width > 220 ? 30 : 18)
        anchors.verticalCenterOffset: isMini ? 0 : -25

        Item {
            anchors.fill: parent
            transform: [
                Translate { x: 256; y: 256 },
                Scale { xScale: 1.05; yScale: 1.05 },
                Matrix4x4 {
                    matrix: Qt.matrix4x4(
                        1, Math.tan(-15 * Math.PI / 180), 0, 0,
                        0, 1, 0, 0,
                        0, 0, 1, 0,
                        0, 0, 0, 1
                    )
                },
                Translate { x: -256; y: -256 }
            ]

            GlowingItem {
                id: rightPillar
                z: 1
                x: 308; y: 126; width: 64; height: 260
                sourceSvg: "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NCAyNjAiPjxkZWZzPjxsaW5lYXJHcmFkaWVudCBpZD0iZ3JhZCIgeDE9IjAlIiB5MT0iMCUiIHgyPSIwJSIgeTI9IjEwMCUiPjxzdG9wIG9mZnNldD0iMCUiIHN0b3AtY29sb3I9IiNGRjhBMDAiLz48c3RvcCBvZmZzZXQ9IjEwMCUiIHN0b3AtY29sb3I9IiNFNTJFMDAiLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48cmVjdCB3aWR0aD0iNjQiIGhlaWdodD0iMjYwIiByeD0iMzIiIGZpbGw9InVybCgjZ3JhZCkiLz48L3N2Zz4="
            }

            GlowingItem {
                id: playTriangle
                z: 2
                x: 178; y: 174; width: 164; height: 164
                sourceSvg: "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNjQgMTY0Ij48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9InBsYXlHcmFkMiIgeDE9IjAlIiB5MT0iMCUiIHgyPSIxMDAlIiB5Mj0iMTAwJSI+PHN0b3Agb2Zmc2V0PSIwJSIgc3RvcC1jb2xvcj0iIzJEMkQyRCIvPjxzdG9wIG9mZnNldD0iMTAwJSIgc3RvcC1jb2xvcj0iIzBBMEEwQSIvPjwvbGluZWFyR3JhZGllbnQ+PGxpbmVhckdyYWRpZW50IGlkPSJwaWxsYXJHcmFkMiIgeDE9IjAlIiB5MT0iMCUiIHgyPSIwJSIgeTI9IjEwMCUiPjxzdG9wIG9mZnNldD0iMCUiIHN0b3AtY29sb3I9IiNGRjhBMDAiLz48c3RvcCBvZmZzZXQ9IjEwMCUiIHN0b3AtY29sb3I9IiNFNTJFMDAiLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48cGF0aCBkPSJNIDEyIDMyIEwgMTUyIDgyIEwgMTIgMTMyIFoiIGZpbGw9InVybCgjcGxheUdyYWQyKSIgc3Ryb2tlPSJ1cmwoI3BpbGxhckdyYWQyKSIgc3Ryb2tlLXdpZHRoPSIyNCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPjwvc3ZnPg=="
            }

            GlowingItem {
                id: leftPillar
                z: 3
                x: 140; y: 126; width: 64; height: 260
                sourceSvg: "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NCAyNjAiPjxkZWZzPjxsaW5lYXJHcmFkaWVudCBpZD0iZ3JhZCIgeDE9IjAlIiB5MT0iMCUiIHgyPSIwJSIgeTI9IjEwMCUiPjxzdG9wIG9mZnNldD0iMCUiIHN0b3AtY29sb3I9IiNGRjhBMDAiLz48c3RvcCBvZmZzZXQ9IjEwMCUiIHN0b3AtY29sb3I9IiNFNTJFMDAiLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48cmVjdCB3aWR0aD0iNjQiIGhlaWdodD0iMjYwIiByeD0iMzIiIGZpbGw9InVybCgjZ3JhZCkiLz48L3N2Zz4="
            }
        }
    }

    signal logoClicked()

    function resetToIdle() {
        [leftPillar, rightPillar, playTriangle].forEach(function(item) {
            item.opacity = 1; item.brightnessAmount = 0; item.glowScale = 0.2; item.glowOpacityMult = 1.0;
            item.itemBlur = 0.0; item.sweepPosition = -2.5;
            item.translateX = 0; item.translateY = 0; item.baseScaleX = 1; item.baseScaleY = 1; item.baseRotation = 0;
        });
    }

    function startFlow(flowName) {
        flowA_Sequence.stop();
        flowB_Sequence.stop();
        flowC_Loop.stop();
        resetToIdle();
        
        if (flowName === "A") flowA_Sequence.start();
        else if (flowName === "B") flowB_Sequence.start();
        else if (flowName === "C") flowC_Loop.start();
    }

    MouseArea {
        anchors.fill: parent
        onClicked: window.logoClicked()
    }

    // --- FLOW B: Kinetic Tension -> Breathing Reactor ---
    SequentialAnimation {
        id: flowB_Sequence
        
        // 1. Entrance: Kinetic Tension
        ParallelAnimation {
            ParallelAnimation {
                NumberAnimation { target: leftPillar; property: "translateX"; from: 40; to: 0; duration: 1000; easing.type: Easing.BezierSpline; easing.bezierCurve: [0.5, -0.5, 0.5, 1.5, 1, 1] }
                NumberAnimation { target: leftPillar; property: "baseScaleY"; from: 0.8; to: 1.0; duration: 1000; easing.type: Easing.BezierSpline; easing.bezierCurve: [0.5, -0.5, 0.5, 1.5, 1, 1] }
                NumberAnimation { target: leftPillar; property: "opacity"; from: 0; to: 1; duration: 500 }
            }
            ParallelAnimation {
                NumberAnimation { target: rightPillar; property: "translateX"; from: -40; to: 0; duration: 1000; easing.type: Easing.BezierSpline; easing.bezierCurve: [0.5, -0.5, 0.5, 1.5, 1, 1] }
                NumberAnimation { target: rightPillar; property: "baseScaleY"; from: 0.8; to: 1.0; duration: 1000; easing.type: Easing.BezierSpline; easing.bezierCurve: [0.5, -0.5, 0.5, 1.5, 1, 1] }
                NumberAnimation { target: rightPillar; property: "opacity"; from: 0; to: 1; duration: 500 }
            }
            SequentialAnimation {
                PauseAnimation { duration: 400 }
                ParallelAnimation {
                    NumberAnimation { target: playTriangle; property: "baseScaleX"; from: 0; to: 1; duration: 800; easing.type: Easing.BezierSpline; easing.bezierCurve: [0.175, 0.885, 0.32, 1.275, 1, 1] }
                    NumberAnimation { target: playTriangle; property: "baseScaleY"; from: 0; to: 1; duration: 800; easing.type: Easing.BezierSpline; easing.bezierCurve: [0.175, 0.885, 0.32, 1.275, 1, 1] }
                    NumberAnimation { target: playTriangle; property: "baseRotation"; from: 180; to: 0; duration: 800; easing.type: Easing.BezierSpline; easing.bezierCurve: [0.175, 0.885, 0.32, 1.275, 1, 1] }
                    NumberAnimation { target: playTriangle; property: "itemBlur"; from: 1.0; to: 0.0; duration: 800; easing.type: Easing.OutQuad }
                    NumberAnimation { target: playTriangle; property: "opacity"; from: 0; to: 1; duration: 400 }
                }
            }
        }
        
        // 2. Loop: Breathing Reactor
        ParallelAnimation {
            loops: Animation.Infinite
            SequentialAnimation {
                ParallelAnimation { NumberAnimation { target: playTriangle; property: "brightnessAmount"; to: 0.3; duration: 3000; easing.type: Easing.InOutSine } NumberAnimation { target: playTriangle; property: "baseScaleX"; to: 1.04; duration: 3000; easing.type: Easing.InOutSine } NumberAnimation { target: playTriangle; property: "baseScaleY"; to: 1.04; duration: 3000; easing.type: Easing.InOutSine } }
                ParallelAnimation { NumberAnimation { target: playTriangle; property: "brightnessAmount"; to: -0.1; duration: 3000; easing.type: Easing.InOutSine } NumberAnimation { target: playTriangle; property: "baseScaleX"; to: 0.98; duration: 3000; easing.type: Easing.InOutSine } NumberAnimation { target: playTriangle; property: "baseScaleY"; to: 0.98; duration: 3000; easing.type: Easing.InOutSine } }
            }
            SequentialAnimation {
                ParallelAnimation { NumberAnimation { target: leftPillar; property: "baseScaleY"; to: 0.96; duration: 3000; easing.type: Easing.InOutSine } NumberAnimation { target: leftPillar; property: "translateY"; to: 2; duration: 3000; easing.type: Easing.InOutSine } NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: -0.15; duration: 3000; easing.type: Easing.InOutSine } }
                ParallelAnimation { NumberAnimation { target: leftPillar; property: "baseScaleY"; to: 1.0; duration: 3000; easing.type: Easing.InOutSine } NumberAnimation { target: leftPillar; property: "translateY"; to: 0; duration: 3000; easing.type: Easing.InOutSine } NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: 0; duration: 3000; easing.type: Easing.InOutSine } }
            }
            SequentialAnimation {
                ParallelAnimation { NumberAnimation { target: rightPillar; property: "baseScaleY"; to: 0.96; duration: 3000; easing.type: Easing.InOutSine } NumberAnimation { target: rightPillar; property: "translateY"; to: 2; duration: 3000; easing.type: Easing.InOutSine } NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: -0.15; duration: 3000; easing.type: Easing.InOutSine } }
                ParallelAnimation { NumberAnimation { target: rightPillar; property: "baseScaleY"; to: 1.0; duration: 3000; easing.type: Easing.InOutSine } NumberAnimation { target: rightPillar; property: "translateY"; to: 0; duration: 3000; easing.type: Easing.InOutSine } NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: 0; duration: 3000; easing.type: Easing.InOutSine } }
            }
        }
    }

    SequentialAnimation {
        id: flowA_Sequence
        
        ParallelAnimation {
            SequentialAnimation {
                ParallelAnimation {
                    NumberAnimation { target: leftPillar; property: "opacity"; from: 0; to: 0.5; duration: 60 }
                    NumberAnimation { target: leftPillar; property: "brightnessAmount"; from: 0; to: 0.5; duration: 60 }
                    NumberAnimation { target: leftPillar; property: "glowScale"; from: 0; to: 0.5; duration: 60 }
                    NumberAnimation { target: leftPillar; property: "baseScaleX"; from: 1; to: 1.02; duration: 60 }
                }
                ParallelAnimation { NumberAnimation { target: leftPillar; property: "opacity"; to: 0; duration: 60 } NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: 0; duration: 60 } NumberAnimation { target: leftPillar; property: "glowScale"; to: 0; duration: 60 } NumberAnimation { target: leftPillar; property: "baseScaleX"; to: 1; duration: 60 } }
                ParallelAnimation { NumberAnimation { target: leftPillar; property: "opacity"; to: 0.5; duration: 60 } NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: 0.5; duration: 60 } NumberAnimation { target: leftPillar; property: "glowScale"; to: 0.5; duration: 60 } NumberAnimation { target: leftPillar; property: "baseScaleX"; to: 1.02; duration: 60 } }
                ParallelAnimation { NumberAnimation { target: leftPillar; property: "opacity"; to: 0; duration: 60 } NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: 0; duration: 60 } NumberAnimation { target: leftPillar; property: "glowScale"; to: 0; duration: 60 } NumberAnimation { target: leftPillar; property: "baseScaleX"; to: 1; duration: 60 } }
                ParallelAnimation { NumberAnimation { target: leftPillar; property: "opacity"; to: 1; duration: 60 } NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: 0.8; duration: 60 } NumberAnimation { target: leftPillar; property: "glowScale"; to: 1.0; duration: 60 } NumberAnimation { target: leftPillar; property: "baseScaleX"; to: 1.05; duration: 60 } }
                ParallelAnimation { NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: 0; duration: 300 } NumberAnimation { target: leftPillar; property: "glowScale"; to: 0.2; duration: 300 } NumberAnimation { target: leftPillar; property: "baseScaleX"; to: 1; duration: 300 } }
            }
            
            SequentialAnimation {
                PauseAnimation { duration: 200 }
                ParallelAnimation { NumberAnimation { target: rightPillar; property: "opacity"; from: 0; to: 0.5; duration: 60 } NumberAnimation { target: rightPillar; property: "brightnessAmount"; from: 0; to: 0.5; duration: 60 } NumberAnimation { target: rightPillar; property: "glowScale"; from: 0; to: 0.5; duration: 60 } NumberAnimation { target: rightPillar; property: "baseScaleX"; from: 1; to: 1.02; duration: 60 } }
                ParallelAnimation { NumberAnimation { target: rightPillar; property: "opacity"; to: 0; duration: 60 } NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: 0; duration: 60 } NumberAnimation { target: rightPillar; property: "glowScale"; to: 0; duration: 60 } NumberAnimation { target: rightPillar; property: "baseScaleX"; to: 1; duration: 60 } }
                ParallelAnimation { NumberAnimation { target: rightPillar; property: "opacity"; to: 0.5; duration: 60 } NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: 0.5; duration: 60 } NumberAnimation { target: rightPillar; property: "glowScale"; to: 0.5; duration: 60 } NumberAnimation { target: rightPillar; property: "baseScaleX"; to: 1.02; duration: 60 } }
                ParallelAnimation { NumberAnimation { target: rightPillar; property: "opacity"; to: 0; duration: 60 } NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: 0; duration: 60 } NumberAnimation { target: rightPillar; property: "glowScale"; to: 0; duration: 60 } NumberAnimation { target: rightPillar; property: "baseScaleX"; to: 1; duration: 60 } }
                ParallelAnimation { NumberAnimation { target: rightPillar; property: "opacity"; to: 1; duration: 60 } NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: 0.8; duration: 60 } NumberAnimation { target: rightPillar; property: "glowScale"; to: 1.0; duration: 60 } NumberAnimation { target: rightPillar; property: "baseScaleX"; to: 1.05; duration: 60 } }
                ParallelAnimation { NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: 0; duration: 300 } NumberAnimation { target: rightPillar; property: "glowScale"; to: 0.2; duration: 300 } NumberAnimation { target: rightPillar; property: "baseScaleX"; to: 1; duration: 300 } }
            }

            SequentialAnimation {
                PauseAnimation { duration: 500 }
                ParallelAnimation {
                    NumberAnimation { target: playTriangle; property: "opacity"; from: 0; to: 1; duration: 800; easing.type: Easing.OutQuad }
                    NumberAnimation { target: playTriangle; property: "brightnessAmount"; from: 1.0; to: 0; duration: 800; easing.type: Easing.OutQuad }
                    NumberAnimation { target: playTriangle; property: "glowScale"; from: 1.0; to: 0.2; duration: 800; easing.type: Easing.OutQuad }
                    NumberAnimation { target: playTriangle; property: "baseScaleX"; from: 1.3; to: 1.0; duration: 800; easing.type: Easing.OutQuad }
                    NumberAnimation { target: playTriangle; property: "baseScaleY"; from: 1.3; to: 1.0; duration: 800; easing.type: Easing.OutQuad }
                }
            }
        } 
        
        ParallelAnimation {
            loops: Animation.Infinite
            SequentialAnimation {
                ParallelAnimation { NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: 0.4; duration: 250 } NumberAnimation { target: leftPillar; property: "glowScale"; to: 0.5; duration: 250 } NumberAnimation { target: leftPillar; property: "baseScaleY"; to: 1.03; duration: 250 } }
                ParallelAnimation { NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: 0; duration: 1200 } NumberAnimation { target: leftPillar; property: "glowScale"; to: 0.2; duration: 1200 } NumberAnimation { target: leftPillar; property: "baseScaleY"; to: 1.0; duration: 1200 } }
                PauseAnimation { duration: 400 }
            }
            SequentialAnimation {
                PauseAnimation { duration: 200 }
                ParallelAnimation { 
                    NumberAnimation { target: playTriangle; property: "brightnessAmount"; to: 0.4; duration: 250 } 
                    NumberAnimation { target: playTriangle; property: "glowScale"; to: 0.5; duration: 250 } 
                    NumberAnimation { target: playTriangle; property: "baseScaleY"; to: 1.03; duration: 250 } 
                    NumberAnimation { target: playTriangle; property: "sweepPosition"; from: -2.5; to: 2.5; duration: 1000; easing.type: Easing.OutQuad }
                }
                ParallelAnimation { NumberAnimation { target: playTriangle; property: "brightnessAmount"; to: 0; duration: 1200 } NumberAnimation { target: playTriangle; property: "glowScale"; to: 0.2; duration: 1200 } NumberAnimation { target: playTriangle; property: "baseScaleY"; to: 1.0; duration: 1200 } }
                PauseAnimation { duration: 200 }
            }
            SequentialAnimation {
                PauseAnimation { duration: 400 }
                ParallelAnimation { NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: 0.4; duration: 250 } NumberAnimation { target: rightPillar; property: "glowScale"; to: 0.5; duration: 250 } NumberAnimation { target: rightPillar; property: "baseScaleY"; to: 1.03; duration: 250 } }
                ParallelAnimation { NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: 0; duration: 1200 } NumberAnimation { target: rightPillar; property: "glowScale"; to: 0.2; duration: 1200 } NumberAnimation { target: rightPillar; property: "baseScaleY"; to: 1.0; duration: 1200 } }
                PauseAnimation { duration: 0 }
            }
        }
    }

    // --- FLOW C: Neon Idle Loop ---
    ParallelAnimation {
        id: flowC_Loop
        
        // Triangle Breathe (5s cycle - Reduced Brightness for better orange)
        SequentialAnimation {
            loops: Animation.Infinite
            ParallelAnimation { NumberAnimation { target: playTriangle; property: "brightnessAmount"; to: 0.3; duration: 2500; easing.type: Easing.InOutSine } NumberAnimation { target: playTriangle; property: "glowScale"; to: 0.5; duration: 2500; easing.type: Easing.InOutSine } NumberAnimation { target: playTriangle; property: "baseScaleX"; to: 1.02; duration: 2500; easing.type: Easing.InOutSine } NumberAnimation { target: playTriangle; property: "baseScaleY"; to: 1.02; duration: 2500; easing.type: Easing.InOutSine } }
            ParallelAnimation { NumberAnimation { target: playTriangle; property: "brightnessAmount"; to: 0; duration: 2500; easing.type: Easing.InOutSine } NumberAnimation { target: playTriangle; property: "glowScale"; to: 0.2; duration: 2500; easing.type: Easing.InOutSine } NumberAnimation { target: playTriangle; property: "baseScaleX"; to: 1.0; duration: 2500; easing.type: Easing.InOutSine } NumberAnimation { target: playTriangle; property: "baseScaleY"; to: 1.0; duration: 2500; easing.type: Easing.InOutSine } }
        }
        
        // Triangle Left-to-Right Highlight Sweep
        SequentialAnimation {
            loops: Animation.Infinite
            PauseAnimation { duration: 1000 }
            NumberAnimation { target: playTriangle; property: "sweepPosition"; from: -2.5; to: 2.5; duration: 1500; easing.type: Easing.InOutQuad }
            PauseAnimation { duration: 2500 }
        }

        // Left Pillar FlickerLow (5s cycle - Slower flickers)
        SequentialAnimation {
            loops: Animation.Infinite
            PauseAnimation { duration: 4000 }
            NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: 0.5; duration: 150 }
            NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: 0; duration: 150 }
            NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: -0.3; duration: 150 }
            NumberAnimation { target: leftPillar; property: "brightnessAmount"; to: 0; duration: 150 }
            PauseAnimation { duration: 400 }
        }
        
        // Right Pillar FlickerLow (Perfect offset)
        SequentialAnimation {
            loops: Animation.Infinite
            PauseAnimation { duration: 2000 }
            NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: 0.5; duration: 150 }
            NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: 0; duration: 150 }
            NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: -0.3; duration: 150 }
            NumberAnimation { target: rightPillar; property: "brightnessAmount"; to: 0; duration: 150 }
            PauseAnimation { duration: 2400 }
        }
    }
}