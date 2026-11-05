# Filtmall Shopping Skill

[简体中文](README.md) · [Filtalgo Website](https://www.filtalgo.com/) · [Skill Instructions](SKILL.md) · [Public API Protocol](references/protocol.md)

**Shop through natural-language conversations, from product discovery to purchase.**

Filtmall Shopping is Filtalgo's hosted shopping Agent Skill. Users can describe their needs, search for products, compare prices and specifications, and continue shopping after authorization and confirmation. Product information, prices, and stock availability are determined by actual service responses.

This package uses the **production environment** by default. Member operations require separate authorization, and order submission and payment require user confirmation.

## Installation

Copy this entire directory into your host's Skill directory under the name `filtmall-shopping`. Python 3.10 or later is required. No additional dependencies, channel AK/SK credentials, or SSH configuration are needed. The client requests a guest identity and stores it privately.

To connect to another available environment, specify both `--control-url` and `--agent-id`.

## Try It

- “Recommend moisturizing face masks under CNY 100.”
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
{"conversation":"<host-generated conversation ID>","text":"Recommend face masks under CNY 100. Search only."}
```

The host should generate a separate identifier for each user and conversation, and reuse it when continuing the conversation. Results are returned as JSON containing status and artifact paths: `answer_file` for the response text, `fragment_file` for inline cards, and `page_file` for a standalone page. The host must be able to access these files and read them as UTF-8. Fields are omitted when the corresponding content is unavailable.

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
scripts/region_lookup.py # Region lookup for the pre environment
data/regions-pre.json    # Region data snapshot for the pre environment
agents/openai.yaml       # Host display metadata
```

This Skill is licensed under [Apache-2.0](LICENSE). The separate CLI Skill that calls the underlying shopping tools directly is `filtmall-shopping-cli`; its identity and sessions are independent of this Skill.
