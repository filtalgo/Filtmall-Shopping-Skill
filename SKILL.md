---
name: filtmall-shopping
description: Use this skill when a user wants to browse, compare, buy, pay for, query orders, track logistics, manage addresses, cancel/refund eligible orders, or apply after-sale service on Filtalgo through the bundled Agent Tool Gateway CLI.
version: 0.2.0
metadata:
  openclaw:
    requires:
      bins:
        - node
---

# Filtmall Shopping

Use the bundled CLI with `node scripts/filtalgo.js`. It talks only to the protocol-adapter Agent Tool Gateway and does not call service, UCP, or ACP endpoints directly.

## First Run

```bash
node scripts/filtalgo.js auth login
node scripts/filtalgo.js doctor --json
```

The current remote test endpoint and OAuth client are built into this bundled CLI. Do not print access tokens, refresh tokens, or client secrets in user-facing output.

This is an internal beta release. The live catalog is a curated remote test catalog with about two dozen official test products across beauty and personal-care categories, such as body wash, skincare, hand care, and related daily-care products. Do not describe the catalog as limited to any single product category.

## Runtime Guidance

- If a command fails because the access token is expired, run `node scripts/filtalgo.js auth refresh --json` first. Ask the user to run `auth login` again only if refresh fails or no refresh token exists.
- If search returns an empty `products` array, do not treat it as a backend failure by default. Try one or two shorter Chinese keywords from the user's request, such as category words, brand words, or product-name fragments. If it is still empty, tell the user that no matching product is currently indexed in the test catalog.
- If checkout/payment preparation says the cart is empty after an expired or abandoned order, explain that the platform may have cleared the cart for the expired checkout and then restart from `cart add-item`.
- Use prices, SKU ids, titles, and payment URLs exactly as returned by the CLI. Never invent products or order state.

## Shopping Flow

```bash
node scripts/filtalgo.js search "沐浴露" --json
node scripts/filtalgo.js cart clear --confirm --json
node scripts/filtalgo.js cart add-item --sku-id <sku_id> --quantity 1 --json
node scripts/filtalgo.js checkout create --json
node scripts/filtalgo.js checkout prepare-payment <checkout_session_id> --handler wallet --json
```

`checkout create` automatically reads the selected cart items and creates a payment-ready checkout session. Use the variant `id` returned by `search` when adding items to the cart.

Give the user the returned `payment_url` so they can complete wallet payment in the buyer page. After payment, use:

```bash
node scripts/filtalgo.js order list --page-size 5 --json
node scripts/filtalgo.js order get <order_sn> --include-items true --json
node scripts/filtalgo.js logistics get <order_sn> --json
```

## Addresses And Order Changes

```bash
node scripts/filtalgo.js address list --json
node scripts/filtalgo.js address create --name <name> --mobile <mobile> --region-path <path> --region-id-path <ids> --detail <detail> --json
node scripts/filtalgo.js address update <address_id> --name <name> --mobile <mobile> --region-path <path> --region-id-path <ids> --detail <detail> --json
node scripts/filtalgo.js address delete <address_id> --confirm --json
node scripts/filtalgo.js order cancel <order_sn> --confirm --json
```

`order cancel` supports unpaid order cancellation and paid-undelivered full refund application, matching the current service behavior.

## After-Sale

Supported service types are `RETURN_MONEY` and `RETURN_GOODS`. Do not request `EXCHANGE_GOODS` in the current version.

```bash
node scripts/filtalgo.js aftersale apply-info --order-sn <order_sn> --order-item-sn <order_item_sn> --json
node scripts/filtalgo.js aftersale reasons --service-type RETURN_GOODS --json
node scripts/filtalgo.js aftersale create --order-sn <order_sn> --order-item-sn <order_item_sn> --service-type RETURN_GOODS --reason <reason> --problem-desc <desc> --apply-refund-price <amount> --json
```
