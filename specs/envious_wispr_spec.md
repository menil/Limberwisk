# Specification: EnviousWispr URL Scheme & Upstream Integration

## 1. Overview

**EnviousWispr** ([saurabhav88/EnviousWispr](https://github.com/saurabhav88/EnviousWispr)) is an open-source, on-device AI dictation application for macOS (Apple Silicon) built with Swift and SwiftUI. It leverages WhisperKit and Parakeet models to provide fast, local speech-to-text without cloud subscriptions.

Currently, EnviousWispr is triggered via Carbon global hotkeys (`RegisterEventHotKey`). To enable zero-latency, tactile control from external hardware buttons (such as MuteMe pucks and USB foot pedals) without synthetic key-injection hacks, this specification defines a native macOS URL scheme for EnviousWispr and the plan for submitting an upstream PR.

---

## 2. Specification & Contract

### 2.1 Target Identifiers
* **Application Bundle ID:** `com.enviouslabs.EnviousWispr`
* **Custom URL Scheme:** `envious-wispr://`
* **Process Detection:** `NSRunningApplication.runningApplicationsWithBundleIdentifier:`

### 2.2 Deep Link Actions

| URL | Action | Semantics |
| :--- | :--- | :--- |
| `envious-wispr://start-dictation` | Start recording | Idempotent: starts recording audio; no-op if already recording. Alias: `envious-wispr://start-hands-free`. |
| `envious-wispr://stop-dictation` | Stop recording & transcribe | Idempotent: finalizes audio buffer and pastes text; no-op if idle. Alias: `envious-wispr://stop-hands-free`. |
| `envious-wispr://toggle-dictation` | Toggle dictation state | Optional toggle convenience for single-trigger devices. |

### 2.3 Non-Focus Invariant
Dispatching `envious-wispr://` commands via `NSWorkspace.shared.openURLs(_:withApplicationAt:configuration:completionHandler:)` with `NSWorkspace.OpenConfiguration(activates: false)` (or `configuration.setActivates_(False)` in PyObjC) MUST NOT bring EnviousWispr's window to the foreground or steal keyboard focus from the active text document or input field across all supported actions.

### 2.4 Error Handling & Lifecycle Semantics
* **Process Not Running:** If EnviousWispr is not currently running when a URL action is dispatched, `NSWorkspace` will fail the dispatch or fail to locate the running instance without blocking the dispatch queue. Clients should monitor process presence using `NSRunningApplication.runningApplicationsWithBundleIdentifier:`.
* **Idempotency Under Rapid Toggling:** Repeated `start-dictation` signals while recording are ignored; repeated `stop-dictation` signals while idle are no-ops.

---

## 3. Upstream PR Implementation Plan (for `saurabhav88/EnviousWispr`)

### 3.1 `Info.plist` URL Scheme Registration
Add the URL scheme definition to the target's `Info.plist`:

```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleTypeRole</key>
        <string>Viewer</string>
        <key>CFBundleURLName</key>
        <string>com.enviouslabs.EnviousWispr</string>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>envious-wispr</string>
        </array>
    </dict>
</array>
```

### 3.2 URL Event Handling in Swift
In the main `@main App` or `AppDelegate`:

```swift
@main
struct EnviousWisprApp: App {
    @StateObject private var dictationCoordinator = DictationCoordinator.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .onOpenURL { url in
                    handleIncomingURL(url)
                }
        }
    }

    private func handleIncomingURL(_ url: URL) {
        guard url.scheme?.lowercased() == "envious-wispr" else { return }
        let action = (url.host ?? url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))).lowercased()
        switch action {
        case "start-dictation", "start-hands-free":
            dictationCoordinator.startDictation()
        case "stop-dictation", "stop-hands-free":
            dictationCoordinator.stopDictation()
        case "toggle-dictation":
            dictationCoordinator.toggleDictation()
        default:
            break
        }
    }
}
```

---

## 4. Security Considerations

- **Trust Boundary:** The custom URL scheme handler is exposed to any local process running within the logged-in user session. No credentials, tokens, or network transfers are accepted via the URL.
- **Microphone TCC Permissions:** Microphone audio capture remains governed strictly by macOS Transparency, Consent, and Control (TCC) granted to the EnviousWispr application bundle.
- **Idempotency Guarantees:** Commands are idempotent; spurious or repeated triggers do not corrupt internal audio buffers or trigger runaway loops.

---

## 5. Client Adapter Implementation (in `muteme-flow`)

In `muteme-flow`, EnviousWispr will be supported as a first-class `DictationBackend`:
* **Adapter:** `EnviousWisprBackend(DictationBackend)`
* **Dispatcher:** `NSWorkspaceDispatcher(bundle_id="com.enviouslabs.EnviousWispr", app_name="EnviousWispr")`
* **Presence:** `WisprPresence(bundle_id="com.enviouslabs.EnviousWispr")`
* **Commands:**
  * `DictationCommand.START` $\rightarrow$ `envious-wispr://start-dictation`
  * `DictationCommand.STOP` $\rightarrow$ `envious-wispr://stop-dictation`

---

## 6. Verification Checklist & Test Scenarios

- [ ] **URL Scheme Registration:** Opening `envious-wispr://start-dictation` via macOS `open` command successfully targets the app.
- [ ] **Idempotency Verification:** Sending consecutive `start-dictation` calls results in single continuous dictation session without audio buffer reset.
- [ ] **Focus Preservation:** When an active text field in a separate application (e.g. TextEdit, Xcode) has focus, triggering URL scheme does not transfer window focus or active keyboard target.
- [ ] **Non-Running Handling:** Dispatching commands while EnviousWispr is closed safely surfaces backend not running status without hanging.
