import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs as Dialogs
import QtWebEngine

ApplicationWindow {
    id: root
    visible: true
    width: 1200
    height: 800
    title: "DeadHop"

    property color bg: AppState.theme === "dark" ? "#0f1115" : "#ffffff"
    property color fg: AppState.theme === "dark" ? "#e6e9ef" : "#111318"
    property color panel: AppState.theme === "dark" ? "#141721" : "#f4f6fb"
    property color accent: AppState.accent

    // Background animated GIF (optional)
    AnimatedImage {
        id: bgAnim
        anchors.fill: parent
        z: -1
        visible: AppState.bgEnabled && AppState.bgPath !== ""
        source: AppState.bgPath
        playing: visible
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        opacity: AppState.bgOpacity
    }

    // Dim/tint behind content
    Rectangle {
        anchors.fill: parent
        z: -0.5
        color: bg
        opacity: AppState.bgEnabled ? 0.75 : 1.0
    }

    // Right member pane
    Rectangle {
        id: members
        width: 220
        visible: false // superseded by SplitView right pane
        anchors { top: parent.top; bottom: parent.bottom; right: parent.right }
        color: panel
        ColumnLayout { anchors.fill: parent; anchors.margins: 8; spacing: 6
            Label { text: "Members"; color: fg; font.bold: true }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: Users
                clip: true
                delegate: Rectangle {
                    width: parent.width; height: 28; color: "transparent"
                    opacity: away ? 0.55 : 1.0
                    HoverHandler { id: hover }
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left; anchors.leftMargin: 8
                        spacing: 6
                        Rectangle {
                            visible: badge && badge.length > 0
                            width: 18; height: 18; radius: 9
                            color: "#232a3d"
                            border.color: "#2e3550"
                            Text { anchors.centerIn: parent; text: badge.charAt(0); color: fg; font.pixelSize: 12 }
                        }
                        Text { text: nick; color: fg }
                    }
                    ToolTip.visible: hover.hovered
                    ToolTip.text: {
                        var parts = []
                        if (account && account.length > 0) parts.push("Account: " + account)
                        if (user && host) parts.push("Ident: " + user + "@" + host)
                        if (realname && realname.length > 0) parts.push("Real: " + realname)
                        return parts.join("\n")
                    }

                    // Context menu for member actions
                    Menu {
                        id: userMenu
                        modal: true
                        dim: false
                        MenuItem { text: "Open PM"; onTriggered: Bridge.openPm(nick) }
                        MenuItem { text: "WHOIS"; onTriggered: Bridge.whois(nick) }
                        MenuSeparator {}
                        MenuItem { text: "Copy Nick"; onTriggered: Bridge.copyText(nick) }
                        MenuItem { text: "Copy Account"; enabled: account && account.length > 0; onTriggered: Bridge.copyText(account) }
                        MenuItem { text: "Copy Ident"; enabled: user && host; onTriggered: Bridge.copyText((user||"") + "@" + (host||"")) }
                        MenuSeparator {}
                        MenuItem { text: "+o (Op)"; onTriggered: Bridge.modeUser("o", nick, true) }
                        MenuItem { text: "-o (Deop)"; onTriggered: Bridge.modeUser("o", nick, false) }
                        MenuItem { text: "+h (Halfop)"; onTriggered: Bridge.modeUser("h", nick, true) }
                        MenuItem { text: "-h (Dehalfop)"; onTriggered: Bridge.modeUser("h", nick, false) }
                        MenuItem { text: "+v (Voice)"; onTriggered: Bridge.modeUser("v", nick, true) }
                        MenuItem { text: "-v (Devoice)"; onTriggered: Bridge.modeUser("v", nick, false) }
                        MenuItem { text: "+q (Owner)"; onTriggered: Bridge.modeUser("q", nick, true) }
                        MenuItem { text: "-q (Deowner)"; onTriggered: Bridge.modeUser("q", nick, false) }
                        MenuItem { text: "+a (Admin)"; onTriggered: Bridge.modeUser("a", nick, true) }
                        MenuItem { text: "-a (Deadmin)"; onTriggered: Bridge.modeUser("a", nick, false) }
                    }
                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.RightButton
                        onPressed: function(ev) {
                            if (ev.button === Qt.RightButton) {
                                userMenu.openAt(ev.scenePosition)
                                ev.accepted = true
                            }
                        }
                    }
                }
            }


    // Settings dialog
    Dialog {
        id: settingsDialog
        title: "Settings"
        modal: true
        standardButtons: Dialog.Close
        onAccepted: settingsDialog.close()
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 10
            GroupBox {
                title: "Appearance"
                Layout.fillWidth: true
                ColumnLayout { anchors.margins: 8; anchors.fill: parent; spacing: 8
                    RowLayout { spacing: 8
                        Label { text: "Theme"; color: fg; Layout.minimumWidth: 120 }
                        ComboBox {
                            id: themeCombo
                            model: ["dark", "light"]
                            currentIndex: AppState.theme === "light" ? 1 : 0
                            onActivated: AppState.setTheme(currentText)
                        }
                    }
                    RowLayout { spacing: 8
                        Label { text: "Accent"; color: fg; Layout.minimumWidth: 120 }
                        TextField { id: accentField; text: AppState.accent; Layout.fillWidth: true }
                        Button { text: "Apply"; onClicked: AppState.setAccent(accentField.text) }
                    }
                    RowLayout { spacing: 8
                        Label { text: "Background"; color: fg; Layout.minimumWidth: 120 }
                        Switch { checked: AppState.bgEnabled; onToggled: AppState.setBgEnabled(checked) }
                    }
                    RowLayout { spacing: 8
                        Label { text: "BG Opacity"; color: fg; Layout.minimumWidth: 120 }
                        Slider { from: 0; to: 1; stepSize: 0.01; value: AppState.bgOpacity; onMoved: AppState.setBgOpacity(value); Layout.fillWidth: true }
                    }
                    RowLayout { spacing: 8
                        Label { text: "BG File"; color: fg; Layout.minimumWidth: 120 }
                        TextField { text: AppState.bgPath; readOnly: true; Layout.fillWidth: true }
                        Button { text: "Browse"; onClicked: fileDialog.open() }
                    }
                }
            }
            GroupBox {
                title: "Notifications"
                Layout.fillWidth: true
                ColumnLayout { anchors.margins: 8; anchors.fill: parent; spacing: 8
                    RowLayout { spacing: 8
                        Label { text: "Enabled"; color: fg; Layout.minimumWidth: 120 }
                        Switch { checked: Bridge.notifEnabled; onToggled: Bridge.setNotifEnabled(checked) }
                    }
                    RowLayout { spacing: 8
                        Label { text: "System Tray"; color: fg; Layout.minimumWidth: 120 }
                        Switch { checked: Bridge.notifSystemTray; onToggled: Bridge.setNotifSystemTray(checked) }
                    }
                    RowLayout { spacing: 8
                        Label { text: "On Mention"; color: fg; Layout.minimumWidth: 120 }
                        Switch { checked: Bridge.notifMention; onToggled: Bridge.setNotifMention(checked) }
                    }
                    RowLayout { spacing: 8
                        Label { text: "On PM"; color: fg; Layout.minimumWidth: 120 }
                        Switch { checked: Bridge.notifPm; onToggled: Bridge.setNotifPm(checked) }
                    }
                    RowLayout { spacing: 8
                        Label { text: "On Connect"; color: fg; Layout.minimumWidth: 120 }
                        Switch { checked: Bridge.notifConnect; onToggled: Bridge.setNotifConnect(checked) }
                    }
                    RowLayout { spacing: 8
                        Label { text: "On Error"; color: fg; Layout.minimumWidth: 120 }
                        Switch { checked: Bridge.notifError; onToggled: Bridge.setNotifError(checked) }
                    }
                    RowLayout { spacing: 8
                        Label { text: "Sound Path"; color: fg; Layout.minimumWidth: 120 }
                        TextField { text: Bridge.soundPath; readOnly: true; Layout.fillWidth: true }
                        Button { text: "Browse"; onClicked: soundDialog.open() }
                    }
                    RowLayout { spacing: 8
                        Label { text: "Volume"; color: fg; Layout.minimumWidth: 120 }
                        Slider { from: 0; to: 1; stepSize: 0.01; value: Bridge.soundVolume; onMoved: Bridge.setSoundVolume(value); Layout.fillWidth: true }
                    }
                }
            }
            GroupBox {
                title: "Logging"
                Layout.fillWidth: true
                ColumnLayout { anchors.margins: 8; anchors.fill: parent; spacing: 8
                    RowLayout { spacing: 8
                        Label { text: "Enabled"; color: fg; Layout.minimumWidth: 120 }
                        Switch { checked: Bridge.logEnabled; onToggled: Bridge.setLogEnabled(checked) }
                    }
                    RowLayout { spacing: 8
                        Label { text: "Directory"; color: fg; Layout.minimumWidth: 120 }
                        TextField { text: Bridge.logDir; readOnly: true; Layout.fillWidth: true }
                        Button { text: "Browse"; onClicked: dirDialog.open() }
                    }
                    RowLayout { spacing: 8 }
                    RowLayout { spacing: 8
                        Label { text: "Export Start (YYYY-MM-DD)"; color: fg; Layout.minimumWidth: 200 }
                        TextField { id: startDateField; placeholderText: "2025-01-01"; Layout.fillWidth: true }
                    }
                    RowLayout { spacing: 8
                        Label { text: "Export End (YYYY-MM-DD)"; color: fg; Layout.minimumWidth: 200 }
                        TextField { id: endDateField; placeholderText: "2025-12-31"; Layout.fillWidth: true }
                    }
                    RowLayout { spacing: 8
                        Label { text: "Format"; color: fg; Layout.minimumWidth: 120 }
                        ComboBox { id: fmtCombo; model: ["jsonl", "csv"]; currentIndex: 0 }
                        Button { text: "Export Current Channel"; onClicked: Bridge.exportLogs(Bridge.currentChannel, startDateField.text, endDateField.text, fmtCombo.currentText) }
                    }
                }
            }
            GroupBox {
                title: "Channel Overrides"
                Layout.fillWidth: true
                ColumnLayout { anchors.margins: 8; anchors.fill: parent; spacing: 8
                    property bool ovMention: true
                    property bool ovPm: true
                    property bool ovConnect: true
                    property bool ovError: true
                    RowLayout { spacing: 8
                        Label { text: "Target"; color: fg; Layout.minimumWidth: 120 }
                        Text { text: Bridge.currentChannel; color: fg }
                        Button { text: "Load"; onClicked: {
                            ovMention = Bridge.notifOverrideMention(Bridge.currentChannel)
                            ovPm = Bridge.notifOverridePm(Bridge.currentChannel)
                            ovConnect = Bridge.notifOverrideConnect(Bridge.currentChannel)
                            ovError = Bridge.notifOverrideError(Bridge.currentChannel)
                        } }
                    }
                    RowLayout { spacing: 8
                        Label { text: "Mention"; color: fg; Layout.minimumWidth: 120 }
                        Switch { checked: parent.parent.ovMention; onToggled: { parent.parent.ovMention = checked; Bridge.setNotifOverrideMention(Bridge.currentChannel, checked) } }
                    }
                    RowLayout { spacing: 8
                        Label { text: "PM"; color: fg; Layout.minimumWidth: 120 }
                        Switch { checked: parent.parent.ovPm; onToggled: { parent.parent.ovPm = checked; Bridge.setNotifOverridePm(Bridge.currentChannel, checked) } }
                    }
                    RowLayout { spacing: 8
                        Label { text: "Connect"; color: fg; Layout.minimumWidth: 120 }
                        Switch { checked: parent.parent.ovConnect; onToggled: { parent.parent.ovConnect = checked; Bridge.setNotifOverrideConnect(Bridge.currentChannel, checked) } }
                    }
                    RowLayout { spacing: 8
                        Label { text: "Error"; color: fg; Layout.minimumWidth: 120 }
                        Switch { checked: parent.parent.ovError; onToggled: { parent.parent.ovError = checked; Bridge.setNotifOverrideError(Bridge.currentChannel, checked) } }
                    }
                }
            }
            GroupBox {
                title: "Scripting"
                Layout.fillWidth: true
                ColumnLayout { anchors.margins: 8; anchors.fill: parent; spacing: 8
                    RowLayout { spacing: 8
                        Label { text: "Scripts Dir"; color: fg; Layout.minimumWidth: 120 }
                        Text { text: AppState ? (JSON.parse('{}') && (AppState.bgPath, "")) : ""; visible: false } // placeholder to keep layout stable
                        Text { text: Qt.resolvedUrl(""); visible: false }
                        Button { text: "Reload Scripts"; onClicked: Bridge.reloadScripts() }
                    }
                }
            }

    GroupBox {
                title: "Profiles"
                Layout.fillWidth: true
                ColumnLayout { anchors.margins: 8; anchors.fill: parent; spacing: 8
                    RowLayout { spacing: 8 }
                    TextArea {
                        id: profilesJson
                        text: Bridge.serversJson()
                        wrapMode: TextArea.Wrap
                        Layout.fillWidth: true
                        Layout.preferredHeight: 160
                        font.family: "monospace"
                    }
                    RowLayout { spacing: 8
                        Button { text: "Refresh"; onClicked: profilesJson.text = Bridge.serversJson() }
                        Button { text: "Save"; onClicked: Bridge.setServersJson(profilesJson.text) }
                    }
                }
            }
        }
    }

    Dialogs.FileDialog {
        id: soundDialog
        title: "Choose a WAV file"
        nameFilters: ["WAV files (*.wav)", "All files (*.*)"]
        onAccepted: {
            var url = (selectedFiles && selectedFiles.length > 0) ? selectedFiles[0] : null
            if (!url) return
            var p = url.toString()
            p = p.replace(/^file:\/\//, "")
            if (p.startsWith("/")) { if (/^\/[A-Za-z]:\//.test(p)) p = p.substring(1) }
            Bridge.setSoundPath(p)
        }
    }

    Dialogs.FileDialog {
        id: dirDialog
        title: "Choose logging directory"
        onAccepted: {
            var url = (selectedFiles && selectedFiles.length > 0) ? selectedFiles[0] : null
            if (!url) return
            var p = url.toString()
            p = p.replace(/^file:\/\//, "")
            if (p.startsWith("/")) { if (/^\/[A-Za-z]:\//.test(p)) p = p.substring(1) }
            var dir = p.replace(/[\/][^\/]*$/, "")
            Bridge.setLogDir(dir)
        }
    }

    // Base background overlay (tint)
    Rectangle {
        x: 0; y: 0
        width: parent.width; height: parent.height
        color: bg
        opacity: AppState.bgEnabled ? 0.75 : 1.0
    }

    // Main content layout with SplitView panes
    ColumnLayout {
        id: mainLayout
        anchors.fill: parent
        spacing: 0

        // Row 1: Header toolbar managed by layout
        ToolBar {
            id: headerBar
            Layout.fillWidth: true
            z: 10
            background: Rectangle { color: panel }
            RowLayout {
                x: 0; y: 0
                width: parent.width; height: parent.height
                spacing: 12
                Label { text: "DeadHop"; font.bold: true; color: fg; leftPadding: 12 }
                Item { Layout.fillWidth: true }
                RowLayout {
                    spacing: 8
                    Switch {
                        id: aiSwitch
                        checked: AppState.aiEnabled
                        onToggled: AppState.setAiEnabled(checked)
                    }
                    Rectangle { width: 10; height: 10; radius: 5; color: aiSwitch.checked ? accent : "#666" }
                    Text { text: aiSwitch.checked ? "AI On" : "AI Off"; color: fg }
                }
                // Background controls (quick access)
                RowLayout {
                    spacing: 8
                    Switch {
                        id: bgSwitch
                        checked: AppState.bgEnabled
                        onToggled: AppState.setBgEnabled(checked)
                    }
                    Rectangle { width: 10; height: 10; radius: 5; color: bgSwitch.checked ? accent : "#666" }
                    Text { text: bgSwitch.checked ? "BG On" : "BG Off"; color: fg }
                }
                Slider {
                    id: bgOpacity
                    from: 0; to: 1; stepSize: 0.01
                    value: AppState.bgOpacity
                    visible: AppState.bgEnabled
                    implicitWidth: 120
                    onMoved: AppState.setBgOpacity(value)
                    ToolTip.visible: hovered
                    ToolTip.text: "BG Opacity: " + value.toFixed(2)
                }
                ToolButton { text: "BG File"; visible: AppState.bgEnabled; onClicked: fileDialog.open() }
                Dialogs.FileDialog {
                    id: fileDialog
                    title: "Choose a GIF background"
                    nameFilters: ["GIF files (*.gif)", "All files (*.*)"]
                    onAccepted: {
                        var url = (selectedFiles && selectedFiles.length > 0) ? selectedFiles[0] : null
                        if (!url) return
                        var p = url.toString()
                        // Strip file:// or file:/// prefix cross-platform
                        p = p.replace(/^file:\/\//, "")
                        if (p.startsWith("/")) {
                            // On Windows, remove leading slash from /C:/...
                            if (/^\/[A-Za-z]:\//.test(p)) p = p.substring(1)
                        }
                        AppState.setBgPath(p)
                    }
                }
                ToolButton { text: "Settings"; onClicked: settingsDialog.open() }
                ToolButton { text: "Connect"; onClicked: Bridge.connectDefault() }
                Item { width: 12 }
            }
        }

        // Row 2: SplitView
        SplitView {
            id: split
            Layout.fillWidth: true
            Layout.fillHeight: true

            // Left: Servers/Quick Connect
            Rectangle {
                color: panel
                implicitWidth: 280
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8
                    Label { text: "Servers"; color: fg; font.bold: true }
                    Repeater {
                        model: ["Libera", "ExampleNet"]
                        delegate: Rectangle { radius: 8; color: "transparent" }
                    }
                    Label { text: "Quick Connect"; color: fg; font.bold: true; Layout.topMargin: 8 }
                    ListView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 150
                        model: (typeof BuiltinServers !== 'undefined' && BuiltinServers) ? BuiltinServers : []
                        clip: true
                        delegate: Item {
                            width: parent.width; height: 34
                            RowLayout { anchors.fill: parent
                                Text { text: String(modelData || ""); color: fg; Layout.fillWidth: true }
                                Button { text: "Join"; onClicked: {
                                    var s = String(modelData)
                                    var host = s
                                    var port = 6697
                                    if (s.indexOf(":") > 0) { var parts = s.split(":"); host = parts[0]; port = parseInt(parts[1]) }
                                    Bridge.connectHost(host, port, true)
                                }}
                            }
                            MouseArea { anchors.fill: parent; onClicked: {
                                    var s = String(modelData)
                                    var host = s
                                    var port = 6697
                                    if (s.indexOf(":") > 0) { var parts = s.split(":"); host = parts[0]; port = parseInt(parts[1]) }
                                    Bridge.connectHost(host, port, true)
                                }}
                        }
                    }
                }
            }

            // Center: Chat area placeholder (to be wired to Messages)
            Rectangle {
                color: "transparent"
                SplitView.preferredWidth: 640
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8
                    Label { text: "Chat"; color: fg; font.bold: true }
                    Item { Layout.fillWidth: true; Layout.fillHeight: true }
                    RowLayout {
                        Layout.fillWidth: true
                        TextField { id: inputField; Layout.fillWidth: true; placeholderText: "Type a message..." }
                        Button { text: "Send"; onClicked: {
                            if (inputField.text && inputField.text.length > 0) { Bridge.sendMessage(inputField.text); inputField.text = "" }
                        }}
                    }
                }
            }

            // Right: Members panel (no anchors)
            Rectangle {
                color: panel
                implicitWidth: 220
                ColumnLayout { anchors.fill: parent; anchors.margins: 8; spacing: 6
                    Label { text: "Members"; color: fg; font.bold: true }
                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        model: Users
                        clip: true
                        delegate: Rectangle {
                            width: parent.width; height: 28; color: "transparent"
                            opacity: away ? 0.55 : 1.0
                            HoverHandler { id: hover2 }
                            Row {
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: parent.left; anchors.leftMargin: 8
                                spacing: 6
                                Rectangle {
                                    visible: badge && badge.length > 0
                                    width: 18; height: 18; radius: 9
                                    color: "#232a3d"
                                    border.color: "#2e3550"
                                    Text { anchors.centerIn: parent; text: badge.charAt(0); color: fg; font.pixelSize: 12 }
                                }
                                Text { text: nick; color: fg }
                            }
                            ToolTip.visible: hover2.hovered
                            ToolTip.text: {
                                var parts = []
                                if (account && account.length > 0) parts.push("Account: " + account)
                                if (user && host) parts.push("Ident: " + user + "@" + host)
                                if (realname && realname.length > 0) parts.push("Real: " + realname)
                                return parts.join("\n")
                            }
                        }
                    }
                }
            }
        }
    }

    // Legacy Drawer remains defined below (unused by main layout)
    Drawer {
        id: sidebar
        width: 280
        height: parent.height
        interactive: true
        visible: true
        edge: Qt.LeftEdge
        contentItem: Rectangle {
            color: panel
            ColumnLayout {
                anchors.fill: parent
                spacing: 8
                anchors.margins: 12
                Label { text: "Servers"; color: fg; font.bold: true }
                Repeater {
                    model: ["Libera", "ExampleNet"]
                    delegate: Rectangle {
                        radius: 8
                        color: "transparent"
                        }
                    }
                }
                Label { text: "Quick Connect"; color: fg; font.bold: true; topPadding: 8 }
                ListView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 150
                    model: (typeof BuiltinServers !== 'undefined' && BuiltinServers) ? BuiltinServers : []
                    clip: true
                    delegate: Item {
                        width: parent.width; height: 34
                        RowLayout { anchors.fill: parent
                            Text { text: String(modelData || ""); color: fg; Layout.fillWidth: true }
                            Button { text: "Join"; onClicked: {
                                var s = String(modelData)
                                var host = s
                                var port = 6697
                                if (s.indexOf(":") > 0) {
                                    var parts = s.split(":"); host = parts[0]; port = parseInt(parts[1])
                                }
                                Bridge.connectHost(host, port, true)
                            }}
                        }
                        MouseArea { anchors.fill: parent; onClicked: {
                                var s = String(modelData)
                                var host = s
                                var port = 6697
                                if (s.indexOf(":") > 0) { var parts = s.split(":"); host = parts[0]; port = parseInt(parts[1]) }
                                Bridge.connectHost(host, port, true)
                            }}
                    }
                }
                Label { text: "Channels"; color: fg; font.bold: true; topPadding: 8 }
                ListView {
                    id: channelList
                    Layout.fillWidth: true
                    Layout.preferredHeight: 260
                    model: Channels
                    clip: true
                    delegate: Rectangle {
                        required property string modelData
                        width: channelList.width
                        height: 36
                        radius: 8
                        color: (Bridge.currentChannel === modelData) ? "#1b2338" : "transparent"
                        border.color: (Bridge.currentChannel === modelData) ? accent : "#202433"
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 8
                            Label { text: modelData; color: fg; Layout.fillWidth: true }
                            Rectangle { width: 8; height: 8; radius: 4; color: accent }
                        }
                        MouseArea { anchors.fill: parent; onClicked: Bridge.setCurrentChannel(modelData) }
                    }
                }
                Item { Layout.fillHeight: true }
            }
        }
    }

    // Main chat area
    ColumnLayout {
        anchors { left: sidebar.right; right: members.left; top: parent.top; bottom: parent.bottom; margins: 0 }
        spacing: 0

        Rectangle { // Topic + search
            color: panel
            height: 48
            RowLayout { anchors.fill: parent; anchors.margins: 12; spacing: 12
                Label { text: Bridge.currentChannel + " — Modern DeadHop IRC"; color: fg; Layout.fillWidth: true }
                TextField { placeholderText: "Search"; Layout.preferredWidth: 240 }
            }
        }

        // Messages list
        ListView {
            id: messageList
            Layout.fillWidth: true
            Layout.fillHeight: true
            model: Messages
            spacing: 8
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            delegate: Item {
                width: messageList.width
                height: bubble.implicitHeight + 12
                RowLayout {
                    anchors.left: parent.left; anchors.right: parent.right; anchors.margins: 16
                    spacing: 8
                    Rectangle { width: 28; height: 28; radius: 14; color: "#2a2f43" }
                    Rectangle {
                        id: bubble
                        Layout.fillWidth: true
                        radius: 10
                        color: "#1b1f2e"
                        Column { anchors.margins: 10; anchors.fill: parent; spacing: 6
                            Row { spacing: 8
                                Text { text: nick; color: fg; font.bold: true }
                                Text { text: new Date(ts*1000).toLocaleTimeString(); color: "#98a2b3"; font.pixelSize: 12 }
                            }
                            Text { text: text; color: fg; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                            // Inline image preview
                            Image {
                                visible: embedType === "image"
                                source: embedUrl
                                fillMode: Image.PreserveAspectFit
                                asynchronous: true
                                cache: true
                                width: parent.width
                                height: visible ? Math.min(280, implicitHeight) : 0
                            }
                            // YouTube embed - click to play (WebEngineView)
                            Rectangle {
                                visible: embedType === "youtube"
                                color: "#0f1115"
                                radius: 8
                                width: parent.width
                                height: visible ? 220 : 0
                                border.color: "#272d3f"
                                Column { anchors.fill: parent; anchors.margins: 6; spacing: 6
                                    Button {
                                        id: playBtn
                                        text: "Play YouTube"
                                        onClicked: web.visible = true
                                    }
                                    WebEngineView {
                                        id: web
                                        anchors.left: parent.left; anchors.right: parent.right
                                        height: 180
                                        visible: false
                                        url: embedUrl
                                        settings.javascriptEnabled: true
                                        settings.pluginsEnabled: false
                                    }
                                }
                            }
                        }
                    }
                }
            }
            onCountChanged: positionViewAtEnd()
        }

        // Composer
        Rectangle {
            color: panel
            height: 72
            RowLayout { anchors.fill: parent; anchors.margins: 12; spacing: 8
                TextArea {
                    id: input
                    placeholderText: "Message " + Bridge.currentChannel
                    wrapMode: TextArea.Wrap
                    Layout.fillWidth: true
                    Keys.onPressed: (e) => {
                        if ((e.key === Qt.Key_Return || e.key === Qt.Key_Enter) && (e.modifiers & Qt.ShiftModifier) === 0) {
                            e.accepted = true
                            if (input.text.length > 0) {
                                Bridge.sendMessage(input.text)
                                input.text = ""
                            }
                        }
                    }
                }
                Button { text: "Send"; onClicked: { if (input.text.length>0) { Bridge.sendMessage(input.text); input.text = "" } } }
            }
        }
    }

    // Toast (simple)
    Rectangle {
        id: toast
        width: Math.min(480, parent.width - 40)
        height: implicitHeight
        radius: 10
        color: "#111521"
        opacity: 0
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
        z: 10
        Behavior on opacity { NumberAnimation { duration: 180 } }
        Column { anchors.margins: 12; anchors.fill: parent
            Text { id: toastText; color: "#dde1ea"; wrapMode: Text.Wrap }
        }
        Connections {
            target: AppState
            function onToastRequested(msg) {
                toastText.text = msg
                toast.opacity = 1
                toastTimer.restart()
            }
        }
        Timer { id: toastTimer; interval: 2200; onTriggered: toast.opacity = 0 }
    }
}

}
