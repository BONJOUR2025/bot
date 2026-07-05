import SwiftUI

/// Stand-in for every real screen not built yet — this pass is just the
/// auth + navigation skeleton (see the chat: scope was deliberately limited
/// so it's actually verifiable on a real Mac/Xcode build instead of dozens
/// of unverified screens at once).
struct PlaceholderView: View {
    let title: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "hammer")
                .font(.system(size: 36))
                .foregroundStyle(.secondary)
            Text("Экран в разработке")
                .foregroundStyle(.secondary)
        }
        .navigationTitle(title)
    }
}
