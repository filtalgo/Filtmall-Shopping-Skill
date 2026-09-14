'use strict';

const DEFAULT_LIMIT = 10;
const MAX_LIMIT = 50;

function asArray(value) {
  if (value === undefined || value === null || value === '') return [];
  return Array.isArray(value) ? value : [value];
}

function cleanText(value) {
  return String(value ?? '').replace(/\s+/gu, ' ').trim();
}

function normalized(value) {
  return cleanText(value)
    .toLocaleLowerCase('en-US')
    .replace(/皮肤|肌肤/gu, '肤质')
    .replace(/补水/gu, '保湿')
    .replace(/防脱(?!发)/gu, '防脱发')
    .replace(/[\s，。！？、；：,.!?/\\|_\-()[\]{}]/gu, '');
}

function boundedLimit(value) {
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed > 0 ? Math.min(parsed, MAX_LIMIT) : DEFAULT_LIMIT;
}

function optionValue(option) {
  return option && option.value !== undefined ? option.value : option?.label;
}

function definitionOptions(definition) {
  return asArray(definition?.options).filter((option) => option && optionValue(option) !== undefined);
}

function supportsOperator(definition, operator) {
  return asArray(definition?.operators).some((entry) => entry?.op === operator);
}

function optionMatchScore(option, values) {
  const optionTokens = [option?.label, optionValue(option)].map(normalized).filter(Boolean);
  let best = 0;
  for (const value of asArray(values)) {
    const candidate = normalized(value);
    if (!candidate) continue;
    for (const token of optionTokens) {
      if (!token || token === '品牌') continue;
      if (candidate === token) best = Math.max(best, 10000 + token.length);
      else if (candidate.includes(token)) best = Math.max(best, 1000 + token.length);
      else if (token.includes(candidate)) best = Math.max(best, 100 + candidate.length);
    }
  }
  return best;
}

function adaptersFrom(payload) {
  return asArray(payload?.result?.adapters || payload?.adapters);
}

function selectCategoryAdapter(adapters, query, profile = {}) {
  const source = normalized([profile.category, profile.category_label, query].filter(Boolean).join(' '));
  let selected = null;
  for (const adapter of adapters) {
    for (const rawCategory of asArray(adapter?.covered_categories)) {
      const category = cleanText(rawCategory);
      const token = normalized(category);
      if (!token || !source.includes(token)) continue;
      if (!selected || token.length > normalized(selected.category).length) {
        selected = {
          adapterName: cleanText(adapter.adapter_name),
          category,
          configVersion: cleanText(adapter.config_version),
        };
      }
    }
  }
  return selected;
}

function contextAdapter(payload) {
  return payload?.result?.adapter || payload?.adapter || null;
}

function profileBudgetMax(query, profile = {}) {
  const configured = Number(profile?.budget?.max ?? profile?.budget_max);
  if (Number.isFinite(configured) && configured >= 0) return configured;
  const text = cleanText(query).replaceAll(',', '');
  const matches = [
    text.match(/(\d+(?:\.\d+)?)\s*元?\s*(?:以内|以下|不超过|最高|上限)/u),
    text.match(/(?:预算|价格)\s*(?:上限|最高)?\s*(\d+(?:\.\d+)?)\s*元?/u),
  ];
  const match = matches.find(Boolean);
  const parsed = match ? Number(match[1]) : NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function addFilter(filters, filter) {
  const key = JSON.stringify(filter);
  if (!filters.some((entry) => JSON.stringify(entry) === key)) filters.push(filter);
}

function matchingOptions(definition, values) {
  return definitionOptions(definition)
    .map((option) => ({ option, score: optionMatchScore(option, values) }))
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score)
    .map((entry) => entry.option);
}

function filterSources(definition, query, profile) {
  const label = normalized(definition?.label);
  if (label.includes('品牌')) return [profile.brand, profile.brand_name, query];
  if (label.includes('肤质') || label.includes('人群')) return [profile.audience, profile.skin_type];
  if (label.includes('质地') || label.includes('肤感')) return [profile.texture_preference];
  return [profile.needs, profile.requirements];
}

function isSoftPreference(definition) {
  const label = normalized(definition?.label);
  return label.includes('肤质') || label.includes('人群') || label.includes('质地') || label.includes('肤感');
}

function rankingFieldMatches(ranking, definition) {
  const rankingField = cleanText(ranking?.field);
  const filterField = cleanText(definition?.field);
  return rankingField && filterField
    && (rankingField === filterField || rankingField === filterField.replace(/^parameter:/u, ''));
}

function buildStructuredRequest({ query, profile = {}, selection, adapterContext, limit }) {
  const definitions = asArray(adapterContext?.filters);
  const filters = [];
  const rankingPreferences = [];
  const categoryDefinition = definitions.find((definition) => definition?.field === 'category');
  const categoryOption = matchingOptions(categoryDefinition, [selection.category])[0];
  if (categoryDefinition && categoryOption && supportsOperator(categoryDefinition, 'eq')) {
    addFilter(filters, {
      field: 'category',
      op: 'eq',
      source: 'user',
      value: optionValue(categoryOption),
    });
  }

  const priceDefinition = definitions.find((definition) => definition?.field === 'price');
  const budgetMax = profileBudgetMax(query, profile);
  if (priceDefinition && budgetMax !== null && supportsOperator(priceDefinition, 'lte')) {
    addFilter(filters, { field: 'price', op: 'lte', source: 'user', value: budgetMax });
  }

  for (const definition of definitions) {
    if (!definition?.field || ['category', 'price'].includes(definition.field) || !supportsOperator(definition, 'eq')) continue;
    const option = matchingOptions(definition, filterSources(definition, query, profile))[0];
    if (!option) continue;
    if (isSoftPreference(definition)) {
      const ranking = asArray(adapterContext?.ranking_preferences)
        .find((entry) => entry?.strategy === 'enum_value_score' && rankingFieldMatches(entry, definition));
      if (ranking) {
        rankingPreferences.push({
          field: ranking.field,
          strategy: 'enum_value_score',
          params: { values: [{ value: optionValue(option), score: 1 }] },
        });
      }
    } else {
      addFilter(filters, {
        field: definition.field,
        op: 'eq',
        source: 'user',
        value: optionValue(option),
      });
    }
  }

  const request = {
    adapter_name: selection.adapterName,
    limit: boundedLimit(limit),
  };
  const configVersion = cleanText(adapterContext?.config_version || selection.configVersion);
  if (configVersion) request.config_version = configVersion;
  if (filters.length) request.filters = filters;
  if (rankingPreferences.length) request.ranking_preferences = rankingPreferences;

  // The gateway contract reserves retrieval_query for remaining product-name
  // text. The request profile carries structured constraints, so do not send
  // the original natural-language request again after converting it.
  const explicitProductText = cleanText(profile.product_name || profile.product_title || profile.product_keyword);
  if (explicitProductText) request.retrieval_query = explicitProductText;
  return request;
}

function selectedSkuId(item) {
  return cleanText(item?.matched_sku_id || item?.default_sku_id || item?.skus?.[0]?.sku_id);
}

function selectedSpuId(item) {
  return cleanText(item?.spu_id || item?.goods_id || item?.id);
}

function selectedLink(product, skuId) {
  const variants = asArray(product?.variants);
  const variant = variants.find((entry) => [entry?.id, entry?.sku].map(cleanText).includes(skuId));
  const channels = variant?.buyer_link_targets?.channels || product?.buyer_link_targets?.channels || {};
  return cleanText(
    variant?.selected_url
      || variant?.url
      || channels?.mobile_h5?.url
      || product?.selected_url
      || product?.detail_url
      || product?.url,
  );
}

function bindProductIdentity(rawUrl, spuId, skuId) {
  if (!rawUrl || !spuId || !skuId) return '';
  try {
    const url = new URL(rawUrl);
    url.searchParams.set('goodsId', spuId);
    url.searchParams.set('skuId', skuId);
    return url.toString();
  } catch {
    return '';
  }
}

function lookupBySku(products) {
  const bySku = new Map();
  for (const product of asArray(products)) {
    const ids = new Set([
      product?.id,
      ...asArray(product?.variants).flatMap((variant) => [variant?.id, variant?.sku]),
    ].map(cleanText).filter(Boolean));
    for (const id of ids) bySku.set(id, product);
  }
  return bySku;
}

function firstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null);
}

function responseItem(item, index, query, lookupMap) {
  const spuId = selectedSpuId(item);
  const skuId = selectedSkuId(item);
  const skus = asArray(item?.skus);
  const sku = skus.find((entry) => cleanText(entry?.sku_id) === skuId) || skus[0] || {};
  const price = firstDefined(sku?.price, item?.price);
  const currency = cleanText(sku?.currency || item?.currency || 'CNY');
  const lookup = lookupMap.get(skuId);
  const detailUrl = bindProductIdentity(selectedLink(lookup, skuId), spuId, skuId);
  return {
    rank: index + 1,
    spu_id: spuId,
    name: cleanText(item?.title || item?.name || sku?.title),
    price: price === undefined ? null : price,
    price_text: price === undefined ? '' : `${currency === 'CNY' ? '¥' : `${currency} `}${price}`,
    stock: firstDefined(sku?.inventory, sku?.stock, item?.inventory, item?.stock, null),
    image: cleanText(sku?.image || sku?.image_url || item?.image || item?.image_url),
    recommended_sku_id: skuId,
    recommended_spec: sku?.specs && typeof sku.specs === 'object' ? sku.specs : {},
    other_specs: skus.filter((entry) => cleanText(entry?.sku_id) !== skuId).map((entry) => entry?.specs || {}),
    attributes: item?.spu_attributes && typeof item.spu_attributes === 'object' ? item.spu_attributes : {},
    price_advantage: item?.price_advantage || { status: 'unavailable', unavailable_message: '暂无可核验的比价依据', samples: [] },
    detail_url: detailUrl,
    match_basis: `搜索服务针对“${query}”返回并排序；未返回的功效或肤感信息不得推断`,
  };
}

function resultSetSummary(result) {
  return {
    facets: asArray(result?.facets),
    next_actions: asArray(result?.next_actions),
    result_handle: cleanText(result?.result_handle),
    session_id: cleanText(result?.session_id),
    summary: result?.summary || { applied_filters: [], returned_count: 0, total_candidates: 0 },
    warnings: asArray(result?.warnings),
  };
}

function buildPayload({ query, selection, startResult, lookupProducts, toolsUsed }) {
  const lookupMap = lookupBySku(lookupProducts);
  const cards = asArray(startResult?.items);
  const items = cards.map((item, index) => responseItem(item, index, query, lookupMap));
  const summary = resultSetSummary(startResult);
  return {
    ok: true,
    tool: 'search_pipeline',
    tools_used: toolsUsed,
    workflow: {
      mode: 'category_result_set',
      adapter_name: selection.adapterName,
      category: selection.category,
      applied_filters: asArray(startResult?.summary?.applied_filters),
    },
    result: { ...startResult, cards, result_set_summary: summary },
    response: {
      status: items.length ? 'results' : 'no_results',
      query,
      count: items.length,
      workflow: {
        mode: 'category_result_set',
        adapter_name: selection.adapterName,
        category: selection.category,
      },
      items,
      response_rules: {
        one_item_per_spu: true,
        preserve_tool_order: true,
        never_render_empty_table: true,
        unsupported_claims_forbidden: true,
      },
    },
  };
}

function brandSelection(adapters, contexts, query, profile = {}) {
  const values = [profile.brand, profile.brand_name, query];
  for (const adapter of adapters) {
    const adapterName = cleanText(adapter?.adapter_name);
    const context = contexts.get(adapterName);
    const brandDefinition = asArray(context?.filters).find((definition) => normalized(definition?.label).includes('品牌'));
    if (matchingOptions(brandDefinition, values).length) {
      return { adapterName, category: '', configVersion: cleanText(adapter?.config_version) };
    }
  }
  return null;
}

function runStructuredSearch({ query, profile = {}, limit, invoke }) {
  const toolsUsed = [];
  const adaptersPayload = invoke(['search-tools', 'adapters', '--json']);
  toolsUsed.push('list_supported_category_adapters');
  const adapters = adaptersFrom(adaptersPayload);
  let selection = selectCategoryAdapter(adapters, query, profile);
  const contexts = new Map();

  if (!selection) {
    for (const adapter of adapters) {
      const adapterName = cleanText(adapter?.adapter_name);
      if (!adapterName) continue;
      const contextPayload = invoke(['search-tools', 'context', adapterName, '--json']);
      toolsUsed.push('get_category_adapter_context');
      contexts.set(adapterName, contextAdapter(contextPayload));
    }
    selection = brandSelection(adapters, contexts, query, profile);
  }
  if (!selection?.adapterName) return null;

  let adapterContext = contexts.get(selection.adapterName);
  if (!adapterContext) {
    const contextPayload = invoke(['search-tools', 'context', selection.adapterName, '--json']);
    toolsUsed.push('get_category_adapter_context');
    adapterContext = contextAdapter(contextPayload);
  }
  const request = buildStructuredRequest({ query, profile, selection, adapterContext, limit });
  const startPayload = invoke(['search-tools', 'start', '--body', JSON.stringify(request), '--json']);
  toolsUsed.push('start_product_search');
  const startResult = startPayload?.result || {};

  const skuIds = [...new Set(asArray(startResult.items).map(selectedSkuId).filter(Boolean))];
  let lookupProducts = [];
  if (skuIds.length) {
    const lookupPayload = invoke(['search-tools', 'lookup', '--ids', skuIds.join(','), '--json']);
    toolsUsed.push('lookup_catalog');
    lookupProducts = asArray(lookupPayload?.result?.products);
  }
  return buildPayload({ query, selection, startResult, lookupProducts, toolsUsed });
}

module.exports = {
  bindProductIdentity,
  buildPayload,
  buildStructuredRequest,
  runStructuredSearch,
  selectCategoryAdapter,
};
