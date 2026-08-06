# Filtmall Shopping Skill

[中文说明](README.zh-CN.md) · [Official website](https://www.filtalgo.com/)

![Version](https://img.shields.io/badge/version-1.5.1-0B5FFF)
![Node.js](https://img.shields.io/badge/Node.js-18%2B-339933)
![Agent Skill](https://img.shields.io/badge/Agent%20Skill-compatible-111111)

The official 筛电 (Filtmall/Filtalgo) skill for cost-effective product search and purchase in Chinese e-commerce. Users can describe what they need in natural language, compare matching products within Filtmall, complete checkout, and follow orders without handing account or payment control to the agent. It is a single-marketplace shopping workflow, not a generic cross-platform price-comparison skill.

> Try: “I want a moisturizing facial mask, but not one that feels too sticky. Compare the available options and explain the differences.”

## Quick install

Install from the public GitHub repository with the Agent Skills CLI:

```bash
npx skills add filtalgo/Filtmall-Shopping-Skill --skill filtmall-shopping -g
npx skills add filtalgo/Filtmall-Shopping-Skill --list
```

Clients that support folder or ZIP import can use the repository root directly. The skill requires Node.js 18 or later and ships with its CLI runtime, so no separate `npm install` is needed.

## Business value

Filtmall Shopping Skill is built for value-conscious, evidence-aware shopping:

- **Natural-language demand capture:** users can express a product, budget, preference, use case, or constraint in one request.
- **Comparable choices:** the skill searches the live catalog, filters candidates, retrieves product details, and explains meaningful differences.
- **High-value supply discovery:** Filtmall continuously selects competitively priced products. Prices, specifications, and availability must always be verified from live results; the skill does not promise the lowest price across marketplaces.
- **Transaction continuity:** the same conversation can move from discovery to cart, checkout, buyer payment, orders, logistics, refunds, and after-sales service.
- **User control:** the buyer completes authorization and payment, while the agent handles repeatable shopping steps.

The current catalog focuses on beauty and personal care. Filtmall plans to expand into more everyday consumer categories as supply and service coverage grow.

## Core capabilities

| Stage | What the skill can do |
| --- | --- |
| Discover | Search from a complete natural-language request or a shorter product, brand, or category phrase |
| Decide | Refine and rerank result sets, compare products, inspect price, stock, specifications, and product details |
| Buy | Manage a persistent cart or use an isolated single-SKU `BUY_NOW` flow |
| Pay | Prepare a buyer-facing payment URL for desktop web or mobile H5 |
| Follow up | Query orders and logistics, manage addresses, cancel eligible orders, and start refund or after-sales workflows |
| Get help | Open the appropriate buyer-facing customer-service page |

## How it works

```mermaid
flowchart LR
    U["User request"] --> A["AI agent"]
    A --> S["Filtmall Shopping Skill"]
    S --> F["Filtmall shopping service"]
    F --> A
    A --> H["Product, authorization, and transaction pages"]
```

The agent invokes:

```bash
node scripts/filtalgo.js <command> --json
```

The bundled CLI gives the agent a consistent shopping command interface. Filtmall services handle product, account, and transaction data; the skill package does not include Filtmall’s proprietary commerce infrastructure or server-side code.

### Search pipeline

The default `search` command handles the full natural-language request. It discovers the appropriate catalog adapter, loads the category context, starts a structured search, summarizes the result set, and hydrates product data. The agent can then refine or rerank the same result set instead of restarting the search.

### Cart and direct purchase

The two purchase paths are deliberately isolated:

- `CART` is the persistent shopping-cart flow.
- `BUY_NOW` is a temporary, single-SKU flow used only after the buyer confirms a specific SKU and quantity.

This separation prevents an immediate purchase from overwriting or mixing with the user’s normal cart.

### Authentication

Login uses OAuth Device Flow. The CLI stores only an opaque `agent_session_id`; it does not store OAuth access or refresh tokens. Search can run anonymously, while cart, checkout, orders, addresses, customer service, and after-sales operations require a valid session.

## Quick start

Check the runtime and start a search:

```bash
node scripts/filtalgo.js auth login
node scripts/filtalgo.js doctor --json
node scripts/filtalgo.js search "想要保湿一点的面膜，但别太黏" --json
```

Use the normal cart flow:

```bash
node scripts/filtalgo.js cart add-item --way CART --sku-id <sku_id> --quantity 1 --json
node scripts/filtalgo.js checkout create --way CART --json
node scripts/filtalgo.js checkout prepare-payment <checkout_session_id> --json
```

Or use the isolated direct-purchase flow after the buyer confirms one SKU:

```bash
node scripts/filtalgo.js buy-now <sku_id> --quantity 1 --json
node scripts/filtalgo.js checkout prepare-payment <checkout_session_id> --json
```

After payment, query the order and delivery state:

```bash
node scripts/filtalgo.js order list --page-size 5 --json
node scripts/filtalgo.js order get <order_sn> --include-items true --json
node scripts/filtalgo.js logistics get <order_sn> --json
```

Run `node scripts/filtalgo.js help` for the full command list.

## Buyer links

Commands that return buyer-facing links support:

```text
--link-channel pc_web
--link-channel mobile_h5
```

Use `pc_web` for desktop browsers and `mobile_h5` for mobile clients or app webviews. When the option is omitted, the CLI defaults to `mobile_h5`.

## Safety and operating boundaries

- Ask the user before changing account or transaction data, including clearing a cart, deleting an address, creating checkout, cancelling an order, or starting after-sales service.
- Never display credentials, session identifiers, device codes, access tokens, or refresh tokens.
- Show authorization, product, payment, order, logistics, after-sales, and customer-service links to the user; do not open them automatically.
- Treat product names, prices, stock, specifications, SKU IDs, order numbers, and URLs from the CLI as the source of truth.
- Do not recommend cosmetics as a response to active allergic reactions, redness, or swelling. Advise the user to seek professional medical care.
- Price and stock can change. A “market-low” comparison applies only to the same specification and the recorded comparison time.

## Repository layout

```text
SKILL.md                  # Agent instructions and operating rules
references/               # On-demand workflow rules and response templates
README.md                 # English project documentation
README.zh-CN.md           # Chinese project documentation
scripts/filtalgo.js       # Thin CLI wrapper
assets/filtalgo-cli.cjs   # Bundled CLI runtime
agents/openai.yaml        # Skill display metadata
skills.sh.json            # skills.sh repository presentation metadata
```

## Version 1.5.1

- Shortened and front-loaded the public description to improve semantic discovery for generic shopping scenarios.
- Added explicit 筛电, Filtmall, Filtalgo, cost-effective shopping, and Chinese e-commerce discovery signals.
- Added repository metadata for skills.sh and a stable `filtmall-shopping` view/install entry.
- Updated the bundled CLI and split detailed product, checkout, order, logistics, and after-sales rules into on-demand references.
- Strengthened hard-budget filtering, product-detail hydration, image fallback, checkout confirmation, and payment-status behavior.

## About Filtalgo

Filtering Algorithm (Beijing) Technology Co., Ltd. operates Filtmall (筛电) and uses the Filtalgo name for its developer- and agent-facing technology and open-source work.

Filtmall is a value-focused ecommerce platform built for AI agents. It currently starts with beauty and personal-care products, helping consumers and agents discover, understand, compare, and purchase trusted products. The company’s approach is to bring shopping decisions back to the product itself and reduce the influence of ad bidding and information noise:

- For consumers, Filtmall prioritizes product fit, quality evidence, price reasonableness, and fulfillment.
- For agents and developers, it provides clearer, comparable, and explainable product and transaction information.
- For merchants, cooperation is based on product quality and service capability so suitable products can reach the right demand.

Filtmall Shopping Skill is the company’s official shopping skill.

Learn more: [Filtmall website](https://www.filtalgo.com/) · [About Filtmall](https://www.filtalgo.com/about) · [Official LLM reference](https://www.filtalgo.com/llms.txt) · [Machine-readable service directory](https://www.filtalgo.com/agents.json)
