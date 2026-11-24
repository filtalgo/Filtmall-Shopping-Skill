<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.png">
    <img alt="Filtmall Logo" src="assets/logo-light.png" width="200">
  </picture>
</p>

<h1 align="center">Filtmall Shopping Skill</h1>

<p align="center">Tell your AI assistant your budget and requirements — research products clearly and buy high-value goods directly through Filtmall.</p>

<p align="center">
  <a href="README.md">简体中文</a> ｜ <a href="README_en.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/filtalgo/Filtmall-Shopping-Skill/releases"><img alt="Release" src="https://img.shields.io/badge/Release-v2.4.3-blue?logo=github"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache--2.0-2EA44F?logo=apache"></a>
  <a href="SKILL.md"><img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="https://github.com/filtalgo/Filtmall-Shopping-Skill"><img alt="Stars" src="https://img.shields.io/github/stars/filtalgo/Filtmall-Shopping-Skill?logo=github"></a>
  <a href="https://skills.sh/filtalgo/Filtmall-Shopping-Skill"><img alt="skills.sh" src="https://skills.sh/b/filtalgo/Filtmall-Shopping-Skill"></a>
</p>

- **What is Filtmall**: **Filtmall (筛电)** is a platform-level **Business Agent** built for **Personal Agents**, as well as an agent-native e-commerce platform focused on extreme value-for-money. Once installed, your Personal Agent connects via this Skill (`filtmall-shopping`) directly to Filtmall's backend shopping Agent to discover products, verify specs and ingredients, compare prices, place orders, and track after-sales in chat — without switching apps or digging through coupon math. Product details, prices, and inventory are determined by live service responses.
- **What is `filtmall-shopping`**: Filtmall's official open-source shopping Agent Skill, giving Skill-enabled AI assistants direct capabilities to search products, check specs and ingredients, compare prices, place orders, and handle after-sales on Filtmall.

## Why Filtmall

Filtmall is built around two core pillars: **Open to Personal Agents by Design** and **Extreme Value-for-Money**.

- **Native open access for Personal Agents**: Built specifically to serve Personal Agents with structured product facts, price references, and fulfillment APIs, without the anti-bot blocks common on traditional marketplaces.
- **Factory-direct OBM supply, zero platform ad fees**: Connects directly with vetted OBMs (Original Brand Manufacturers) and charges zero advertising or paid-traffic fees — most items are priced at roughly **1/3 to 2/3** of comparable specifications on traditional platforms, delivering extreme value for money.
- **No paid rankings — matched purely to your requirements**: Ranked strictly by requirement fit and value rather than ad spend; state your budget, specs, and use case in plain language to get specs, prices, ingredients/materials, and fit reasons in seconds.
- **Curated quality, zero-friction browsing**: Products are vetted for both same-spec price advantage and manufacturer qualification, reputation, or sample feedback (spanning beauty & personal care, food, bags, and expanding with demand). Browse and compare with no login or API key; every transaction confirms first and pays on the official checkout page.

| Dimension | Traditional E-Commerce | Filtmall |
| --- | --- | --- |
| Agent Access | Built for manual browsing; often blocks external AI agents | Open natively to Personal Agents via structured APIs |
| Ranking | Influenced by paid ads and traffic bidding | Zero paid rankings — sorted by fit and value |
| Pricing Basis | Multi-layer distributors + platform ad spend | Direct OBM factories + zero platform ad fees |
| Decision Speed | Manual scrolling across pages, reviews, and coupons | AI summarizes specs, ingredients, and price references in seconds |

## Installation

Choose the easiest method for your AI assistant (requires Python 3.10+ locally):

| AI Assistant / Environment | Recommended Installation |
| --- | --- |
| **WorkBuddy** | One-click install via [WorkBuddy Skill Store · Filtmall Shopping](https://www.workbuddy.cn/share/asset?extra_from=&resource_type=link&shareCode=cs261124Dt1WMAXrsiMLBGjMOhQz3c&share_way=link&sig=bDrtltW2Ysncjump) |
| **SkillHub** | Install via [SkillHub · filtmall-agentic-shopping](https://skillhub.cn/skills/org-r0hb81co/filtmall-agentic-shopping) |
| **skills.sh** | View on [skills.sh · filtmall-shopping](https://www.skills.sh/filtalgo/filtmall-shopping-skill/filtmall-shopping) |
| **Zero-CLI (General AI Agents)** | Send this repo URL to your AI and ask: "Please install this shopping skill: `https://github.com/filtalgo/Filtmall-Shopping-Skill`" |
| **CLI (Claude Code / Codex / Cursor, etc.)** | Use the `npx` command below (requires Node.js 22.20+) |
| **Offline / No Node.js** | Download a package from [GitHub Releases](https://github.com/filtalgo/Filtmall-Shopping-Skill/releases) and copy it into your host's skill folder as `filtmall-shopping` (preserving `data/`, `third_party/`, and `LICENSE`) |

Global CLI installation (recommended):

```bash
npx skills add filtalgo/Filtmall-Shopping-Skill --skill filtmall-shopping -g
```

Omit `-g` for project-local installation; pass `-a claude-code` to target a specific host.

## Quick Start

Once installed, try asking in chat:

- Recommend moisturizing face masks under ¥100, ideally under ¥5 per sheet
- Find a lightweight commuter backpack under ¥250 that fits a 14-inch laptop
- Compare the specs, ingredients, and prices of the first and third options
- Show my shopping cart / Check the shipping status of this order

Connects to the production environment by default. Browsing, search, comparison, and ingredient lookups require no login; member operations require separate authorization and explicit confirmation before writes.

## Capabilities

| Capability | Description |
| --- | --- |
| Discovery & Comparison | Filter by category, budget, specs, and preferences; view prices, stock, fit reasons, and price references |
| Details & Ingredients | Inspect product specs, materials, and cosmetic ingredient details |
| Shopping Cart | Add, update quantity, remove items, and review totals after authorization |
| Shipping Addresses | List, add, or edit addresses with offline province/city/district resolution |
| Checkout & Payment | Preview and confirm orders to obtain the official checkout link; payment completes on the store page |
| Orders & Shipping | Track order status and delivery updates |
| After-Sales & Support | Submit/track after-sales requests and access customer support links |

Available capabilities depend on the target Agent configuration, business services, and user authorization. The Skill never fabricates unreturned data.

## Boundaries & Safety

- **No autonomous payment**: Payment is always completed by the user on the official checkout page.
- **Confirm before writes**: Cart, address, order, and after-sales changes always summarize key details and ask for confirmation first.
- **Local isolation**: Credentials and pending states are kept in a private local state directory and never written to chat or logs.
- **Idempotent recovery**: On uncertain network outcomes, the Skill checks status first rather than blindly re-sending write requests.

## About Filtmall

Filtmall is built by **Filtmall (Beijing) Intelligent Technology Co., Ltd.**, dedicated to building an extreme value-for-money agent-native e-commerce platform for Personal Agents.

- Website: [www.filtalgo.com](https://www.filtalgo.com/)
- Web Store (H5): [m.filtalgo.com](https://m.filtalgo.com/)
- WeChat Mini-Program: Search "筛电商城" in WeChat

<details>
<summary>Developer & Integration Guide (Configuration, Architecture, Tests & Protocol Docs)</summary>

### Configuration

- **Environment**: Production by default. Pass both `--control-url` and `--agent-id` to switch to another open environment.
- **Host identifier**: Supports `host` values `today` / `workbuddy` / `doubao` / `qianwen` / `lingguang` / `default`.

### Offline Tests

```bash
python3 -m unittest discover -s tests
```

### Protocol & Reference Docs

- [SKILL.md](SKILL.md): Host invocation and interaction rules
- [references/protocol.md](references/protocol.md): Public API protocol
- [references/presentation.md](references/presentation.md): Display and host adaptation
- [references/authorization.md](references/authorization.md): Authorization, confirmation, and payment boundaries

</details>

## License

[Apache-2.0](LICENSE)

---

<p align="center">
  <a href="https://www.filtalgo.com/">Website</a> ·
  <a href="https://m.filtalgo.com/">Store</a> ·
  <a href="https://github.com/filtalgo/Filtmall-Shopping-Skill">GitHub</a> ·
  <a href="https://www.skills.sh/filtalgo/filtmall-shopping-skill/filtmall-shopping">skills.sh</a> ·
  <a href="https://skillhub.cn/skills/org-r0hb81co/filtmall-agentic-shopping">SkillHub</a>
</p>
