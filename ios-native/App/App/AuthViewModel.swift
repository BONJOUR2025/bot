import Foundation

@MainActor
final class AuthViewModel: ObservableObject {
    @Published var user: AuthUser?
    @Published var isLoading = false
    @Published var errorMessage: String?

    var isAuthenticated: Bool { user != nil }

    /// Called once at app launch — if a token is already saved (previous
    /// session), verify it's still valid against /api/auth/me rather than
    /// trusting it blindly (it may have expired — see TOKEN_TTL_SECONDS,
    /// 12 hours, in app/services/access_control_service.py).
    func restoreSession() async {
        guard APIClient.shared.token != nil else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            user = try await APIClient.shared.fetchMe()
        } catch {
            APIClient.shared.logout()
        }
    }

    func login(login: String, password: String) async {
        errorMessage = nil
        isLoading = true
        defer { isLoading = false }
        do {
            user = try await APIClient.shared.login(login: login, password: password)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func logout() {
        APIClient.shared.logout()
        user = nil
    }
}
