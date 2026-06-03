# Filtmall Shopping Skill

[中文说明](README.zh-CN.md)

**Official website:** [https://www.filtalgo.com/](https://www.filtalgo.com/)

Filtmall Shopping Skill brings an AI-assisted shopping experience to developers, agent builders, and early users who want to try practical agent commerce workflows. It packages a lightweight Node.js CLI and buyer authorization flow into a ready-to-use skill folder, so an AI agent can help users search products, compare options, build carts, create checkout, open the buyer payment page, and follow up on orders.

This repository is designed for quick public demos and hands-on exploration. Clone it, install it as a skill, and let your agent experience a real shopping flow powered by the Filtalgo ecosystem.

## What You Can Try

- Product discovery with natural Chinese keywords such as `沐浴露`, `洗发露`, or brand/product fragments.
- AI-assisted cart and checkout flow.
- Browser-based buyer authorization and wallet payment handoff.
- Order list, order detail, logistics query, address management, cancellation, refund, and after-sale workflows.
- A packaged CLI runtime that only requires Node.js 18 or later.
- A curated remote test catalog with beauty and personal-care products, including body wash, skincare, hand care, shampoo, and related daily-care goods.

## Who Is This For

- Developers exploring AI shopping assistants.
- Agent platform users looking for a real commerce workflow demo.
- Teams evaluating how AI agents can guide shopping, checkout, and post-purchase service.
- Community members who want to experience the Filtalgo/Filtmall ecosystem before broader public release.

## Repository Contents

```text
SKILL.md                  # Agent-facing skill instructions
README.md                 # English project overview
README.zh-CN.md           # Chinese project overview
scripts/filtalgo.js       # Thin wrapper for the bundled CLI
assets/filtalgo-cli.cjs   # Bundled CLI runtime
agents/openai.yaml        # Skill UI metadata
```

## Quick Start

Prerequisite: Node.js 18 or later.

```bash
node scripts/filtalgo.js auth login
node scripts/filtalgo.js doctor --json
node scripts/filtalgo.js search "沐浴露" --json
```

After login, the agent can run the normal shopping flow:

```bash
node scripts/filtalgo.js cart clear --confirm --json
node scripts/filtalgo.js cart add-item --sku-id <sku_id> --quantity 1 --json
node scripts/filtalgo.js checkout create --json
node scripts/filtalgo.js checkout prepare-payment <checkout_session_id> --handler wallet --json
```

Give the returned `payment_url` to the buyer. The buyer completes wallet payment in the browser, then the agent can query order state:

```bash
node scripts/filtalgo.js order list --page-size 5 --json
node scripts/filtalgo.js order get <order_sn> --include-items true --json
node scripts/filtalgo.js logistics get <order_sn> --json
```

## Suggested Demo Prompt

After installing this skill, try asking your agent:

> I want to buy a cost-effective body wash. Please search Filtmall, compare several options, add one to my cart, create checkout, and send me the payment link.

The agent should use the bundled CLI, show real product options, ask for confirmation when needed, and return a browser payment URL.

## Why Developers Like This Demo

Many agent demos stop at product recommendations. Filtmall Shopping Skill goes further: it lets an agent move from recommendation to cart, checkout, buyer payment handoff, and order follow-up. That makes it useful for testing real agent-commerce behavior, not just conversational product search.

The buyer remains in control of login and payment, while the agent handles the repetitive shopping steps.

## About Filtalgo

[Filtalgo](https://www.filtalgo.com/) is building practical AI and commerce infrastructure for smarter product discovery, assisted shopping, and intelligent transaction workflows. Filtmall Shopping Skill is an early public-facing demo of that direction.

Visit the official website: [https://www.filtalgo.com/](https://www.filtalgo.com/)

## Responsible Use

- Do not print access tokens, refresh tokens, or client secrets in user-facing output.
- Ask the user for confirmation before checkout, cancellation, refund, or after-sale actions.
- Use prices, SKU IDs, product names, order numbers, and payment links exactly as returned by the CLI.
- If search returns no products, try one or two shorter keywords before reporting that the test catalog has no match.

## Current Status

This is a public-preview / MVP skill for demos and developer exploration. The remote catalog is intentionally curated, and the experience will continue to evolve as Filtalgo expands the product range, agent UX, and post-purchase workflows.
