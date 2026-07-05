import SwiftUI

/// Separate, fully native (SwiftUI, no WebView) counterpart to the
/// Capacitor-wrapped admin_frontend/ios app — the two are independent
/// Xcode projects/targets, installable side by side, sharing nothing but
/// the same backend API. This one is a skeleton on purpose: login +
/// navigation only, real screens land later one at a time.
@main
struct BonjourNativeApp: App {
    @StateObject private var auth = AuthViewModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(auth)
        }
    }
}
