import Foundation

/// Talks to the same FastAPI backend the web admin (admin_frontend) uses —
/// see app/api/auth.py. Auth is Bearer-token based (not the browser's cookie
/// jar): POST /api/auth/login returns a token in the JSON body itself
/// (app/schemas/auth.py's LoginResponse), which get_current_user
/// (app/api/dependencies.py) accepts equally via an Authorization header or
/// the cookie — a native app has no cookie jar shared with Safari, so the
/// header is the only sane option here.
enum APIError: Error, LocalizedError {
    case invalidResponse
    case server(status: Int, message: String)
    case decoding

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "Некорректный ответ сервера"
        case .server(_, let message): return message
        case .decoding: return "Не удалось разобрать ответ сервера"
        }
    }
}

struct AuthUser: Codable {
    let id: String
    let login: String
    let roleId: String?
    let roleName: String?
    let permissions: [String]
    let botButtons: [String]
    let displayName: String?
    let employeeId: String?

    enum CodingKeys: String, CodingKey {
        case id, login, permissions
        case roleId = "role_id"
        case roleName = "role_name"
        case botButtons = "bot_buttons"
        case displayName = "display_name"
        case employeeId = "employee_id"
    }
}

struct LoginResponse: Codable {
    let token: String
    let user: AuthUser
}

final class APIClient {
    static let shared = APIClient()

    /// Same origin as the web admin (admin_frontend/capacitor.config.json) —
    /// one backend serves both the wrapper app and this native shell.
    let baseURL = URL(string: "https://app.bonjour.pw")!

    private let session = URLSession(configuration: .default)

    var token: String? {
        didSet { if let token { KeychainHelper.save(token) } }
    }

    private init() {
        token = KeychainHelper.load()
    }

    func login(login: String, password: String) async throws -> AuthUser {
        var request = URLRequest(url: baseURL.appendingPathComponent("/api/auth/login"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["login": login, "password": password])

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard http.statusCode == 200 else {
            throw APIError.server(status: http.statusCode, message: Self.errorMessage(from: data, status: http.statusCode))
        }
        let decoded = try decode(LoginResponse.self, from: data)
        self.token = decoded.token
        return decoded.user
    }

    func fetchMe() async throws -> AuthUser {
        try await authorizedGet("/api/auth/me")
    }

    func logout() {
        token = nil
        KeychainHelper.clear()
    }

    /// Generic authenticated GET, for screens added later.
    func authorizedGet<T: Decodable>(_ path: String, query: [String: String] = [:]) async throws -> T {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)
        if !query.isEmpty {
            components?.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = components?.url else { throw APIError.invalidResponse }

        var request = URLRequest(url: url)
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard http.statusCode == 200 else {
            throw APIError.server(status: http.statusCode, message: Self.errorMessage(from: data, status: http.statusCode))
        }
        return try decode(T.self, from: data)
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        do {
            return try JSONDecoder().decode(type, from: data)
        } catch {
            throw APIError.decoding
        }
    }

    private static func errorMessage(from data: Data, status: Int) -> String {
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let detail = obj["detail"] as? String {
                if detail == "invalid_credentials" { return "Неверный логин или пароль" }
                return detail
            }
        }
        if status == 401 { return "Неверный логин или пароль" }
        return "Ошибка сервера (\(status))"
    }
}
