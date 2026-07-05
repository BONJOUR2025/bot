import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var auth: AuthViewModel

    var body: some View {
        Group {
            if auth.isAuthenticated {
                MainShellView()
            } else {
                LoginView()
            }
        }
        .task {
            await auth.restoreSession()
        }
    }
}
