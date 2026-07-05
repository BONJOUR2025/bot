import SwiftUI
import Charts

/// Fully native replacement for admin_frontend/src/pages/SalesAnalytics.jsx —
/// same backend endpoints (/api/sales/daily, /api/employees/), same business
/// categories and color palette, but rendered with Swift Charts instead of
/// Recharts-in-a-WebView: GPU-accelerated, scrubbable, and free of the
/// dropdown/stacking-context bugs the web version needed a portal to work
/// around. First fully-built screen in ios-native (see PlaceholderView for
/// the rest, still pending).
struct SalesView: View {
    @StateObject private var vm = SalesViewModel()
    @State private var tab = 0

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                filtersCard

                if let error = vm.errorMessage {
                    Text(error)
                        .font(.subheadline)
                        .foregroundStyle(.red)
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(.red.opacity(0.1), in: RoundedRectangle(cornerRadius: 12))
                }

                if vm.isLoading && !vm.loaded {
                    ProgressView("Загрузка…").frame(maxWidth: .infinity).padding(.top, 40)
                } else if vm.loaded {
                    kpiRow

                    Picker("", selection: $tab) {
                        Text("Обзор").tag(0)
                        Text("Сотрудники").tag(1)
                        Text("Сводная").tag(2)
                    }
                    .pickerStyle(.segmented)

                    switch tab {
                    case 0: overviewTab
                    case 1: employeesTab
                    default: detailsTab
                    }
                }
            }
            .padding(16)
        }
        .navigationTitle("Продажи")
        .navigationBarTitleDisplayMode(.inline)
        .background(Color(.systemGroupedBackground))
        .task { if !vm.loaded { await vm.load() } }
        .refreshable { await vm.load() }
    }

    // MARK: - Filters

    private var filtersCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    quickButton("Этот месяц", "month")
                    quickButton("Прошлый мес.", "prev")
                    quickButton("Квартал", "quarter")
                    quickButton("Год", "year")
                }
            }
            HStack(spacing: 12) {
                DatePicker("От", selection: $vm.dateFrom, displayedComponents: .date)
                    .datePickerStyle(.compact)
                DatePicker("До", selection: $vm.dateTo, displayedComponents: .date)
                    .datePickerStyle(.compact)
            }
            .font(.subheadline)
            .onChange(of: vm.dateFrom) { Task { await vm.load() } }
            .onChange(of: vm.dateTo) { Task { await vm.load() } }

            HStack(spacing: 8) {
                ForEach(SalesCategory.allCases) { cat in
                    let on = vm.activeCategories.contains(cat)
                    Button {
                        withAnimation(.snappy) { vm.toggleCategory(cat) }
                    } label: {
                        Text(cat.label)
                            .font(.caption.weight(.semibold))
                            .padding(.horizontal, 10).padding(.vertical, 6)
                            .background(on ? cat.color.opacity(0.18) : Color(.secondarySystemBackground), in: Capsule())
                            .foregroundStyle(on ? cat.color : .secondary)
                            .overlay(Capsule().stroke(on ? cat.color : .clear, lineWidth: 1))
                    }
                }
                Spacer()
                if vm.isLoading {
                    ProgressView().scaleEffect(0.8)
                }
            }
        }
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }

    private func quickButton(_ label: String, _ key: String) -> some View {
        Button {
            vm.applyQuickRange(key)
            Task { await vm.load() }
        } label: {
            Text(label)
                .font(.caption.weight(.medium))
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(Color(.tertiarySystemBackground), in: Capsule())
        }
    }

    // MARK: - KPI row

    private var kpiRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                KpiCard(label: "Итого выручка", value: fmtK(vm.kpiTotal), delta: vm.kpiDelta,
                        sub: "∅ \(fmtK(vm.avgPerActiveDay)) / дн.", accent: .indigo, symbol: "chart.bar.fill")
                ForEach(SalesCategory.allCases) { cat in
                    KpiCard(label: cat.label, value: fmtK(vm.kpi(for: cat)), delta: vm.kpiDelta(for: cat),
                            sub: nil, accent: cat.color, symbol: nil)
                }
            }
        }
    }

    // MARK: - Overview

    private var overviewTab: some View {
        VStack(spacing: 16) {
            if !vm.dailySeries.isEmpty {
                RevenueChartCard(vm: vm)
            }
            if !vm.categoryBreakdown.isEmpty {
                DonutCard(vm: vm)
            }
            if vm.weekdayStats.contains(where: { $0.count > 0 }) {
                WeekdayChartCard(stats: vm.weekdayStats)
            }
            if !vm.employeeTotals.isEmpty {
                Top3Card(vm: vm)
            }
        }
    }

    // MARK: - Employees

    private var employeesTab: some View {
        VStack(spacing: 16) {
            if vm.employeeTotals.isEmpty {
                emptyState
            } else {
                LeaderboardCard(vm: vm)
                EmployeeBarChartCard(vm: vm)
            }
        }
    }

    // MARK: - Details

    private var detailsTab: some View {
        vm.dailySeries.isEmpty ? AnyView(emptyState) : AnyView(DetailsGridCard(vm: vm))
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "chart.bar.xaxis")
                .font(.system(size: 34))
                .foregroundStyle(.tertiary)
            Text("Нет данных за выбранный период").foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }
}

// MARK: - KPI card

private struct KpiCard: View {
    let label: String
    let value: String
    let delta: Double?
    let sub: String?
    let accent: Color
    let symbol: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                if let symbol { Image(systemName: symbol).font(.caption).foregroundStyle(accent) }
                Text(label.uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.secondary)
            }
            Text(value)
                .font(.title3.weight(.bold))
                .foregroundStyle(accent)
                .contentTransition(.numericText())
            HStack(spacing: 4) {
                if let delta, abs(delta) >= 0.1 {
                    Label(String(format: "%@%.1f%%", delta > 0 ? "+" : "", delta), systemImage: delta > 0 ? "arrow.up.right" : "arrow.down.right")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(delta > 0 ? .green : .red)
                }
                if let sub {
                    Text(sub).font(.system(size: 10)).foregroundStyle(.secondary)
                }
            }
        }
        .padding(12)
        .frame(width: 148, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(accent.opacity(0.25), lineWidth: 1))
        .overlay(alignment: .leading) {
            RoundedRectangle(cornerRadius: 2).fill(accent).frame(width: 3).padding(.vertical, 10)
        }
        .animation(.snappy, value: value)
    }
}

// MARK: - Revenue chart (interactive scrub)

private struct RevenueChartCard: View {
    @ObservedObject var vm: SalesViewModel
    @State private var selectedDate: String?

    private var topCodes: [String] { vm.topEmployeeCodes }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Динамика продаж").font(.headline)
                Spacer()
                Text("\(vm.dailySeries.count) дн.").font(.caption).foregroundStyle(.secondary)
            }

            Chart {
                seriesMarks
                selectionRule
            }
            .chartForegroundStyleScale(range: SALES_PALETTE)
            .chartLegend(position: .bottom, spacing: 6)
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 5)) { _ in
                    AxisGridLine()
                }
            }
            .chartYAxis {
                AxisMarks { value in
                    AxisGridLine()
                    AxisValueLabel {
                        if let d = value.as(Double.self) { Text(fmtK(d)) }
                    }
                }
            }
            .frame(height: 240)
            .chartOverlay { proxy in
                GeometryReader { geo in
                    Rectangle().fill(.clear).contentShape(Rectangle())
                        .gesture(DragGesture(minimumDistance: 0).onChanged { value in
                            let x = value.location.x - geo[proxy.plotAreaFrame].origin.x
                            if let date: String = proxy.value(atX: x) {
                                selectedDate = date
                            }
                        }.onEnded { _ in selectedDate = nil })
                }
            }
        }
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }

    @ChartContentBuilder
    private var seriesMarks: some ChartContent {
        ForEach(topCodes, id: \.self) { code in
            ForEach(vm.dailySeries) { day in
                AreaMark(
                    x: .value("Дата", day.date),
                    y: .value("Сумма", day.byCode[code] ?? 0)
                )
                .foregroundStyle(by: .value("Сотрудник", vm.name(for: code)))
                .interpolationMethod(.catmullRom)
                .opacity(vm.highlightedCode == nil || vm.highlightedCode == code ? 0.55 : 0.08)
                LineMark(
                    x: .value("Дата", day.date),
                    y: .value("Сумма", day.byCode[code] ?? 0)
                )
                .foregroundStyle(by: .value("Сотрудник", vm.name(for: code)))
                .interpolationMethod(.catmullRom)
                .lineStyle(StrokeStyle(lineWidth: 2))
                .opacity(vm.highlightedCode == nil || vm.highlightedCode == code ? 1 : 0.12)
            }
        }
    }

    @ChartContentBuilder
    private var selectionRule: some ChartContent {
        if let selectedDate, let slice = vm.dailySeries.first(where: { $0.date == selectedDate }) {
            RuleMark(x: .value("Дата", selectedDate))
                .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                .foregroundStyle(.secondary)
                .annotation(position: .top, alignment: .center, spacing: 4) {
                    ScrubTooltip(vm: vm, slice: slice)
                }
        }
    }
}

private struct ScrubTooltip: View {
    @ObservedObject var vm: SalesViewModel
    let slice: DaySlice

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(slice.date).font(.caption.weight(.semibold))
            ForEach(vm.topEmployeeCodes.prefix(4), id: \.self) { code in
                if let v = slice.byCode[code], v > 0 {
                    HStack(spacing: 4) {
                        Text(vm.name(for: code)).font(.caption2).foregroundStyle(.secondary)
                        Text(fmtK(v)).font(.caption2.weight(.semibold))
                    }
                }
            }
        }
        .padding(8)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
        .shadow(radius: 4)
    }
}

// MARK: - Donut

private struct DonutCard: View {
    @ObservedObject var vm: SalesViewModel
    @State private var selectedAngle: Double?

    private var selectedCategory: SalesCategory? {
        guard let selectedAngle else { return nil }
        var cumulative: Double = 0
        for (cat, value) in vm.categoryBreakdown {
            cumulative += value
            if selectedAngle <= cumulative { return cat }
        }
        return nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Структура выручки").font(.headline)
            Text("\(fmtK(vm.kpiTotal)) · \(vm.activeDaysCount) дн.")
                .font(.caption).foregroundStyle(.secondary)

            Chart(vm.categoryBreakdown, id: \.0) { cat, value in
                SectorMark(
                    angle: .value("Сумма", value),
                    innerRadius: .ratio(0.62),
                    outerRadius: selectedCategory == cat ? .ratio(1.0) : .ratio(0.92),
                    angularInset: 1.5
                )
                .foregroundStyle(cat.color)
                .opacity(selectedCategory == nil || selectedCategory == cat ? 1 : 0.35)
                .cornerRadius(4)
            }
            .chartAngleSelection(value: $selectedAngle)
            .frame(height: 180)
            .animation(.snappy, value: selectedAngle)

            VStack(spacing: 6) {
                ForEach(vm.categoryBreakdown, id: \.0) { cat, value in
                    let pct = vm.kpiTotal > 0 ? value / vm.kpiTotal * 100 : 0
                    HStack {
                        Circle().fill(cat.color).frame(width: 8, height: 8)
                        Text(cat.label).font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Text(String(format: "%.0f%%", pct)).font(.caption.weight(.semibold))
                        Text(fmtK(value)).font(.caption).foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 3).padding(.horizontal, 6)
                    .background(selectedCategory == cat ? cat.color.opacity(0.12) : .clear, in: RoundedRectangle(cornerRadius: 8))
                }
            }
        }
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }
}

// MARK: - Weekday heatmap

private struct WeekdayChartCard: View {
    let stats: [WeekdayStat]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: "calendar").foregroundStyle(.secondary)
                Text("По дням недели").font(.headline)
                Text("ср. выручка").font(.caption2).foregroundStyle(.secondary)
            }
            Chart(stats) { s in
                BarMark(x: .value("День", s.name), y: .value("Сумма", s.avg))
                    .foregroundStyle(s.index >= 5 ? Gradient(colors: [Color(hex: 0xfcd34d), Color(hex: 0xf59e0b)]) : Gradient(colors: [Color(hex: 0xa5b4fc), Color(hex: 0x6366f1)]))
                    .cornerRadius(4)
                    .annotation(position: .top) {
                        if s.count > 0 { Text(fmtK(s.avg)).font(.system(size: 9)).foregroundStyle(.secondary) }
                    }
            }
            .frame(height: 130)
        }
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }
}

// MARK: - Top 3

private struct Top3Card: View {
    @ObservedObject var vm: SalesViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: "trophy.fill").foregroundStyle(.yellow)
                Text("Топ-3").font(.headline)
            }
            let top = Array(vm.employeeTotals.prefix(3).enumerated())
            let maxTotal = vm.employeeTotals.first?.total ?? 1
            ForEach(top, id: \.element.code) { i, e in
                HStack(spacing: 10) {
                    Text(["🥇", "🥈", "🥉"][i]).font(.title3)
                    EmployeeAvatar(name: vm.name(for: e.code), color: SALES_PALETTE[i % SALES_PALETTE.count], size: 30)
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(vm.name(for: e.code)).font(.subheadline.weight(.semibold)).lineLimit(1)
                            Spacer()
                            Text(fmtK(e.total)).font(.subheadline.weight(.bold)).foregroundStyle(SALES_PALETTE[i % SALES_PALETTE.count])
                        }
                        ProgressView(value: maxTotal > 0 ? e.total / maxTotal : 0)
                            .tint(SALES_PALETTE[i % SALES_PALETTE.count])
                    }
                }
            }
        }
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }
}

// MARK: - Leaderboard

private struct LeaderboardCard: View {
    @ObservedObject var vm: SalesViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Image(systemName: "trophy.fill").foregroundStyle(.yellow)
                Text("Рейтинг сотрудников").font(.headline)
                Spacer()
                Text("\(vm.employeeTotals.count) чел.").font(.caption).foregroundStyle(.secondary)
            }
            .padding(14)
            Divider()
            let maxTotal = vm.employeeTotals.first?.total ?? 1
            ForEach(Array(vm.employeeTotals.enumerated()), id: \.element.code) { i, e in
                Button {
                    withAnimation(.snappy) { vm.toggleHighlight(e.code) }
                } label: {
                    HStack(spacing: 10) {
                        Text(i < 3 ? ["🥇", "🥈", "🥉"][i] : "\(i + 1)")
                            .font(i < 3 ? .title3 : .subheadline.weight(.semibold))
                            .foregroundStyle(.secondary)
                            .frame(width: 26)
                        EmployeeAvatar(name: vm.name(for: e.code), color: SALES_PALETTE[i % SALES_PALETTE.count], size: 34)
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text(vm.name(for: e.code)).font(.subheadline.weight(.semibold)).lineLimit(1)
                                Spacer()
                                Text(fmtK(e.total)).font(.subheadline.weight(.bold)).foregroundStyle(SALES_PALETTE[i % SALES_PALETTE.count])
                            }
                            ProgressView(value: maxTotal > 0 ? e.total / maxTotal : 0)
                                .tint(SALES_PALETTE[i % SALES_PALETTE.count])
                            CategoryStripe(e: e)
                        }
                    }
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    .background(vm.highlightedCode == e.code ? Color.accentColor.opacity(0.1) : .clear)
                }
                .buttonStyle(.plain)
                if e.code != vm.employeeTotals.last?.code { Divider().padding(.leading, 60) }
            }
        }
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }
}

private struct CategoryStripe: View {
    let e: EmployeeTotal
    var body: some View {
        GeometryReader { geo in
            let total = max(e.total, 0.0001)
            HStack(spacing: 1) {
                Color(hex: 0x6366f1).frame(width: geo.size.width * e.repair / total)
                Color(hex: 0x22c55e).frame(width: geo.size.width * e.cosmetics / total)
                Color(hex: 0xf59e0b).frame(width: geo.size.width * e.shoes / total)
            }
            .clipShape(Capsule())
        }
        .frame(height: 4)
    }
}

private struct EmployeeAvatar: View {
    let name: String
    let color: Color
    let size: CGFloat
    var body: some View {
        Circle().fill(color)
            .frame(width: size, height: size)
            .overlay(Text(initials(name)).font(.system(size: size * 0.34, weight: .bold)).foregroundStyle(.white))
    }
}

// MARK: - Employee stacked bar chart

private struct EmployeeBarChartCard: View {
    @ObservedObject var vm: SalesViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Сравнение по категориям").font(.headline)
            Chart {
                ForEach(vm.employeeTotals) { e in
                    ForEach(SalesCategory.allCases.filter { vm.activeCategories.contains($0) }) { cat in
                        BarMark(
                            x: .value("Сумма", e.amount(for: cat)),
                            y: .value("Сотрудник", vm.name(for: e.code))
                        )
                        .foregroundStyle(by: .value("Категория", cat.label))
                    }
                }
            }
            .chartForegroundStyleScale([
                SalesCategory.repair.label: SalesCategory.repair.color,
                SalesCategory.cosmetics.label: SalesCategory.cosmetics.color,
                SalesCategory.shoes.label: SalesCategory.shoes.color,
            ])
            .chartLegend(position: .bottom)
            .frame(height: CGFloat(max(180, vm.employeeTotals.count * 46)))
        }
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }
}

// MARK: - Details grid (native Grid — no web equivalent this clean)

private struct DetailsGridCard: View {
    @ObservedObject var vm: SalesViewModel

    private var codes: [String] { vm.topEmployeeCodes }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Сводная таблица").font(.headline)
                Spacer()
                Text("\(vm.dailySeries.count) дн.").font(.caption).foregroundStyle(.secondary)
            }
            ScrollView(.horizontal, showsIndicators: true) {
                Grid(alignment: .trailing, horizontalSpacing: 14, verticalSpacing: 8) {
                    GridRow {
                        Text("Период").gridColumnAlignment(.leading).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        ForEach(codes, id: \.self) { code in
                            Text(vm.name(for: code)).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        }
                        Text("Итого").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    }
                    Divider().gridCellColumns(codes.count + 2)
                    ForEach(vm.dailySeries) { day in
                        GridRow {
                            Text(day.date.suffix(5)).font(.caption).gridColumnAlignment(.leading)
                            ForEach(codes, id: \.self) { code in
                                let v = day.byCode[code] ?? 0
                                Text(v == 0 ? "—" : "\(Int(v.rounded()))")
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(v == 0 ? .tertiary : .primary)
                            }
                            Text("\(Int(day.total.rounded()))").font(.caption.weight(.bold).monospacedDigit())
                        }
                    }
                    Divider().gridCellColumns(codes.count + 2)
                    GridRow {
                        Text("Итого").font(.caption.weight(.bold)).gridColumnAlignment(.leading)
                        ForEach(codes, id: \.self) { code in
                            let total = vm.dailySeries.reduce(0.0) { $0 + ($1.byCode[code] ?? 0) }
                            Text("\(Int(total.rounded()))").font(.caption.weight(.bold).monospacedDigit())
                        }
                        Text("\(Int(vm.dailySeries.reduce(0.0) { $0 + $1.total }.rounded()))")
                            .font(.caption.weight(.bold).monospacedDigit())
                            .foregroundStyle(Color.accentColor)
                    }
                }
                .padding(.bottom, 4)
            }
        }
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }
}
