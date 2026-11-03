# CLAUDE.md

Factory Inventory Management System Demo with GitHub integration - Full-stack application with Vue 3 frontend, Python FastAPI backend, and in-memory mock data (no database).

> ⚠️ **This repository and any fork you create are PUBLIC.** Do not commit credentials, internal hostnames, or private registry URLs. `client/.npmrc` pins the public npm registry and `client/package-lock.json` is gitignored to prevent locally-configured registries from leaking into commits — leave both in place.

## Critical Tool Usage Rules

### Subagents
Use the Task tool with these specialized subagents for appropriate tasks:

- **vue-expert**: Use for Vue 3 frontend features, UI components, styling, and client-side functionality
  - Examples: Creating components, fixing reactivity issues, performance optimization, complex state management
  - **MANDATORY RULE: ANY time you need to create or significantly modify a .vue file, you MUST delegate to vue-expert**
- **code-reviewer**: Use after writing significant code to review quality and best practices
- **Explore**: Use for understanding codebase structure, searching for patterns, or answering questions about how components work
- **general-purpose**: Use for complex multi-step tasks or when other agents don't fit

### Skills
- **backend-api-test** skill: Use when writing or modifying tests in `tests/backend` directory with pytest and FastAPI TestClient

### MCP Tools
- **ALWAYS use GitHub MCP tools** (`mcp__github__*`) for ALL GitHub operations
  - Exception: Local branches only - use `git checkout -b` instead of `mcp__github__create_branch`
- **ALWAYS use Playwright MCP tools** (`mcp__playwright__*`) for browser testing
  - Test against: `http://localhost:3000` (frontend), `http://localhost:8001` (API)

## Stack
- **Frontend**: Vue 3 + Composition API + Vite (port 3000)
- **Backend**: Python FastAPI (port 8001)
- **Data**: JSON files in `server/data/` loaded via `server/mock_data.py`

## Commands

```bash
./scripts/start.sh | ./scripts/stop.sh        # Both servers (bash; on Windows use the manual commands below)
cd server && uv sync                           # Install backend deps (incl. dev deps)
cd tests && uv run --project ../server pytest                      # All backend tests (pytest.ini lives in tests/)
cd tests && uv run --project ../server pytest backend/test_inventory.py::test_name   # Single test
cd client && npm run build                     # Production build (no lint or frontend tests exist)
```

API docs: http://localhost:8001/docs

## Quick Start

```bash
# Backend
cd server
uv run python main.py

# Frontend
cd client
npm install && npm run dev
```

## Key Patterns

**Filter System**: 4 filters (Time Period, Warehouse, Category, Order Status) apply to all data via query params
**Data Flow**: Vue filters → `client/src/api.js` → FastAPI → In-memory filtering → Pydantic validation → Computed properties
**Reactivity**: Raw data in refs (`allOrders`, `inventoryItems`), derived data in computed properties

## Architecture Notes

- **Backend**: `server/main.py` holds all routes, Pydantic models, and filter helpers (`apply_filters` for warehouse/category/status, `filter_by_month` for month or `Q1-2025`-style quarters). `QUARTER_MAP` is hard-coded to 2025. Month filtering matches on the `order_date` field, which is why inventory has no month filter.
- **Data**: `server/mock_data.py` loads every JSON file once at import into module-level lists. `server/generate_data.py` regenerates sample data. Edits to JSON need a server restart.
- **Tests**: `tests/backend/conftest.py` puts `server/` on `sys.path` and imports `app` directly, so tests run against the real JSON data.
- **Frontend**: Routes are declared in `client/src/main.js`. `App.vue` renders a global `FilterBar` above `<router-view />`. Filter state is shared through the `useFilters` composable and passed to `api.js`, which skips params set to `'all'`.
- **API base URL** is hard-coded to `http://localhost:8001/api` in `client/src/api.js`.
- **i18n**: UI strings live in `client/src/locales/{en,ja}.js` and are read via `useI18n` (`t('a.b.c')`). Locale also switches currency (USD/JPY). Add new UI text to both locale files.
- **Auth** (`useAuth`) is mock user data only.
- `Backlog.vue` exists but has no route in `main.js`. `CreatePurchaseOrderRequest` is defined in `main.py` but has no POST endpoint yet; purchase orders are read-only and only feed the `has_purchase_order` flag on `/api/backlog`.
- Longer style guidance is in `client/CLAUDE.md` and `server/CLAUDE.md`.

## API Endpoints
- `GET /api/inventory` - Filters: warehouse, category
- `GET /api/orders` - Filters: warehouse, category, status, month
- `GET /api/inventory/{id}`, `/api/orders/{id}` - Single record (404 if missing)
- `GET /api/dashboard/summary` - All filters
- `GET /api/demand`, `/api/backlog` - No filters
- `GET /api/reports/quarterly`, `/api/reports/monthly-trends`
- `GET /api/spending/*` - Summary, monthly, categories, transactions

## Common Issues
1. Use unique keys in v-for (not `index`) - use `sku`, `month`, etc.
2. Validate dates before `.getMonth()` calls
3. Update Pydantic models when changing JSON data structure
4. Inventory filters don't support month (no time dimension)
5. Revenue goals: $800K/month single, $9.6M YTD all months

## File Locations
- Views: `client/src/views/*.vue`
- API Client: `client/src/api.js`
- Backend: `server/main.py`, `server/mock_data.py`
- Data: `server/data/*.json`
- Styles: `client/src/App.vue`

## Code Comments
- Always document non-obvious logic changes with comments

## Design System
- Colors: Slate/gray (#0f172a, #64748b, #e2e8f0)
- Status: green/blue/yellow/red
- Charts: Custom SVG, CSS Grid for layouts
- No emojis in UI
