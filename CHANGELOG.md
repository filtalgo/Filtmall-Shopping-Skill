# Changelog

All notable changes to Filtmall Shopping Skill are recorded here. Published versions are also available in [GitHub Releases](https://github.com/filtalgo/Filtmall-Shopping-Skill/releases).

## [Unreleased]

### Changed

- Added explicit mixed-license documentation: Apache-2.0 for the open-source Skill materials, a limited proprietary license for the bundled CLI runtime, and notices for bundled third-party software.

## [1.11.0] - 2026-09-08

### Added

- Added explicit single-ingredient cosmetic information lookup with dedicated routing, evidence boundaries, and medical-safety guidance.

### Changed

- Updated search hydration to request the product identity, SKU, buyer-link, image, and price-evidence fields required by the recommendation renderer.
- Preserved product-detail links and price-evidence source URLs across the complete recommendation flow.

## [1.10.0] - 2026-09-02

### Changed

- Added a two-stage recommendation flow that separates semantic selection from source validation, product binding, ranking, and final Markdown rendering.
- Strengthened product identity across multi-turn shopping so names, images, prices, specifications, detail links, and candidate numbers remain bound to the same product.
- Added dedicated follow-up guidance for product details, comparisons, and research from Filtmall product links.
- Added reviewed local brand knowledge and evidence-bounded brand summaries, with omission when no approved brand information is available.
- Expanded transaction and after-sales guidance while preserving the existing confirmation and safety boundaries.

## [1.6.6] - 2026-08-18

### Changed

- Added source-backed price-advantage evidence to product search results, with an explicit fallback when no verifiable comparison is available.
- Improved optional signed-in search context and added `local`, `dev`, `pre`, and `prod` CLI configuration profiles.
- Refined skill routing and shopping guidance for product discovery, payment status, delivery constraints, images, and safety-sensitive requests.

## [1.6.5] - 2026-08-13

### Changed

- Restored the `SKILL.md` frontmatter description from v1.6.0 to preserve its established activation scope and routing language.
- Kept the v1.6.4 instruction body and shopping workflow unchanged.

## [1.6.4] - 2026-08-13

### Changed

- Rewrote marketplace summaries around the user outcome described in the README: one request, better-fit products, prices that are often the lowest online, verifiable same-product price evidence, and a complete shopping journey.
- Removed implementation details from SkillHub and ClawHub listing copy while keeping technical routing rules in `SKILL.md`.

## [1.6.3] - 2026-08-13

### Changed

- Focused the English and Chinese README pages on Filtmall's agent-native shopping experience and extreme-value positioning.
- Replaced product-level price examples with a concise, bounded statement of the verified price advantage.
- Moved version-specific updates out of the README and into the changelog and GitHub Release notes.
- Kept buyer-link channel details in the Skill's technical instructions and developer command examples.

[1.11.0]: https://github.com/filtalgo/Filtmall-Shopping-Skill/releases/tag/v1.11.0
[1.10.0]: https://github.com/filtalgo/Filtmall-Shopping-Skill/releases/tag/v1.10.0
[1.6.6]: https://github.com/filtalgo/Filtmall-Shopping-Skill/releases/tag/v1.6.6
[1.6.5]: https://github.com/filtalgo/Filtmall-Shopping-Skill/releases/tag/v1.6.5
[1.6.4]: https://github.com/filtalgo/Filtmall-Shopping-Skill/releases/tag/v1.6.4
[1.6.3]: https://github.com/filtalgo/Filtmall-Shopping-Skill/releases/tag/v1.6.3
