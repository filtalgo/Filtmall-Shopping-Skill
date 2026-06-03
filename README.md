# Filtmall Shopping Skill

[中文说明](README.zh-CN.md)

Filtmall Shopping Skill is an agent-ready shopping skill for the Filtalgo/Filtmall commerce platform. It packages a lightweight Node.js CLI, OAuth authorization flow, and Agent Tool Gateway calls into a single folder that can be published to skill marketplaces or used directly by AI agents.

The goal is simple: let an agent help a buyer search products, compare options, manage cart and addresses, create checkout, hand off wallet payment to the buyer page, and then query orders, logistics, cancellation, refund, and after-sale state without giving the agent direct access to internal service APIs.

## Highlights

- Agent-oriented shopping workflow from product search to payment handoff.
- OAuth login through the buyer site with a loopback CLI callback.
- Calls only the protocol-adapter Agent Tool Gateway.
- Bundled CLI requires Node.js 18 or later; no npm install is needed for the packaged skill.
- Current remote test catalog contains curated beauty and personal-care products such as body wash, skincare, hand care, shampoo, and related daily-care goods.
- Supports order query, logistics query, address management, unpaid order cancellation, paid-undelivered refund request, and after-sale requests for `RETURN_MONEY` and `RETURN_GOODS`.

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

## Why This Exists

Most public agent runtimes do not yet provide a full buyer-side OAuth client, checkout runtime, or payment handoff flow. This skill bridges that gap:

1. The CLI opens the Filtalgo buyer authorization page.
2. The buyer signs in and grants explicit scopes.
3. The CLI stores OAuth tokens locally.
4. The agent calls the protocol-adapter Agent Tool Gateway through the CLI.
5. Payment remains buyer-controlled through a browser cashier page.

This keeps the agent useful while preserving the boundary that internal service APIs are not exposed to the agent.

## Security Notes

- Do not print access tokens, refresh tokens, or client secrets in user-facing output.
- The bundled OAuth client is for the remote test environment.
- The CLI sends the real access token only in the HTTP `Authorization` header.
- The agent should never call service, UCP, or ACP endpoints directly; use the Agent Tool Gateway through `scripts/filtalgo.js`.

## Current Status

This is an internal beta / MVP skill. It is intended for controlled demos, remote development testing, and agent workflow validation before a broader public release.

## Brand

Filtmall Shopping Skill is part of the Filtalgo ecosystem, exploring practical agent-commerce workflows for real catalog search, cart operations, buyer-authorized checkout, and post-purchase service.
