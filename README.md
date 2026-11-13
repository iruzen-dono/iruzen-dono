<div align="center">
  <img src="assets/header.svg?v=202611131355" alt="jules zhou — full-stack developer, AI agent tooling" width="860" />
</div>

**Full-stack developer and indie hacker** in Lomé, Togo — final year of a BSc in Artificial Intelligence & Big Data, open to international remote work.

I design and operate SaaS products end to end — database, API, UI, billing — and build open-source tooling for AI agents in Python. Most of that tooling sits on the unglamorous half of agent reliability: hand the model the right context, then fail the build the moment that context stops being true.

---

### Tools for agents

| Project | The problem it solves | Install |
| :--- | :--- | :--- |
| [**hermes-project-oracle**](https://github.com/iruzen-dono/hermes-project-oracle) | Context files rot silently. Scan the repo → generate `AGENTS.md`/`CLAUDE.md` → `oracle-check` fails CI on drift → `oracle-lint` flags rules the code cannot verify. | `pip install hermes-project-oracle` |
| [**memory-vault**](https://github.com/iruzen-dono/memory-vault) | Sessions disappear into chat history. Packs them into portable `.hermes-memory` context packs. | `pip install hermes-memory-vault` |
| [**hermes-plugin-gen**](https://github.com/iruzen-dono/hermes-plugin-gen) | Writing a Hermes Agent plugin by hand. Generates a working scaffold from a description. | — |
| [**workless**](https://github.com/iruzen-dono/workless) | Workflow automation you can self-host — a Zapier/Make alternative with a real execution engine. | — |
| [**portfolio-terminal**](https://github.com/iruzen-dono/portfolio-terminal) | A portfolio that is not a dashboard template — 30+ commands, virtual filesystem, fr/en. | [live](https://portfolio-terminal-lake.vercel.app) |

### SaaS in production

| Product | What ships | Stack |
| :--- | :--- | :--- |
| **Quotask** | Quoting and invoicing: PDF generation, proposal templates, e-signature, Stripe + Lemon Squeezy billing | Next.js 16 · Drizzle · Turso |
| **LandlordKit** | Rental management: tenant portal, recurring rent collection, lease expiry alerts, analytics | Next.js 16 · Neon · Resend |
| **TradeQuote** | Quoting for service businesses: line items, configurable VAT, public accept/decline | Next.js 16 · React 19 · Neon |
| [**XEARN**](https://github.com/iruzen-dono/XEARN) | Pan-African micro-earning platform: 40+ endpoints, 99 automated tests, gamification, admin panel | NestJS 11 · Next.js 15 · Expo |
| [**Workless**](https://github.com/iruzen-dono/workless) | Self-hosted workflow engine: React Flow builder, DAG execution, webhooks, scheduling | Laravel 11 · Next.js 15 · Redis |

Three of them live in private repos — no links on purpose rather than dead ones.

---

### Open source

Targeted fixes in codebases I had no prior familiarity with: read the file, find the actual cause, send the smallest patch that holds.

| Repository | Contributions |
| :--- | :--- |
| [**medusajs/medusa**](https://github.com/medusajs/medusa/pull/16006) | `#16006` **merged** — admin: handle deleted stock locations in the order fulfillment section |
| [**neomjs/neo**](https://github.com/neomjs/neo/pulls?q=is%3Apr+author%3Airuzen-dono) | 2 **merged** — curation window for held issues, count published when a batched update closes |
| [**hermes-browser-extension**](https://github.com/abundantbeing/hermes-browser-extension/pulls?q=is%3Apr+author%3Airuzen-dono) | 6 **merged** — multi-tab context picker, slash commands, DOM chip states, ESLint/Prettier, subagent results, model picker |
| [**keisary/KeycePass**](https://github.com/keisary/KeycePass/pull/1) | `#1` **merged** — password manager fix |
| [**FlowiseAI/Flowise**](https://github.com/FlowiseAI/Flowise/pulls?q=is%3Apr+author%3Airuzen-dono) | 5 opened — Docker tag pinning, variable names in `overrideConfig`, RediSearch escaping, duplicate chatflow on rapid save |
| [**NVIDIA/auto-ontology**](https://github.com/NVIDIA/auto-ontology/pulls?q=is%3Apr+author%3Airuzen-dono) · [**meta/prophet**](https://github.com/facebook/prophet/pull/2784) | open — non-ASCII and CSV handling, plus a `cmdstanpy` pin so Windows builds stop fetching a retired Rtools URL |

Also PRs in **directus**, **saleor**, **posthog**, **dify**.

---

### GitHub

<img src="assets/stats.svg?v=202611131355" alt="Twelve-month contributions, commits, merged PRs, repositories, external PRs and PyPI downloads" width="860" />

<img src="assets/activity.svg?v=202611131355" alt="Weekly contributions over 53 weeks with current and longest streaks" width="860" />

<img src="assets/heatmap.svg?v=202611131355" alt="Contribution calendar for the last twelve months" width="860" />

<img src="assets/signals.svg?v=202611131355" alt="Commits by weekday and hour, and language split by bytes" width="860" />

<sub>Every card is generated from the GitHub and PyPI APIs by [`scripts/readme_cards.py`](scripts/readme_cards.py) and committed as SVG by a daily workflow — no third-party widget, no hosted badge service that can disappear.</sub>

---

### Background

**Experience** — independent since `2024-11`: five commercialised products, plus freelance technical and UX/UI audits of hotel group sites in Lomé (Sarakawa Hotel, Hôtel 2 Février). Open-source contributor since `2025-06`.

**Education** — BSc Artificial Intelligence & Big Data, Ascencia Keyce Togo (2026 → present) · two-year Computer Science & Software Engineering programme, Collège de Paris Supérieur (2023 → 2025) · Baccalauréat série C, mathematics & physics (2023).

**Languages** — French (native) · English (professional: code review, documentation, upstream discussions).

**Availability** — remote, worldwide, UTC±0.

---

### Reach me

- Mail — [juleszhou01@gmail.com](mailto:juleszhou01@gmail.com)
- X — [@iruzendono](https://twitter.com/iruzendono)
- Discord `@iruzenn` · Telegram `@Am_The_CEO`
- An agent answers for me when I'm heads-down — [@Comphermes_bot](https://t.me/Comphermes_bot)

<div align="center">
  <sub>
    <a href="https://github.com/iruzen-dono?tab=repositories">All repos</a> ·
    <a href="https://portfolio-terminal-lake.vercel.app">Portfolio</a> ·
    <a href="https://pypi.org/project/hermes-project-oracle/">PyPI</a>
  </sub>
</div>
