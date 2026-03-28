# SIEGE Observatory Build Instructions for Coding Agent

## What You're Building

You are building a web dashboard called Observatory for the SIEGE coevolution experiment. It is a read-only visualization layer that reads JSON/JSONL files from the `evolution_output/` directory and presents them through a FastAPI backend + React frontend. Read the full spec in `OBSERVATORY_SPEC.md` before writing any code.

**This is a separate service from the core evolution loop.** It never writes to `evolution_output/`. It can run while the evolution loop is active.

## Prerequisites

The core SIEGE evolution loop must already exist and produce output in the expected format. If `evolution_output/` does not yet exist or is empty, create a mock data generator (see Layer 1 below) so you can develop the dashboard independently.

## Build Order (Strict — Do Not Skip Ahead)

### Layer 1: Mock Data Generator

Before building any UI, create a script at `observatory/generate_mock_data.py` that produces realistic fake evolution output for 20 generations. This is your development fixture — every subsequent layer depends on it.

The mock data must match the schemas in the Observatory spec exactly:
- `evolution_output/generation_NNN/metrics.json` — aggregate stats per generation with realistic trajectories (attack success rate starting ~70% and declining with oscillations, species counts fluctuating between 2-6, HoF growing)
- `evolution_output/generation_NNN/episodes/` — 50-100 episode JSON files per generation with full conversation logs, technique tags, pipeline stages triggered, and realistic outcomes
- `evolution_output/generation_NNN/banks/` — bank genome JSON files
- `evolution_output/generation_NNN/attackers/` — attacker genome Python files
- `evolution_output/generation_NNN/diagnostics.json` — pathology alerts (empty for most generations, occasional warnings)
- `evolution_output/hall_of_fame/attacks/` and `banks/`
- `evolution_output/lineage.jsonl` — mutation history with parent→child links forming a connected DAG

The conversations in mock episodes should be readable and varied — not lorem ipsum. Write 10-15 distinct conversation templates covering different attack techniques (direct override, authority impersonation, social engineering, multi-turn manipulation) and bank responses (immediate rejection, internal deliberation that catches the attack, internal deliberation that fails to catch it, legitimate approval). Randomly compose episodes from these templates with variation.

**Test:** The mock data passes schema validation. Every episode references a bank_id and attacker_id that exist in the corresponding generation's genome files. Every lineage entry references genome IDs that exist.

### Layer 2: Backend API (FastAPI)

Implement the FastAPI server at `observatory/server.py`. Start with these endpoints in order:

1. `GET /api/generations` — list all generations with summary stats
2. `GET /api/timeseries?metrics=...` — time series data for charts
3. `GET /api/generations/{gen}/episodes?...` — paginated, filtered episode list (metadata only, no conversation)
4. `GET /api/episodes/{episode_id}` — full episode with conversation log
5. `GET /api/genomes/banks/{bank_id}` — bank genome + fitness
6. `GET /api/genomes/attackers/{attacker_id}` — attacker genome + fitness
7. `GET /api/greatest-hits` — curated highlights
8. `GET /api/lineage/{genome_id}` — ancestry chain
9. `GET /api/lineage/tree` — full lineage graph
10. `GET /api/strategy-map/{gen}` — behavioral descriptors for scatter plot
11. `GET /api/diagnostics/{gen}` — pathology alerts
12. `WS /api/ws/live` — WebSocket for live generation updates

Implementation rules:
- On startup, scan `evolution_output/` and build an in-memory index of all generations, genomes, and episodes. Cache aggressively.
- Episode list endpoints return metadata only (no conversation field). Conversation is fetched only via the single-episode endpoint.
- For the lineage tree endpoint, parse `lineage.jsonl` into a graph structure. Cache it.
- Use a filesystem watcher (watchdog library) to detect new generation folders and invalidate caches.
- Add CORS middleware for local development (frontend on different port).
- Serve the production frontend build as static files from the same FastAPI app.

**Test:** Every endpoint returns valid JSON matching the expected schema. Episode filtering works correctly (by outcome, bank_id, attacker_id, technique tag). Pagination works. Test against mock data.

### Layer 3: Frontend Scaffold + Generation Overview

Set up the React app with Vite + Tailwind + React Router + React Query (or SWR).

Build the Generation Overview page first — it's the home page and validates that the full stack works end-to-end.

**Generation Overview has three sections:**

Top: Time series line charts (Recharts). X-axis = generation. Lines for:
- Attack success rate (current population) — primary line
- Attack success rate (vs Hall of Fame) — secondary line, dashed. Divergence from the first line = cycling.
- Legitimate approval rate
- Species count (banks + attackers)
- HoF size

Middle: Current (latest) generation summary cards showing: generation number, best bank (ID + defense rate), most successful attacker (ID + success rate + technique tags), active pathology alerts as colored banners.

Bottom: Species composition stacked area chart (Recharts). X = generation, Y = population share. One chart for banks, one for attackers. Each species is a distinct color.

Click any point on the timeline charts to navigate to that generation's detail view. This is the primary drill-down interaction.

**Test:** Charts render with mock data. Clicking a generation navigates correctly. Pathology alerts display when present in diagnostics.json.

### Layer 4: Episode Browser + Conversation View

This is the highest-value page. Users will spend most of their time here.

**Episode table:**
- Columns: Generation, Bank ID, Attacker ID, Type, Outcome (color-coded badge), Turn Count, Technique Tags (pill badges), Amount
- Sortable by any column
- Sidebar filters: generation range slider, outcome checkboxes, bank/attacker ID search, technique tag multi-select
- Pagination (50 per page)

**Conversation View (expanded row):**
When a row is clicked, expand it to show the full conversation in a chat-style layout:
- Attacker messages: left-aligned, red-tinted background
- Bank responses: right-aligned, blue-tinted background
- Bank internal reasoning (classification, verification stages): collapsible gray section between attacker and bank messages. Collapsed by default. Clicking "Show reasoning" expands it.
- Action blocks highlighted: red background if attack succeeded, green if blocked/approved correctly
- Final outcome banner at the bottom of the conversation

The conversation view is the most important component in the entire dashboard. Make it readable, clear, and fast. Every message should be easy to distinguish by role at a glance.

**Test:** Table renders with correct data. Filters narrow results correctly. Conversation view renders all turn types (attacker, bank, bank_internal). Collapsible reasoning sections work.

### Layer 5: Genome Inspector

Two variants: Bank Inspector and Attacker Inspector. Navigated to from episode browser (click a bank/attacker ID) or from lineage explorer.

**Bank Inspector:**
- Defense pipeline rendered as a vertical flowchart (use a simple CSS/HTML layout, not a charting library — boxes connected by arrows). Each box shows the stage name and the actual prompt/rules text, truncated with expand-on-click.
- Fitness radar chart (Recharts RadarChart) with 4 axes: current defense rate, historical defense rate, legitimate approval rate, pipeline efficiency.
- Win/loss table: list of attackers, outcome per attacker, clickable to open that episode.
- Metadata: generation, species, genome ID.
- Lineage link: "View parent →" button navigating to parent genome.

**Attacker Inspector:**
- Python source code with syntax highlighting (use a lightweight library like Prism.js or highlight.js, or just use a `<pre>` with monospace font and basic keyword coloring — don't over-engineer this).
- Fitness radar chart with 4 axes: success rate, total extracted, novelty score, stealth.
- Technique tags displayed as large pill badges.
- Win/loss table: list of banks, outcome per bank, clickable to open that episode.
- Behavioral descriptor values (the 5 novelty dimensions) shown as a small bar chart or simple number display.
- Lineage link.

**Test:** Both inspector variants render correctly. Links between inspectors and episodes work bidirectionally. Fitness radar charts display correctly.

### Layer 6: Greatest Hits

Implement the curation logic from Section 3.6 of the Observatory spec as a backend function that runs when greatest-hits data is requested (compute on-the-fly from episode data, cache per generation).

**Frontend:** Reverse-chronological feed. Each hit is a card with:
- Type icon (use emoji or a simple icon set — 🩸 first blood, 🗡️ giant killer, 😰 close call, 🚀 breakthrough, 💀 extinction, ⬆️ escalation)
- Title (bold)
- One-line description
- Generation badge
- "View Episode" or "View Lineage" button

This page should feel like a social media feed of the most interesting evolutionary events. Scannable, with clear visual hierarchy.

**Test:** Curation logic correctly identifies each hit type. Cards render. Navigation buttons work.

### Layer 7: Lineage Explorer

Interactive graph visualization of evolutionary descent.

**Use D3 force-directed graph** (or a tree layout if the lineage is cleanly tree-shaped). Nodes = genomes, edges = parent→child.

Node encoding:
- Color: fitness value mapped to a red→green gradient
- Size: number of descendants (computed from lineage graph)
- Gold border: in Hall of Fame
- Shape: circle = bank, diamond = attacker

Edge encoding:
- Thickness: magnitude of fitness change
- Dashed if fitness decreased

Interactions:
- Hover node: tooltip with genome ID, generation, fitness summary
- Click node: navigate to Genome Inspector
- Hover edge: tooltip with mutation intensity + summary
- Zoom and pan
- Generation range filter (don't render the entire lineage at once for large runs — let the user select a window)

This is the most complex frontend component. If it's taking too long, ship a simplified version first: a simple vertical timeline list showing parent→child relationships as indented text entries, with the full D3 graph as a follow-up.

**Test:** Graph renders with mock data. Nodes are positioned sensibly. Click and hover interactions work. Doesn't crash on 100+ nodes.

### Layer 8: Strategy Map

Animated 2D scatter plot of the attacker population in behavioral descriptor space.

**Use D3** for the scatter plot.

- Two axis dropdowns: select from the 5 behavioral dimensions
- Points: one per attacker in the selected generation
- Color: success rate (gray → red gradient)
- Size: novelty score
- Hover: tooltip with attacker ID, technique tags, success rate

**Animation:** A generation scrubber (slider + play/pause) that transitions the scatter plot between generations. Points should animate smoothly to their new positions (D3 transition). Points that are new should fade in; points that died should fade out.

This is the second most complex frontend component. Same rule as Lineage Explorer — if it's taking too long, ship a static version (single generation, no animation) first, then add the scrubber.

**Test:** Scatter plot renders. Axis selection works. Hover tooltips display. Animation plays through generations without errors.

### Layer 9: Live Updates

Add the WebSocket endpoint to the backend (filesystem watcher that pushes a message when a new generation folder appears). Frontend subscribes on the Generation Overview page and auto-refreshes charts when new data arrives.

This is a nice-to-have. Only build it after everything else works.

## Critical Implementation Rules

**Read-only. Always.** The dashboard never writes to `evolution_output/`. If you need derived data (like the greatest hits curation), compute it on the fly and cache in memory. Never write cache files into the evolution output directory.

**The Conversation View is the product.** If you have to cut scope, cut the Strategy Map and Lineage Explorer before you cut the Conversation View. Being able to read individual attack/defense interactions is the core value of this dashboard.

**Don't over-style.** This is a research tool, not a consumer app. Tailwind defaults are fine. Readable typography, clear color-coding for outcomes, and fast navigation matter more than visual polish. Do not add animations to the UI beyond the Strategy Map scrubber.

**Keep the backend simple.** No database. No ORM. Read JSON files from disk, cache in memory, serve via FastAPI. The data volume is small (hundreds of generations × hundreds of episodes = tens of thousands of files at most). This all fits in memory.

**Responsive is not required.** This will be used on a laptop/desktop. Don't spend time on mobile layouts.

**Link everything.** Every bank ID and attacker ID in the dashboard should be a clickable link to the Genome Inspector. Every episode reference should link to the Episode Browser with that episode expanded. The user should be able to navigate fluidly between the macro view (Generation Overview) and the micro view (single conversation) in two clicks.

## What NOT to Do

- Do not add authentication or user accounts. This is a local research tool.
- Do not add the ability to modify evolution parameters from the dashboard. Read-only.
- Do not build a custom charting library. Use Recharts for standard charts and D3 only for the scatter plot and lineage graph.
- Do not use a database. JSON files + in-memory cache is the entire storage layer.
- Do not add features not in the spec. Ship the core pages first.
- Do not spend more than minimal effort on error states and loading skeletons. A simple "Loading..." text is fine. Focus on the data views.
