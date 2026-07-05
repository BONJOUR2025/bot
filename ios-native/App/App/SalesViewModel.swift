import SwiftUI

/// One employee's sales for one calendar day — mirrors the row shape
/// returned by GET /api/sales/daily (see app/api/sales.py /
/// FirebirdService.get_daily_sales): repair/cosmetics/shoes are already
/// split into the three business categories, total is their sum.
struct SalesRow: Decodable {
    let date: String
    let code: String
    let description: String?
    let repair: Double
    let cosmetics: Double
    let shoes: Double
    let total: Double
}

private struct EmployeeOut: Decodable {
    let name: String
}

enum SalesCategory: String, CaseIterable, Identifiable, Hashable {
    case repair, cosmetics, shoes
    var id: String { rawValue }

    var label: String {
        switch self {
        case .repair: return "Ремонт / Химчистка"
        case .cosmetics: return "Косметика"
        case .shoes: return "Обувь"
        }
    }

    var color: Color {
        switch self {
        case .repair: return Color(hex: 0x6366f1)
        case .cosmetics: return Color(hex: 0x22c55e)
        case .shoes: return Color(hex: 0xf59e0b)
        }
    }

    func amount(of row: SalesRow) -> Double {
        switch self {
        case .repair: return row.repair
        case .cosmetics: return row.cosmetics
        case .shoes: return row.shoes
        }
    }
}

struct EmployeeTotal: Identifiable {
    let code: String
    var repair: Double = 0
    var cosmetics: Double = 0
    var shoes: Double = 0
    var activeDays: Int = 0
    var id: String { code }
    var total: Double { repair + cosmetics + shoes }

    func amount(for cat: SalesCategory) -> Double {
        switch cat {
        case .repair: return repair
        case .cosmetics: return cosmetics
        case .shoes: return shoes
        }
    }
}

struct DaySlice: Identifiable {
    let date: String
    var byCode: [String: Double]
    var id: String { date }
    var total: Double { byCode.values.reduce(0, +) }
}

struct WeekdayStat: Identifiable {
    let index: Int
    let name: String
    let avg: Double
    let count: Int
    var id: Int { index }
}

/// Palette cycled by leaderboard rank / chart series index — matches
/// admin_frontend/src/pages/SalesAnalytics.jsx's CHART_COLORS so the same
/// employee reads as "the same color" across the web and native app.
let SALES_PALETTE: [Color] = [0x6366f1, 0x22c55e, 0xf59e0b, 0xef4444, 0x3b82f6,
                              0x8b5cf6, 0xec4899, 0x14b8a6, 0xf97316, 0xa3e635].map { Color(hex: $0) }

let RU_WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

@MainActor
final class SalesViewModel: ObservableObject {
    @Published var dateFrom: Date
    @Published var dateTo: Date
    @Published var activeCategories: Set<SalesCategory> = Set(SalesCategory.allCases)
    @Published var highlightedCode: String?

    @Published private(set) var rows: [SalesRow] = []
    @Published private(set) var prevRows: [SalesRow] = []
    @Published private(set) var nameByCode: [String: String] = [:]
    @Published private(set) var isLoading = false
    @Published private(set) var loaded = false
    @Published var errorMessage: String?

    init() {
        let cal = Calendar.current
        let now = Date()
        dateFrom = cal.date(from: cal.dateComponents([.year, .month], from: now)) ?? now
        dateTo = now
    }

    func applyQuickRange(_ key: String) {
        let cal = Calendar.current
        let now = Date()
        let comps = cal.dateComponents([.year, .month], from: now)
        switch key {
        case "month":
            dateFrom = cal.date(from: comps) ?? now
            dateTo = now
        case "prev":
            let firstOfThis = cal.date(from: comps) ?? now
            dateTo = cal.date(byAdding: .day, value: -1, to: firstOfThis) ?? now
            dateFrom = cal.date(from: cal.dateComponents([.year, .month], from: dateTo)) ?? dateTo
        case "quarter":
            let month = (comps.month ?? 1) - 1
            let qStartMonth = (month / 3) * 3 + 1
            dateFrom = cal.date(from: DateComponents(year: comps.year, month: qStartMonth, day: 1)) ?? now
            dateTo = now
        case "year":
            dateFrom = cal.date(from: DateComponents(year: comps.year, month: 1, day: 1)) ?? now
            dateTo = now
        default:
            break
        }
    }

    func toggleCategory(_ cat: SalesCategory) {
        if activeCategories.contains(cat) {
            if activeCategories.count > 1 { activeCategories.remove(cat) }
        } else {
            activeCategories.insert(cat)
        }
    }

    func toggleHighlight(_ code: String) {
        highlightedCode = (highlightedCode == code) ? nil : code
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        let df = Self.iso(dateFrom)
        let dt = Self.iso(dateTo)
        let spanDays = max(Calendar.current.dateComponents([.day], from: dateFrom, to: dateTo).day ?? 0, 0)
        let prevTo = Calendar.current.date(byAdding: .day, value: -1, to: dateFrom) ?? dateFrom
        let prevFrom = Calendar.current.date(byAdding: .day, value: -spanDays, to: prevTo) ?? prevTo

        do {
            async let main: [SalesRow] = APIClient.shared.authorizedGet(
                "/api/sales/daily", query: ["date_from": df, "date_to": dt])
            async let previous: [SalesRow] = APIClient.shared.authorizedGet(
                "/api/sales/daily", query: ["date_from": Self.iso(prevFrom), "date_to": Self.iso(prevTo)])
            async let employees: [EmployeeOut] = APIClient.shared.authorizedGet("/api/employees/", query: ["archived": "false"])

            let (mainRows, prevRowsResult, emps) = try await (main, previous, employees)
            rows = mainRows
            prevRows = prevRowsResult
            nameByCode = Self.buildNameMap(emps)
            loaded = true
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? "Ошибка загрузки"
        }
    }

    func name(for code: String) -> String { nameByCode[code] ?? code }

    // MARK: - Derived data

    private func categoryTotal(_ row: SalesRow) -> Double {
        activeCategories.reduce(0) { $0 + $1.amount(of: row) }
    }

    var kpiTotal: Double { rows.reduce(0) { $0 + categoryTotal($1) } }
    var kpiPrevTotal: Double { prevRows.reduce(0) { $0 + categoryTotal($1) } }
    var kpiDelta: Double? { Self.delta(kpiTotal, kpiPrevTotal) }

    func kpi(for cat: SalesCategory) -> Double {
        rows.reduce(0) { $0 + cat.amount(of: $1) }
    }
    func kpiPrev(for cat: SalesCategory) -> Double {
        prevRows.reduce(0) { $0 + cat.amount(of: $1) }
    }
    func kpiDelta(for cat: SalesCategory) -> Double? {
        Self.delta(kpi(for: cat), kpiPrev(for: cat))
    }

    var employeeTotals: [EmployeeTotal] {
        var map: [String: EmployeeTotal] = [:]
        for row in rows {
            var t = map[row.code] ?? EmployeeTotal(code: row.code)
            t.repair += row.repair
            t.cosmetics += row.cosmetics
            t.shoes += row.shoes
            if categoryTotal(row) > 0 { t.activeDays += 1 }
            map[row.code] = t
        }
        return map.values.sorted { $0.total > $1.total }
    }

    var dailySeries: [DaySlice] {
        var byDate: [String: [String: Double]] = [:]
        for row in rows {
            byDate[row.date, default: [:]][row.code, default: 0] += categoryTotal(row)
        }
        return byDate.keys.sorted().map { DaySlice(date: $0, byCode: byDate[$0] ?? [:]) }
    }

    var topEmployeeCodes: [String] {
        Array(employeeTotals.prefix(6).map(\.code))
    }

    var categoryBreakdown: [(SalesCategory, Double)] {
        SalesCategory.allCases.map { ($0, kpi(for: $0)) }.filter { $0.1 > 0 }
    }

    var weekdayStats: [WeekdayStat] {
        var totals = Array(repeating: 0.0, count: 7)
        var counts = Array(repeating: 0, count: 7)
        let formatter = Self.dayFormatter
        for row in rows {
            guard let d = formatter.date(from: row.date) else { continue }
            let idx = (Calendar.current.component(.weekday, from: d) + 5) % 7
            totals[idx] += categoryTotal(row)
            counts[idx] += 1
        }
        return (0..<7).map { i in
            WeekdayStat(index: i, name: RU_WEEKDAYS[i], avg: counts[i] > 0 ? totals[i] / Double(counts[i]) : 0, count: counts[i])
        }
    }

    var activeDaysCount: Int { Set(rows.filter { categoryTotal($0) > 0 }.map(\.date)).count }
    var avgPerActiveDay: Double { activeDaysCount > 0 ? kpiTotal / Double(activeDaysCount) : 0 }

    // MARK: - Helpers

    private static func delta(_ cur: Double, _ prev: Double) -> Double? {
        guard prev > 0 else { return nil }
        return (cur - prev) / prev * 100
    }

    private static func buildNameMap(_ employees: [EmployeeOut]) -> [String: String] {
        var map: [String: String] = [:]
        for emp in employees {
            guard let match = emp.name.range(of: #"^(.*?)\s*(\d{4})$"#, options: .regularExpression) else { continue }
            let matched = String(emp.name[match])
            guard let codeRange = matched.range(of: #"\d{4}$"#, options: .regularExpression) else { continue }
            let code = String(matched[codeRange])
            let display = matched[..<codeRange.lowerBound].trimmingCharacters(in: .whitespaces)
            map[code] = display.isEmpty ? emp.name : display
        }
        return map
    }

    private static let dayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.calendar = Calendar(identifier: .gregorian)
        f.timeZone = TimeZone(identifier: "Europe/Moscow")
        return f
    }()

    private static func iso(_ date: Date) -> String { dayFormatter.string(from: date) }
}

extension Color {
    init(hex: UInt32) {
        let r = Double((hex >> 16) & 0xff) / 255
        let g = Double((hex >> 8) & 0xff) / 255
        let b = Double(hex & 0xff) / 255
        self.init(red: r, green: g, blue: b)
    }
}

func fmtRub(_ v: Double) -> String {
    let rounded = Int(v.rounded())
    let formatter = NumberFormatter()
    formatter.numberStyle = .decimal
    formatter.groupingSeparator = " "
    return (formatter.string(from: NSNumber(value: rounded)) ?? "\(rounded)") + " ₽"
}

func fmtK(_ v: Double) -> String {
    if v >= 1_000_000 { return String(format: "%.1f млн ₽", v / 1_000_000) }
    if v >= 1_000 { return String(format: "%.0fk ₽", v / 1_000) }
    return "\(Int(v.rounded())) ₽"
}

func initials(_ name: String) -> String {
    let parts = name.split(separator: " ")
    if parts.count > 1 { return String(parts[0].prefix(1) + parts[1].prefix(1)).uppercased() }
    return String(name.prefix(2)).uppercased()
}
