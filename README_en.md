# Filtmall Shopping Skill

[简体中文](README.md) · [Filtalgo Website](https://www.filtalgo.com/) · [Skill Instructions](SKILL.md) · [Public API Protocol](references/protocol.md)

**Shop through natural-language conversations, from product discovery to purchase.**

Filtmall Shopping is Filtalgo's hosted shopping Agent Skill. Users can describe their needs, search for products, compare prices and specifications, and continue shopping after authorization and confirmation. Product information, prices, and stock availability are determined by actual service responses.

This package uses the **production environment** by default. Member operations require separate authorization, and order submission and payment require user confirmation.

The current version is **2.1.2**, published as [GitHub Release v2.1.2](https://github.com/filtalgo/Filtmall-Shopping-Skill/releases/tag/v2.1.2). The `metadata.version` in `SKILL.md` is `2.1.2`, and the matching release/tag is `v2.1.2`.

## Installation

Copy this entire directory into your host's Skill directory under the name `filtmall-shopping`. Python 3.10 or later is required. No additional dependencies, channel AK/SK credentials, or SSH configuration are needed. The client requests a guest identity and stores it privately.

To connect to another available environment, specify both `--control-url` and `--agent-id`.

## Try It

- “Recommend moisturizing face masks that cost no more than CNY 100.”
- “Compare the specifications and prices of the first and third products.”
- “Show me the items in my shopping cart.”
- “Check the shipping status of this order.”

Member operations require user authorization, and write operations require user confirmation.

## Capabilities

| Stage | What users can do |
| --- | --- |
| Discover | Describe categories, budgets, and needs in natural language to find products |
| Compare | View prices, specifications, stock availability, product information, and available price comparison evidence returned by the service |
| Explore details | View product information and specifications, and look up ingredient information |
| Purchase | Manage the shopping cart after authorization, and preview and confirm orders |
| Follow up | Check orders and shipping, and handle applicable cancellation and after-sales requests |

Available capabilities depend on the target Agent's configuration, business services, and user authorization. The Skill does not fabricate data that the service has not returned.

## How It Works

```mermaid
flowchart LR
    U["User request"] --> A["Host Agent"]
    A --> S["Filtmall Shopping Skill"]
    S --> C["Control Session API"]
    C --> R["Hosted Shopping Agent"]
    R --> C
    C --> S
    S --> A
```

The Skill submits requests through Control's public guest and session APIs, preserving session and request state so conversations can continue and interrupted requests can be recovered. The hosted Agent orchestrates business tools on the server. A guest identity does not constitute member authorization. The public API does not implement the standard A2A Agent Card discovery protocol.

## Developer Quick Start

The recommended approach is single-call mode, with one line of JSON passed through standard input:

```bash
python3 "<skill-dir>/scripts/service.py" --once --format widget
```

```json
{"conversation":"<host-generated conversation ID>","text":"Recommend face masks that cost no more than CNY 100. Search only."}
```

The host should generate a separate identifier for each user and conversation, and reuse it when continuing the conversation. Choose `format` as `widget` (inline HTML), `html` (standalone page), or `md` (Markdown); the same format applies to product cards and cart snapshots. Results contain `answer_file` for response text, `fragment_file`, `page_file`, or `html_file` for product cards, and `cart_file` for the current turn's cart. HTML modes also return `cart_fragment_file` or `cart_page_file`. `cart_status` is `current` or `unavailable`; when unavailable, check the cart before repeating a write operation. The host must be able to access these files and read them as UTF-8. Fields are omitted when the corresponding content is unavailable.

### Choose a display format

| Use case | Request parameter | Product artifact | Cart artifact |
| --- | --- | --- | --- |
| Embed in a chat or host interface | `"format":"widget"` (default) | `fragment_file`, an HTML fragment | `cart_fragment_file`, an HTML fragment |
| Open a standalone page in a browser or WebView | `"format":"html"` | `page_file`, a complete HTML page | `cart_page_file`, a complete HTML page |
| Display Markdown or text | `"format":"md"` | `html_file`, a `.cards.md` file | `cart_file`, a `.cart.md` file |

The format applies to products, carts, checkouts, and after-sales results; response text remains in `answer_file`. Checkout results use `checkout_file`, and after-sales results use `after_sale_file`. In `widget` mode, the corresponding aliases are `checkout_fragment_file` and `after_sale_fragment_file`; in `html` mode, they are `checkout_page_file` and `after_sale_page_file`. In `md` mode, read the respective Markdown files directly. Business documents can produce files without response text, and multiple objects share the corresponding business file. Only documents from the current turn are used. Standalone pages use the same cards as inline fragments, without an extra page heading or status sidebar.

Set `checkout_path` and `after_sale_path` directly or through `out_dirs` to choose output paths. Different artifacts must use different paths. Default filenames are unique per turn, and custom paths are replaced atomically. If `presentation_status=failed`, retain successful files and recover rendering through `resume` in the same conversation; do not repeat the business write. Payment preparation does not prove payment, and a refund amount does not prove receipt. Completed or cancelled checkouts do not show payment prompts or payment links; available detail links and explicit payment facts remain visible.

Cart cards show selected and total product/quantity counts, formatted unit prices, and missing-price notices. HTML folds rows after the first three while retaining all rows; Markdown includes every row. Images share a bounded turn budget and reuse duplicate URLs. Product links still lead to actual store pages. Inline images require host support for `data:` images.

The `--format` startup option sets the default, while a request's `format` overrides it. For example:

```json
{"op":"send","conversation":"<conversation-id>","text":"Show my cart","format":"md"}
```

For inline product cards in **Qoder**, use `widget` and set `out_dirs.fragment_path` directly to an HTML file under Qoder's `visualizations/` directory. Replace the placeholder with that directory's actual absolute path, and display the returned `fragment_file` inline. For an asynchronous request, pass the same path to the `resume` request that retrieves the final result.

```json
{"op":"send","conversation":"<conversation-id>","text":"Recommend a face mask under 100 yuan, search only.","format":"widget",
 "out_dirs":{"fragment_path":"<absolute-path-to-Qoder-visualizations>/products.html"}}
```

An explicitly specified path can overwrite an existing file; choose different filenames when retaining results from multiple turns.

If the network is interrupted or the result is unknown, use `resume` within the same conversation to check the original request; do not automatically resubmit it. Use `cancel` to stop a request and `clear` to clear a conversation. See [SKILL.md](SKILL.md) for the complete request, authorization, address, and presentation rules.

## User Control and Data Boundaries

- Obtain explicit user consent before modifying the shopping cart, addresses, or orders, or initiating after-sales requests.
- Users complete authorization and payment on the corresponding pages. Do not treat a guest identity as member authorization or fabricate payment links or success statuses.
- Credentials and unresolved requests are stored in the host's private state directory and must not be included in model messages or logs.
- The bundled address region data is a snapshot of the pre environment and may only be queried when pre is explicitly selected. It must not be used for production addresses or to infer production region IDs.
- A completed status does not mean payment succeeded. Order and payment outcomes are determined by the actual results from business services.

## Directory Structure

```text
SKILL.md                 # Host invocation and interaction rules
references/protocol.md   # Control public session protocol
scripts/service.py       # Entry point for single-call and persistent service modes
scripts/client.py        # Identity, sessions, and request recovery
scripts/cards.py         # Product card rendering
scripts/commerce_render.py # Cart, checkout, and after-sales rendering
scripts/region_lookup.py # Region lookup for the pre environment
data/regions-pre.json    # Region data snapshot for the pre environment
agents/openai.yaml       # Host display metadata
```

This Skill is licensed under [Apache-2.0](LICENSE). The separate CLI Skill that calls the underlying shopping tools directly is `filtmall-shopping-cli`; its identity and sessions are independent of this Skill.
