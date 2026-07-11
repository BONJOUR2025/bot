# TODOS.md

## `/admin/payroll-summary` hangs forever at 75% — amoCRM metrics requests never resolve

**What:** The "Сводный отчёт по ФОТ" (payroll summary) page always gets stuck at "3 из 4
категорий готово" (75%), permanently showing "Менеджеры: Загружаю…". Reproduced 3x across
fresh page loads (immediate, 5s wait, 20s wait) — always the exact same stuck state.

**Root cause (confirmed via network inspection):** 4 requests to
`/api/manager-salary/metrics?date_from=...&date_to=...&amo_user_id=...` (one per manager ×
per period) sit in `pending` state and never complete — no error, no timeout, just hangs.
This endpoint calls out to amoCRM (`app/services/...`, see CLAUDE.md: "amoCRM (manager
salary)"). Likely an expired/invalid amoCRM token (CLAUDE.md notes amoCRM tokens
auto-refresh and get written back to `.env`) or amoCRM itself not responding — the backend
call has no apparent timeout, so the frontend waits forever with no error state.

**Why it matters:** Whoever needs this report (payroll/finance) currently cannot ever
generate it — not a slow report, a permanently broken one, with no error message telling
them why.

**Files:** `app/services/` (amoCRM client + manager-salary metrics), backend only —
no frontend/CSS fix applies here.

**Context:** Found via full-site `/design-review` visual sweep (`/admin/payroll-summary`),
2026-07-11. Out of scope for a visual-only pass — needs backend investigation (amoCRM
token/timeout) as a separate task.

**Depends on / blocked by:** None, but needs someone who can check/refresh amoCRM
credentials.

---

## ~~Fix `fmtMoney` decimal rounding in SalaryUI.jsx~~ — DONE (2026-07-11)

Fixed in commit `cbfa264`: shared `fmtMoney` helper in
`admin_frontend/src/components/ui/SalaryUI.jsx` didn't round before formatting, so summed
backend values showed inconsistent, ugly decimals (e.g. "120 160,634 ₽" instead of
"120 161 ₽"). Found via `/design-review` on the live ФОТ по салонам page. Deployed to
production via `deploy.ps1` and verified live.

---

## ~~Fix `btn-primary` typo repo-wide~~ — DONE (2026-07-11)

Fixed in commit `6d2d211`: all 12 remaining files (`AiCheckPanel.jsx`, `IntegrationsModal.jsx`,
`KnowledgeBaseModal.jsx`, `StrategyModal.jsx`, `VacancyModal.jsx`, `Assets.jsx`, `Payouts.jsx`,
`Recruitment.jsx`, `SaleTransfers.jsx`, `Salons.jsx`, `Schedule.jsx`, `Vacations.jsx`) renamed
`btn-primary` → `btn--primary`. Build verified clean (`npm run build`).

---

## Write DESIGN.md

**What:** Document the design system that already exists in practice across the admin frontend:
CSS custom properties for theming (`--color-primary`, `--color-muted-foreground`, etc.), the
`.app-card` / `.btn` / `.btn--{primary,secondary,sm,md,lg}` / `.input` component classes, the
KPI-stat-card pattern (icon + colored left border + label + value), and the loading/error/empty
state conventions (`SkeletonTable`, inline error banners, icon + copy + CTA empty states).

**Why:** New pages (Receivables.jsx, AgbisUsers.jsx, PayrollBySalon.jsx, Clients.jsx, added in
`claude/init-wmebv3`) already follow this system consistently, but nothing captures it in
writing — future pages depend on tribal knowledge / copy-pasting an existing page correctly.

**Pros:** Makes the existing consistency durable instead of accidental. Gives future design
reviews (`/plan-design-review`) a concrete baseline to check against instead of "no DESIGN.md
found."

**Cons:** Documentation effort with no functional payoff by itself.

**Context:** Surfaced during Pass 5 (Design System Alignment) of `/plan-design-review` on
`claude/init-wmebv3`. Recommended as a separate `/design-consultation` run rather than bundling
into this branch.

**Depends on / blocked by:** None.
