import SwiftUI

private struct NavItem: Identifiable {
    let id = UUID()
    let title: String
    let systemImage: String
}

private struct NavSection: Identifiable {
    let id = UUID()
    let title: String
    let items: [NavItem]
}

/// Mirrors admin_frontend/src/components/Navigation.jsx's category
/// structure — same section names, so this reads as "the same app" to
/// someone who already knows the web admin. Every destination is a
/// PlaceholderView for now (see the chat: skeleton-first, screens later).
private let sections: [NavSection] = [
    NavSection(title: "Обзор", items: [
        NavItem(title: "Дашборд", systemImage: "square.grid.2x2"),
    ]),
    NavSection(title: "Сотрудники", items: [
        NavItem(title: "Сотрудники", systemImage: "person.2"),
        NavItem(title: "Подбор персонала", systemImage: "person.badge.plus"),
        NavItem(title: "Архив", systemImage: "archivebox"),
        NavItem(title: "Дни рождения", systemImage: "birthday.cake"),
        NavItem(title: "Имущество", systemImage: "shippingbox"),
    ]),
    NavSection(title: "Учёт времени и отсутствий", items: [
        NavItem(title: "Расписание", systemImage: "calendar"),
        NavItem(title: "Отпуска", systemImage: "sun.max"),
        NavItem(title: "Заявки на отгул", systemImage: "calendar.badge.minus"),
        NavItem(title: "Рабочее время", systemImage: "clock"),
    ]),
    NavSection(title: "Точки и продажи", items: [
        NavItem(title: "Салоны", systemImage: "storefront"),
        NavItem(title: "Счётчик посетителей", systemImage: "person.3"),
        NavItem(title: "Продажи", systemImage: "chart.line.uptrend.xyaxis"),
        NavItem(title: "Планы продаж", systemImage: "mappin.and.ellipse"),
        NavItem(title: "Перемещение продажи", systemImage: "arrow.left.arrow.right"),
    ]),
    NavSection(title: "Зарплата", items: [
        NavItem(title: "Сводный отчёт", systemImage: "chart.bar.doc.horizontal"),
        NavItem(title: "Администраторы", systemImage: "person.crop.circle"),
        NavItem(title: "Мастера", systemImage: "hammer"),
        NavItem(title: "Менеджеры", systemImage: "person.2.badge.gearshape"),
        NavItem(title: "Курьер", systemImage: "shippingbox.and.arrow.backward"),
    ]),
    NavSection(title: "Выплаты", items: [
        NavItem(title: "Выплаты", systemImage: "banknote"),
        NavItem(title: "Контроль выплат", systemImage: "checkmark.seal"),
        NavItem(title: "Штрафы и премии", systemImage: "star"),
    ]),
    NavSection(title: "Прочее", items: [
        NavItem(title: "Рассылка", systemImage: "megaphone"),
        NavItem(title: "Кассовые перемещения", systemImage: "arrow.left.arrow.right.circle"),
        NavItem(title: "Платёжный календарь", systemImage: "calendar.badge.clock"),
        NavItem(title: "Задачи", systemImage: "checklist"),
        NavItem(title: "Настройки", systemImage: "gearshape"),
    ]),
]

struct MainShellView: View {
    @EnvironmentObject private var auth: AuthViewModel

    var body: some View {
        NavigationStack {
            List {
                ForEach(sections) { section in
                    Section(section.title) {
                        ForEach(section.items) { item in
                            NavigationLink(value: item.title) {
                                Label(item.title, systemImage: item.systemImage)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Центр управления")
            .navigationDestination(for: String.self) { title in
                if title == "Продажи" {
                    SalesView()
                } else {
                    PlaceholderView(title: title)
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        if let name = auth.user?.displayName ?? auth.user?.login {
                            Text(name)
                        }
                        Button("Выход", role: .destructive) { auth.logout() }
                    } label: {
                        Image(systemName: "person.crop.circle")
                    }
                }
            }
        }
    }
}
