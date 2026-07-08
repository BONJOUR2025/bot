import UIKit
import Capacitor

// SceneDelegate forces the window to .light to keep the status-bar-style
// cross-fade animation clean (see the comment there). That override
// cascades down to every subview by default — including the WKWebView —
// which means `prefers-color-scheme` in CSS/JS would always report
// "light" on-device, no matter the phone's real appearance, breaking the
// web app's "auto" theme. Un-forcing it here, on the webview specifically,
// lets the webview keep following the real system setting while the
// window (and its status-bar chrome) stays pinned to .light.
class MainViewController: CAPBridgeViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        webView?.overrideUserInterfaceStyle = .unspecified
    }
}
