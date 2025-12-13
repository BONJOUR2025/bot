# Admin frontend

This React 19 + Vite app uses Tailwind CSS 3.4.x and React Router 7. It is configured to build under `/admin/` and proxies API requests to the FastAPI backend during local development.

## Path alias `@`

Shadcn/ui components and the rest of the app can import modules using the `@/` prefix:

- `vite.config.js` maps `@` to `./src`.
- `jsconfig.json` provides editor support for the same alias.

## Shadcn/ui bootstrap (Tailwind v3)

The project is on Tailwind CSS **3.x**, so use the Tailwind v3-compatible shadcn CLI (for example `shadcn@2.3.0`). In `admin_frontend/`:

1. Initialize shadcn/ui:
   ```bash
   npx shadcn@2.3.0 init
   ```
   This creates `components.json`, installs dependencies, and scaffolds the theme and `cn` utility.

2. Add commonly used components for the dashboard, employees, and requests screens:
   ```bash
   npx shadcn@2.3.0 add button card badge table
   npx shadcn@2.3.0 add input label textarea select
   npx shadcn@2.3.0 add dialog dropdown-menu tabs
   npx shadcn@2.3.0 add toast sonner
   npx shadcn@2.3.0 add form
   ```

3. Replace plain elements incrementally (e.g., `<button>` → `<Button variant="...">`) without changing handlers or business logic. React Hook Form can be wrapped with shadcn `Form` components for minimal code changes.

If you upgrade Tailwind to v4 in the future, switch to the latest `shadcn` CLI per the official Vite/Tailwind v4 instructions.
