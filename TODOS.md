# TODOS.md

## Fix `btn-primary` typo repo-wide (single-hyphen vs `.btn--primary`)

**What:** `globals.css` only defines `.btn--primary` (BEM double-hyphen). ~10 pre-existing files
use `btn btn-primary` (single hyphen), which resolves to no matching rule — those buttons render
as plain `.btn` (neutral gray) instead of the primary gradient/CTA style.

**Why:** Primary action buttons should be the most visually prominent element on their screen.
Right now they silently fall back to the same styling as secondary/cancel buttons, undermining
visual hierarchy wherever it's used.

**Files affected:** `admin_frontend/src/components/recruitment/AiCheckPanel.jsx`,
`IntegrationsModal.jsx`, `KnowledgeBaseModal.jsx`, `StrategyModal.jsx`, `VacancyModal.jsx`,
`admin_frontend/src/pages/Assets.jsx`, `Payouts.jsx`, `Recruitment.jsx`, `SaleTransfers.jsx`,
`Salons.jsx`, `Schedule.jsx`, `Vacations.jsx`.

**Pros:** One mechanical find-replace (`btn-primary` → `btn--primary`) fixes visual hierarchy
across ~25 buttons app-wide. Low risk — purely a CSS class rename, no logic changes.

**Cons:** Touches many files outside any single feature branch; needs a quick visual smoke-test
after (some buttons that "look fine" today, because a neutral button happens to still be usable,
will visibly change appearance).

**Context:** Found during `/plan-design-review` of the `claude/init-wmebv3` branch, which
introduced the same typo in a new file (`ErrorBoundary.jsx`, fixed directly in that branch).
The other ~10 occurrences pre-date this branch and are out of its scope.

**Depends on / blocked by:** None.

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
