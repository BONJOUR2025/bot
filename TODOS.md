# TODOS.md

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
