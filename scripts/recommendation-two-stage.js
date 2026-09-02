'use strict';

const fs = require('fs');
const path = require('path');

const PRICE_DISCLAIMER = '价格可能因账号、地区、会员身份和优惠活动等发生变化。';
const MODEL_ATTRIBUTE_KEY = /品牌|成分|功效|适用|肤质|发质|人群|净含量|规格|分类|类型|包装|香味|香型|质地|肤感|使用方式|使用方法|用法|形态|剂型/u;
const UNSUPPORTED_BRAND_ENDORSEMENT = /知名|口碑|销量|排名|第一|领先|广受|热门|畅销|市场份额|用户评价|消费者认可|官方认证/u;
const REPUTATION_DIMENSION = /品牌.*(?:口碑|知名|认可|可靠|实力)|(?:口碑|知名度|认可度|品牌力|市场排名)/u;
const UNSUPPORTED_REPUTATION_CLAIM = /口碑|知名度?|认可度|品牌背书|品牌可靠|可靠品牌|市场排名|畅销|热门/u;
const PRICE_PRIORITY = /预算优先|价格优先|低价优先|便宜优先|价格先行|预算先行|低价先行|越便宜越好|先看价格|价格最重要/u;
const PRICE_PRIORITY_CLAIM = /(?:价格|预算|低价).{0,8}(?:首要|第一|最高|优先|先行)|(?:优先|先行).{0,8}(?:价格|预算|低价)/u;
const TEXTURE_PREFERENCE = /清爽|滋润|黏|粘|油腻|轻薄|厚重|肤感|易吸收|不紧绷/u;

class RecommendationTwoStageError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = 'RecommendationTwoStageError';
    this.code = 'RECOMMENDATION_TWO_STAGE_INVALID';
    this.details = details;
  }
}

function fail(message, details) {
  throw new RecommendationTwoStageError(message, details);
}

function text(value, max = 4000) {
  const normalized = String(value ?? '').replace(/\s+/g, ' ').trim();
  if (normalized.length > max || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(normalized)) return '';
  return normalized;
}

function requiredText(value, field, max = 4000) {
  const normalized = text(value, max);
  if (!normalized) fail(`${field} 不能为空`, { field });
  return normalized;
}

function identifier(value, field) {
  const normalized = requiredText(value, field, 128);
  if (!/^[A-Za-z0-9_.:-]+$/u.test(normalized)) fail(`${field} 无效`, { field });
  return normalized;
}

function asArray(value) {
  if (value === undefined || value === null || value === '') return [];
  return Array.isArray(value) ? value : [value];
}

function values(value) {
  return [...new Set(asArray(value).map((entry) => text(entry, 500)).filter(Boolean))];
}

function textValue(value) {
  if (Array.isArray(value)) return value.map(textValue).filter(Boolean).join('、');
  if (value && typeof value === 'object') return Object.entries(value)
    .flatMap(([key, entry]) => values(entry).map((part) => `${key}：${part}`)).join('、');
  return text(value, 1000);
}

function normalizeSpec(value) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const entries = Object.entries(value).flatMap(([key, entry]) => values(entry).map((part) => {
      if (['规格', '默认', '容量', '含量', '净含量', '产品净含量', '包装', '型号'].includes(key)) return part;
      if (/^(g|kg|ml|l|克|千克|毫升|升|片|袋|盒|支|瓶|包|粒|枚)$/iu.test(key)) return new RegExp(`${key}$`, 'iu').test(part) ? part : `${part}${key}`;
      return `${part}（${key}）`;
    }));
    return [...new Set(entries)].join('、') || '以商品详情页为准';
  }
  return text(value, 200) || '以商品详情页为准';
}

function safeUrl(value) {
  const normalized = text(value, 2000);
  if (!/^https?:\/\//iu.test(normalized)) return '';
  try {
    return new URL(normalized).toString();
  } catch {
    return '';
  }
}

function validDetailUrl(value, spuId, skuId) {
  const normalized = safeUrl(value);
  if (!normalized) return '';
  const url = new URL(normalized);
  if (!/(^|\.)filtalgo\.com$/iu.test(url.hostname) || url.pathname !== '/pages/goods/product/detail') return normalized;
  return url.searchParams.get('goodsId') === spuId && url.searchParams.get('skuId') === skuId ? normalized : '';
}

function loadBrandKnowledge() {
  try {
    const asset = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'assets', 'brand-knowledge.json'), 'utf8'));
    if (asset?.schemaVersion !== 1 || !Array.isArray(asset.brands)) return [];
    return asset.brands.flatMap((brand) => {
      const brandId = text(brand?.brandId, 128);
      const brandName = text(brand?.brandName, 128);
      const body = text(brand?.summary?.body, 3000);
      return brand?.knowledgeAvailable && brandId && brandName && body ? [{ brandId, brandName, body }] : [];
    });
  } catch {
    return [];
  }
}

const BRAND_KNOWLEDGE = loadBrandKnowledge();

function matchingBrand(raw) {
  const attributes = raw?.attributes && typeof raw.attributes === 'object' ? raw.attributes : {};
  const ids = new Set(['brandId', 'brand_id', '品牌ID', '品牌id'].flatMap((key) => values(raw?.[key] ?? attributes[key])));
  const names = new Set(['brandName', 'brand_name', '品牌', '品牌名称']
    .flatMap((key) => values(raw?.[key] ?? attributes[key])).map((value) => value.toLocaleLowerCase('en-US')));
  const title = text(raw?.name, 1000).replace(/^[【\[（(]\s*/u, '').toLocaleLowerCase('en-US');
  return BRAND_KNOWLEDGE.find((brand) => ids.has(brand.brandId)
    || names.has(brand.brandName.toLocaleLowerCase('en-US'))
    || title.startsWith(brand.brandName.toLocaleLowerCase('en-US'))) || null;
}

function normalizePriceAdvantage(raw, price) {
  const advantage = raw?.price_advantage;
  if (!advantage || advantage.status !== 'available') return null;
  const current = Number(advantage.current_landed_price ?? price);
  const complete = asArray(advantage.samples).flatMap((sample) => {
    const platform = text(sample?.platform_name, 100);
    const comparison = Number(sample?.comparison_price);
    const amount = Number(sample?.advantage_amount);
    const rate = Number(sample?.advantage_rate);
    const collectedAt = text(sample?.collected_at, 100);
    const sourceUrl = safeUrl(sample?.source_url);
    return Number.isFinite(current) && Number.isFinite(comparison) && comparison > current
      && Number.isFinite(amount) && amount > 0 && Number.isFinite(rate) && rate > 0
      && platform && collectedAt && sourceUrl
      ? [{ current, platform, comparison, amount, rate, collectedAt, sourceUrl }]
      : [];
  }).sort((left, right) => right.comparison - left.comparison);
  return complete[0] || null;
}

function normalizeItem(raw, toolIndex) {
  const spuId = text(raw?.spu_id, 128);
  const skuId = text(raw?.recommended_sku_id, 128);
  const price = Number(raw?.price);
  const detailUrl = validDetailUrl(raw?.detail_url, spuId, skuId);
  if (!spuId || !skuId || !text(raw?.name, 1000) || !Number.isFinite(price) || !detailUrl) return null;
  const attributes = raw?.attributes && typeof raw.attributes === 'object' && !Array.isArray(raw.attributes) ? raw.attributes : {};
  return {
    spu_id: spuId,
    sku_id: skuId,
    tool_index: toolIndex,
    name: text(raw.name, 1000),
    price,
    price_text: text(raw.price_text, 100) || `¥${price}`,
    image: safeUrl(raw.image),
    recommended_spec: normalizeSpec(raw.recommended_spec),
    recommended_spec_facts: raw.recommended_spec,
    detail_url: detailUrl,
    attributes,
    brand: matchingBrand(raw),
    price_advantage: normalizePriceAdvantage(raw, price),
    raw,
  };
}

function extractBudget(query, profile) {
  const profileMax = Number(profile?.budget?.max ?? profile?.budget_max);
  if (Number.isFinite(profileMax) && profileMax > 0) return { max: profileMax, hard: true, text: `${profileMax}元以内` };
  const normalized = text(query, 2000).replaceAll(',', '');
  const hard = normalized.match(/(?:预算|价格)?\s*(\d+(?:\.\d+)?)\s*元?\s*(?:以内|以下|不超过|最多|封顶)/u)
    || normalized.match(/(?:以内|以下|不超过|最多|封顶)\s*(\d+(?:\.\d+)?)\s*元?/u);
  if (hard) return { max: Number(hard[1]), hard: true, text: `${Number(hard[1])}元以内` };
  const soft = normalized.match(/(?:预算\s*)?(?:约|大约|差不多)?\s*(\d+(?:\.\d+)?)\s*元\s*(?:左右|上下)?/u);
  return soft ? { max: Number(soft[1]), hard: false, text: `${Number(soft[1])}元左右` } : null;
}

function normalizedRequestProfile(query, value) {
  const profile = value && typeof value === 'object' && !Array.isArray(value) ? { ...value } : {};
  const normalizedQuery = text(query, 2000);
  const priceFirst = PRICE_PRIORITY.test(normalizedQuery);
  const legacyPreference = text(profile.preference, 200);
  const texturePreference = text(profile.texture_preference, 200);
  if (!texturePreference && legacyPreference && TEXTURE_PREFERENCE.test(legacyPreference) && !PRICE_PRIORITY_CLAIM.test(legacyPreference)) {
    profile.texture_preference = legacyPreference;
  }
  delete profile.preference;
  if (PRICE_PRIORITY_CLAIM.test(texturePreference)) delete profile.texture_preference;
  if (priceFirst) profile.selection_priority = '价格优先';
  else if (PRICE_PRIORITY_CLAIM.test(text(profile.selection_priority || profile.priority, 200))) {
    delete profile.selection_priority;
    delete profile.priority;
  }
  return { profile, selectionPriority: { price_first: priceFirst, label: priceFirst ? '价格优先' : '未明确指定' } };
}

function requestedCount(query) {
  const match = text(query, 2000).match(/(?:推荐|看看|看|列出|提供|筛选)\s*(?:出|一下|下)?\s*([一二三四五六七八九十\d]+)\s*(?:款|个)/u);
  if (!match) return null;
  const chinese = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 };
  const count = Number(match[1]) || chinese[match[1]];
  return Number.isInteger(count) && count > 0 ? count : null;
}

function requestLines(search) {
  const profile = search.request_profile || {};
  const fields = [
    ['品类', profile.category || profile.category_label || search.category],
    ['适用人群', profile.audience],
    ['核心需求', profile.needs],
    ['肤感偏好', profile.texture_preference],
    ['选择优先级', profile.selection_priority || profile.priority],
    ['预算', profile.budget_text || search.budget?.text],
    ['使用频率', profile.usage_frequency || profile.usage],
  ];
  const lines = fields.flatMap(([label, value]) => {
    const normalized = textValue(value);
    return normalized ? [`- ${label}：${normalized}`] : [];
  });
  return lines.length ? lines : [`- 当前需求：${search.query}`];
}

function compactAttributes(attributes) {
  return Object.fromEntries(Object.entries(attributes || {}).flatMap(([key, value]) => {
    const normalizedKey = text(key, 40);
    const normalizedValue = values(value);
    return normalizedKey && MODEL_ATTRIBUTE_KEY.test(normalizedKey) && normalizedValue.length
      ? [[normalizedKey, normalizedValue]]
      : [];
  }).slice(0, 12));
}

function quantityTokens(value) {
  const normalized = textValue(value).toLocaleLowerCase('en-US').replace(/\s+/gu, '');
  return new Set([...normalized.matchAll(/\d+(?:\.\d+)?(?:kg|mg|ml|g|l|克|千克|毫升|升|片|袋|盒|支|瓶|包|粒|枚)/giu)].map((match) => match[0]));
}

function compactAttributesForItem(item) {
  const compact = compactAttributes(item.attributes);
  const specTokens = quantityTokens(item.recommended_spec);
  if (!specTokens.size) return compact;
  return Object.fromEntries(Object.entries(compact).filter(([key, value]) => {
    if (!/净含量|规格|容量/u.test(key)) return true;
    const tokens = quantityTokens(value);
    return !tokens.size || [...tokens].some((token) => specTokens.has(token));
  }));
}

function modelCandidate(item) {
  return {
    spu_id: item.spu_id,
    name: item.name,
    current_price: item.price_text,
    recommended_spec_facts: item.recommended_spec_facts,
    attributes: compactAttributesForItem(item),
  };
}

function createSearchAssessment(payload, query) {
  const response = payload?.response || {};
  const normalizedQuery = text(query || response.query, 2000);
  const normalizedProfile = normalizedRequestProfile(normalizedQuery, payload?.request_profile || response?.request_profile || {});
  const requestProfile = normalizedProfile.profile;
  const budget = extractBudget(normalizedQuery, requestProfile);
  const items = asArray(response.items).map(normalizeItem).filter(Boolean);
  const search = {
    ok: payload?.ok !== false,
    stage: 'search_results',
    query: normalizedQuery,
    request_profile: requestProfile,
    selection_priority: normalizedProfile.selectionPriority,
    category: text(response?.workflow?.category, 200),
    budget,
    requested_count: requestedCount(normalizedQuery),
    result_set: payload?.result?.result_set_summary || response?.result_set_summary,
    items,
  };
  if (!items.length) {
    return { search: null, response: noResultsResponse(search) };
  }
  const modelTask = {
    request: search.query,
    request_profile: search.request_profile,
    selection_priority: search.selection_priority,
    available_candidate_count: items.length,
    requested_display_count: search.requested_count,
    constraints: [
      '从本次搜索候选中选择真正值得展示的商品；可以选择任意子集，不得新增、重复或修改 spu_id。',
      search.selection_priority.price_first
        ? '本轮已明确价格优先：价格必须成为主要评分维度，并实际影响综合分和排序。'
        : '本轮未明确价格优先；预算上限只是资格约束，不等于“价格首要”“预算优先”或“低价优先”，不得自行改写用户优先级。',
      '硬条件不满足的商品不要提交；证据不足的维度写“暂时无法确认”，不要把缺失信息伪装成低性能。',
      '候选事实没有提供品牌口碑、知名度、认可度、销量或市场排名；不得对这些项目数值评分或在文案中下结论，用户确实关心时只能写“暂时无法确认”。',
      '每个参与综合评分的维度都必须出现在 dimension_results 中；不得在最终展示时省略拉低或抬高综合分的维度。',
      search.requested_count
        ? `用户希望查看 ${search.requested_count} 款；有足够合格候选时选择该数量，不设置全局最大条数。`
        : '根据候选差异和展示价值自主决定数量，不沿用固定默认条数，也不设置全局最大条数。',
      'product_overview 只概括真实属性，不从成分推导未标注功效；第一阶段不写推荐理由、首选或次选。',
    ],
    candidates: items.map(modelCandidate),
    output_schema: {
      needs_focus: '站在用户立场完整概括真正需求和优先级；没有可靠内容时省略',
      candidates: [{
        spu_id: '从搜索候选中选择真实 spu_id',
        product_overview: '只根据该商品真实属性概括；没有可靠内容时省略',
        score: '1.0 到 5.0；按用户本轮优先级综合评分',
        dimension_results: [{ label: '参与综合评分的维度', value: '一位小数分数，或“暂时无法确认”' }],
      }],
    },
  };
  return {
    search,
    response: {
      ok: search.ok,
      tool: 'shopping_candidate_assessment_task',
      response: {
        status: 'needs_candidate_assessment',
        instruction: '只生成 model_task.output_schema 对应的 JSON，然后调用 recommend prepare；不要向用户展示本结果。',
        model_task: modelTask,
      },
    },
  };
}

function fallbackNeedsFocus(search) {
  const needs = textValue(search.request_profile?.needs);
  const budget = search.budget?.text;
  if (needs && budget) return `在${budget}的前提下，优先匹配${needs}及其他明确需求，再综合比较价格。`;
  if (needs) return `优先匹配${needs}及其他明确需求，再综合比较候选。`;
  return `按你当前提出的条件筛选候选，并只根据可核验的商品信息进行比较。`;
}

function normalizedNeedsFocus(value, search) {
  const normalized = text(value, 1000);
  if (!normalized) return fallbackNeedsFocus(search);
  if (!search.selection_priority?.price_first && PRICE_PRIORITY_CLAIM.test(normalized)) return fallbackNeedsFocus(search);
  return normalized;
}

function normalizeScore(value, field) {
  const score = Number(value);
  if (!Number.isFinite(score) || score < 1 || score > 5) fail(`${field} 必须为 1.0 到 5.0`, { field });
  return Math.round(score * 10) / 10;
}

function hasReputationEvidence(item) {
  const attributes = item?.attributes && typeof item.attributes === 'object' ? item.attributes : {};
  const evidence = Object.entries(attributes)
    .filter(([key]) => /口碑|知名|评分|评价|销量|排名/u.test(key))
    .map(([key, value]) => `${key}：${textValue(value)}`)
    .join('、');
  return Boolean(evidence);
}

const DIMENSION_EVIDENCE_CONCEPTS = [
  { label: /保湿|补水/u, evidence: /保湿|补水|透明质酸|玻尿酸/u },
  { label: /修护|修复|屏障/u, evidence: /修护|修复|屏障/u },
  { label: /舒缓|镇静/u, evidence: /舒缓|镇静/u },
  { label: /紧致|抗皱|淡纹/u, evidence: /紧致|抗皱|淡纹/u },
  { label: /美白|焕亮|淡斑/u, evidence: /美白|焕亮|淡斑/u },
  { label: /干性|干皮|肤质|人群适用/u, evidence: /干性|干皮|适用肤质|所有肤质|所有人群/u },
  { label: /清爽|滋润|黏腻|质地|肤感/u, evidence: /清爽|滋润|黏腻|质地|肤感/u },
  { label: /留香|香味|香型/u, evidence: /留香|香味|香型/u },
];

function hasDimensionEvidence(item, label) {
  if (REPUTATION_DIMENSION.test(label)) return hasReputationEvidence(item);
  if (/价格|性价比|预算/u.test(label)) return Number.isFinite(item.price);
  const concept = DIMENSION_EVIDENCE_CONCEPTS.find((entry) => entry.label.test(label));
  if (!concept) return true;
  const corpus = `${item.name}、${Object.entries(item.attributes || {}).map(([key, value]) => `${key}：${textValue(value)}`).join('、')}`;
  return concept.evidence.test(corpus);
}

function normalizeDimensions(value, index, item) {
  if (!Array.isArray(value) || !value.length) fail(`第 ${index + 1} 个候选缺少评分维度`);
  return value.slice(0, 12).map((entry, dimensionIndex) => {
    const label = requiredText(entry?.label, `candidates[${index}].dimension_results[${dimensionIndex}].label`, 64);
    let result = requiredText(entry?.value, `candidates[${index}].dimension_results[${dimensionIndex}].value`, 128);
    if (!hasDimensionEvidence(item, label)) result = '暂时无法确认';
    return { label, value: result };
  });
}

function productCard(item, rank) {
  return {
    rank,
    goods_id: item.spu_id,
    sku_id: item.sku_id,
    name: item.name,
    image: item.image,
    price: item.price,
    price_text: item.price_text,
    spec: item.recommended_spec,
    detail_url: item.detail_url,
  };
}

function normalizeBrandOverview(value, item) {
  if (!item.brand) return '';
  const sentences = item.brand.body.split(/(?<=[。！？])/u).map((entry) => entry.trim()).filter(Boolean);
  const concise = text(sentences.slice(0, 2).join(''), 220);
  return concise || text(item.brand.body, 220);
}

function fallbackProductOverview(item) {
  const facts = Object.entries(compactAttributesForItem(item)).flatMap(([key, value]) => {
    const normalized = textValue(value);
    if (!normalized) return [];
    if (/功效/u.test(key)) return [`主打${normalized}`];
    if (/成分/u.test(key)) return [`商品信息标注含${normalized}`];
    if (/适用|肤质|发质|人群/u.test(key)) return [`适用信息为${normalized}`];
    return [`${key}为${normalized}`];
  }).slice(0, 3);
  const prefix = `${item.name}，推荐规格为${item.recommended_spec}`;
  return `${prefix}${facts.length ? `，${facts.join('，')}` : ''}。`;
}

function overviewHasConflictingQuantity(value, item) {
  const specTokens = quantityTokens(item.recommended_spec);
  if (!specTokens.size) return false;
  const conflicting = Object.entries(item.attributes || {}).flatMap(([key, entry]) => {
    if (!/净含量|规格|容量/u.test(key)) return [];
    return [...quantityTokens(entry)].filter((token) => !specTokens.has(token));
  });
  const normalized = text(value, 1000).toLocaleLowerCase('en-US').replace(/\s+/gu, '');
  return conflicting.some((token) => normalized.includes(token));
}

function overviewReferencesAnotherCandidate(value, item, allItems) {
  const normalized = text(value, 1000).toLocaleLowerCase('zh-CN');
  if (!normalized) return false;
  return allItems.some((other) => {
    if (other.spu_id === item.spu_id) return false;
    const otherName = text(other.name, 1000).toLocaleLowerCase('zh-CN');
    if (otherName.length >= 4 && normalized.includes(otherName)) return true;
    const otherBrand = other.brand?.brandName?.toLocaleLowerCase('zh-CN');
    const ownBrand = item.brand?.brandName?.toLocaleLowerCase('zh-CN');
    if (otherBrand && otherBrand !== ownBrand && normalized.includes(otherBrand)) return true;
    const otherSpec = text(other.recommended_spec, 200).toLocaleLowerCase('zh-CN');
    const ownSpec = text(item.recommended_spec, 200).toLocaleLowerCase('zh-CN');
    return otherSpec.length >= 5 && otherSpec !== ownSpec && normalized.includes(otherSpec);
  });
}

function normalizeProductOverview(value, item, allItems) {
  const normalized = text(value, 300);
  return normalized && !overviewReferencesAnotherCandidate(normalized, item, allItems) && !overviewHasConflictingQuantity(normalized, item)
    ? normalized
    : fallbackProductOverview(item);
}

function sanitizeGeneratedProse(value, max = 1000) {
  const normalized = text(value, max);
  if (!normalized || !UNSUPPORTED_REPUTATION_CLAIM.test(normalized)) return normalized;
  const pieces = normalized.split(/([，；。])/u);
  let safe = '';
  for (let index = 0; index < pieces.length; index += 2) {
    const clause = pieces[index] || '';
    const delimiter = pieces[index + 1] || '';
    if (!UNSUPPORTED_REPUTATION_CLAIM.test(clause)) safe += `${clause}${delimiter}`;
  }
  return text(safe, max);
}

function prepareRecommendation(search, payload) {
  if (!search || search.stage !== 'search_results' || !Array.isArray(search.items) || !search.items.length) fail('缺少有效的本次搜索结果');
  if (!payload || !Array.isArray(payload.candidates) || !payload.candidates.length) fail('第一阶段没有提交候选商品');
  const byId = new Map(search.items.map((item) => [item.spu_id, item]));
  const seen = new Set();
  const candidates = payload.candidates.map((assessment, index) => {
    const spuId = identifier(assessment?.spu_id, `candidates[${index}].spu_id`);
    if (seen.has(spuId)) fail('候选商品不能重复', { spu_id: spuId });
    seen.add(spuId);
    const item = byId.get(spuId);
    if (!item) fail('候选商品不在本次搜索结果中', { spu_id: spuId });
    if (search.budget?.hard && item.price > search.budget.max) fail('候选商品超过硬预算', { spu_id: spuId });
    return {
      ...item,
      product_overview: normalizeProductOverview(assessment.product_overview, item, search.items),
      brand_overview: normalizeBrandOverview(assessment.brand_overview, item),
      score: normalizeScore(assessment.score, `candidates[${index}].score`),
      dimension_results: normalizeDimensions(assessment.dimension_results, index, item),
    };
  }).sort((left, right) => right.score - left.score || left.tool_index - right.tool_index);
  const prepared = {
    ok: search.ok,
    stage: 'recommendation_prepared',
    query: search.query,
    request_profile: search.request_profile,
    selection_priority: search.selection_priority,
    request_lines: requestLines(search),
    needs_focus: normalizedNeedsFocus(payload.needs_focus, search),
    budget: search.budget,
    requested_count: search.requested_count,
    result_set: search.result_set,
    candidates,
    product_cards: candidates.map((candidate, index) => productCard(candidate, index + 1)),
  };
  return {
    prepared,
    response: {
      ok: prepared.ok,
      tool: 'shopping_recommendation_decision_task',
      response: {
        status: 'needs_recommendation_decision',
        instruction: '只根据已排序候选生成推荐理由、首选和条件式次选，然后调用 recommend finalize；不要重新评分或直接回复用户。',
        model_task: decisionTask(prepared),
      },
    },
  };
}

function decisionTask(prepared) {
  return {
    request: prepared.query,
    needs_focus: prepared.needs_focus,
    constraints: [
      '第二阶段不得增删候选、改变 score、dimension_results 或排序。',
      '为每款候选填写 recommendation_reason，说明它为什么适合当前用户以及相对取舍。',
      '不得补充品牌口碑、知名度、认可度、销量、市场排名或“品牌可靠”等未提供结论。',
      '只有排序第一且 score 不低于 3.5 的候选可以作为 primary_choice；否则填写 no_primary_reason。',
      'alternative_choices 只能选择候选且不能重复首选；没有真实差异时可以省略。',
      '所有商品引用使用真实 spu_id；不得生成 Markdown、链接、价格、规格或商品事实。',
    ],
    candidates: prepared.candidates.map((candidate) => ({
      spu_id: candidate.spu_id,
      name: candidate.name,
      score: candidate.score,
      dimension_results: candidate.dimension_results,
      product_overview: candidate.product_overview,
    })),
    output_schema: {
      candidate_reasons: prepared.candidates.map((candidate) => ({
        spu_id: candidate.spu_id,
        recommendation_reason: '为什么适合这位用户及其关键取舍',
      })),
      primary_choice: prepared.candidates[0]?.score >= 3.5
        ? { spu_id: prepared.candidates[0].spu_id, reason: '整体最值得选的原因和关键取舍' }
        : null,
      no_primary_reason: prepared.candidates[0]?.score >= 3.5 ? null : '当前没有可靠首选的原因',
      alternative_choices: prepared.candidates.length > 1
        ? [{ spu_id: '非首选候选的真实 spu_id', condition: '更重视某项真实差异', reason: '该优势及相对首选的取舍' }]
        : [],
    },
  };
}

function stars(score) {
  if (score >= 4.5) return '★★★★★';
  if (score >= 3.5) return '★★★★☆';
  if (score >= 2.5) return '★★★☆☆';
  if (score >= 1.5) return '★★☆☆☆';
  return '★☆☆☆☆';
}

function numberText(value) {
  const number = Number(value);
  return Number.isFinite(number) ? String(Math.round((number + Number.EPSILON) * 10) / 10) : '';
}

function renderCandidate(lines, candidate, index, reason) {
  lines.push('', `#### ${index + 1}. ${candidate.name}`, '');
  if (candidate.image) lines.push(`![${candidate.name}](${candidate.image})`, '');
  lines.push(`当前价格：${candidate.price_text}`);
  lines.push(`推荐规格：${candidate.recommended_spec}`);
  lines.push(`商品链接：[打开商品详情](${candidate.detail_url})`);
  if (candidate.brand_overview) lines.push('', `品牌概览：${candidate.brand_overview}`);
  if (candidate.product_overview) lines.push('', `商品概览：${candidate.product_overview}`);
  lines.push('', `综合适配度：${stars(candidate.score)} ${candidate.score.toFixed(1)}/5`);
  lines.push('', '关键维度表现：');
  candidate.dimension_results.forEach((dimension) => lines.push(`- ${dimension.label}：${dimension.value}`));
  if (reason) lines.push('', `推荐理由：${reason}`);
  const advantage = candidate.price_advantage;
  if (advantage) {
    lines.push('', '价格优势：');
    lines.push(`- 筛电当前到手价：${numberText(advantage.current)}元`);
    lines.push(`- ${advantage.platform} 同款同规格：${numberText(advantage.comparison)}元`);
    lines.push(`- 在筛电买便宜约 ${numberText(advantage.amount)}元，少花约 ${numberText(advantage.rate <= 1 ? advantage.rate * 100 : advantage.rate)}%`);
    lines.push(`- 比价时间：${advantage.collectedAt}`);
    lines.push(`- [打开来源链接](${advantage.sourceUrl})`);
  }
}

function renderPrepared(prepared) {
  const lines = ['### 我理解你的需求', '', ...prepared.request_lines];
  if (prepared.needs_focus) lines.push('', '### 你的需求重点', '', prepared.needs_focus);
  lines.push('', '### 候选商品', '', `根据以上需求，我筛出了 ${prepared.candidates.length} 款更值得考虑的商品，并按综合适配度从高到低排列。`);
  let hasPrice = false;
  prepared.candidates.forEach((candidate, index) => {
    renderCandidate(lines, candidate, index, '');
    hasPrice = hasPrice || Boolean(candidate.price_advantage);
  });
  if (hasPrice) lines.push('', PRICE_DISCLAIMER);
  return `${lines.join('\n').trimEnd()}\n`;
}

function keyedEntries(entries, field) {
  const result = new Map();
  if (entries === undefined) return result;
  if (!Array.isArray(entries)) fail(`${field} 必须为数组`);
  entries.forEach((entry, index) => {
    const spuId = identifier(entry?.spu_id, `${field}[${index}].spu_id`);
    if (result.has(spuId)) fail(`${field} 不能包含重复商品`, { spu_id: spuId });
    result.set(spuId, entry);
  });
  return result;
}

function finalizeRecommendation(prepared, payload = {}) {
  if (!prepared || prepared.stage !== 'recommendation_prepared' || !Array.isArray(prepared.candidates) || !prepared.candidates.length) fail('缺少有效的第一阶段推荐结果');
  const byId = new Map(prepared.candidates.map((candidate) => [candidate.spu_id, candidate]));
  const reasons = keyedEntries(payload.candidate_reasons, 'candidate_reasons');
  for (const spuId of reasons.keys()) if (!byId.has(spuId)) fail('推荐理由引用了非候选商品', { spu_id: spuId });
  let primary = null;
  if (payload.primary_choice) {
    const spuId = identifier(payload.primary_choice.spu_id, 'primary_choice.spu_id');
    const candidate = byId.get(spuId);
    if (!candidate) fail('首选不是候选商品', { spu_id: spuId });
    if (prepared.candidates[0].spu_id !== spuId || candidate.score < 3.5) fail('首选必须是评分最高且不低于 3.5 的候选', { spu_id: spuId });
    const reason = sanitizeGeneratedProse(payload.primary_choice.reason, 1000);
    if (reason) primary = { spu_id: spuId, reason };
  }
  const alternatives = [];
  if (payload.alternative_choices !== undefined) {
    if (!Array.isArray(payload.alternative_choices)) fail('alternative_choices 必须为数组');
    const seen = new Set();
    payload.alternative_choices.forEach((entry, index) => {
      const spuId = identifier(entry?.spu_id, `alternative_choices[${index}].spu_id`);
      if (!byId.has(spuId)) fail('次选不是候选商品', { spu_id: spuId });
      if (primary?.spu_id === spuId) fail('次选不能重复首选', { spu_id: spuId });
      if (seen.has(spuId)) fail('次选不能重复', { spu_id: spuId });
      seen.add(spuId);
      const condition = sanitizeGeneratedProse(entry.condition, 300);
      const reason = sanitizeGeneratedProse(entry.reason, 600);
      if (condition && reason) alternatives.push({ spu_id: spuId, condition, reason });
    });
  }
  const lines = ['### 我理解你的需求', '', ...prepared.request_lines];
  if (prepared.needs_focus) lines.push('', '### 你的需求重点', '', prepared.needs_focus);
  lines.push('', '### 候选商品', '', `根据以上需求，我筛出了 ${prepared.candidates.length} 款更值得考虑的商品，并按综合适配度从高到低排列。`);
  if (prepared.requested_count && prepared.candidates.length < prepared.requested_count) {
    lines.push('', `你希望查看 ${prepared.requested_count} 款；当前只有 ${prepared.candidates.length} 款具备足够证据，因此只展示这些候选。`);
  }
  let hasPrice = false;
  prepared.candidates.forEach((candidate, index) => {
    const entry = reasons.get(candidate.spu_id);
    renderCandidate(lines, candidate, index, sanitizeGeneratedProse(entry?.recommendation_reason, 1000));
    hasPrice = hasPrice || Boolean(candidate.price_advantage);
  });
  if (hasPrice) lines.push('', PRICE_DISCLAIMER);
  if (primary) {
    const candidate = byId.get(primary.spu_id);
    lines.push('', '### 如果只买一款', '', `我会选 **${candidate.name}**。`, '', primary.reason, '', `商品链接：[打开商品详情](${candidate.detail_url})。`);
  } else {
    const noPrimary = text(payload.no_primary_reason, 1000);
    if (noPrimary) lines.push('', '### 当前没有合适的首选', '', noPrimary);
  }
  if (alternatives.length) {
    lines.push('', '### 其他情况可以这样选', '');
    alternatives.forEach((alternative) => {
      const candidate = byId.get(alternative.spu_id);
      lines.push(`- 如果${alternative.condition}，可以改选 **${candidate.name}**，因为${alternative.reason}  `);
      lines.push(`  商品链接：[打开商品详情](${candidate.detail_url})。`);
    });
  }
  const products = prepared.candidates.map((candidate, index) => ({
    number: index + 1,
    spu_id: candidate.spu_id,
    sku_id: candidate.sku_id,
    name: candidate.name,
    image: candidate.image,
    price: candidate.price,
    price_text: candidate.price_text,
    spec: candidate.recommended_spec,
    detail_url: candidate.detail_url,
  }));
  return {
    ok: prepared.ok,
    tool: 'shopping_agent_response',
    response: {
      status: 'results',
      instruction: '下一条 assistant 消息必须从 markdown 的第一个 # 开始，并逐字输出完整 markdown；不得添加任何前缀、解释、摘要或收尾。',
      markdown: `${lines.join('\n').trimEnd()}\n`,
      products,
      card_order: products.map((product) => ({ spu_id: product.spu_id, sku_id: product.sku_id })),
      result_set: prepared.result_set,
    },
  };
}

function noResultsResponse(search) {
  const lines = ['### 我理解你的需求', '', ...requestLines(search), '', '### 候选商品', '', '当前没有找到同时满足这些条件、且商品事实足够完整的候选。', '', '### 当前没有合适的首选', '', '当前结果不足以支持可靠首选。你可以放宽一个条件后再试。'];
  return {
    ok: search.ok,
    tool: 'shopping_agent_response',
    response: {
      status: 'no_results',
      instruction: '将 markdown 字段原样作为唯一最终回复。',
      markdown: `${lines.join('\n')}\n`,
      products: [],
      card_order: [],
      result_set: search.result_set,
    },
  };
}

function detailFactLines(candidate) {
  return Object.entries(candidate.attributes || {}).flatMap(([key, value]) => {
    const normalized = textValue(value);
    return normalized ? [`- ${key}：${normalized}`] : [];
  });
}

function currentSpecLines(candidate) {
  const lines = [
    '### 当前规格信息',
    '',
    `- 当前选中规格：${candidate.recommended_spec}`,
    `- 当前价格：${candidate.price_text}`,
  ];
  const stock = Number(candidate.raw?.stock);
  if (Number.isFinite(stock)) lines.push(`- 库存状态：${stock > 0 ? '有货' : '暂时无货'}（实时情况以商品页为准）`);
  const otherSpecs = [...new Set(asArray(candidate.raw?.other_specs).map(normalizeSpec).filter((spec) => spec && spec !== candidate.recommended_spec))];
  if (otherSpecs.length) lines.push(`- 其他可选规格：${otherSpecs.join('、')}`);
  return lines;
}

function selectionDetailResponse(prepared, number, finalPayload = {}) {
  if (!Number.isInteger(number) || number < 1 || number > prepared.candidates.length) fail(`最近一次结果中没有第 ${number} 款商品`);
  const candidate = prepared.candidates[number - 1];
  const reasonEntry = asArray(finalPayload.candidate_reasons).find((entry) => entry?.spu_id === candidate.spu_id);
  const lines = [`### 第 ${number} 款商品详情`, '', `**${candidate.name}**`, ''];
  if (candidate.image) lines.push(`![${candidate.name}](${candidate.image})`, '');
  lines.push(`当前价格：${candidate.price_text}`);
  lines.push(`当前规格：${candidate.recommended_spec}`);
  lines.push(`商品链接：[打开商品详情](${candidate.detail_url})`);
  if (candidate.brand_overview) lines.push('', `品牌概览：${candidate.brand_overview}`);
  if (candidate.product_overview) lines.push('', `商品概览：${candidate.product_overview}`);
  lines.push('', `综合适配度：${stars(candidate.score)} ${candidate.score.toFixed(1)}/5`, '', '关键维度表现：');
  candidate.dimension_results.forEach((dimension) => lines.push(`- ${dimension.label}：${dimension.value}`));
  if (reasonEntry?.recommendation_reason) lines.push('', '### 进一步推荐说明', '', sanitizeGeneratedProse(reasonEntry.recommendation_reason, 1000));
  lines.push('', ...currentSpecLines(candidate));
  const facts = detailFactLines(candidate);
  if (facts.length) lines.push('', '### 商品参数', '', ...facts);
  const product = productCard(candidate, 1);
  return {
    ok: prepared.ok,
    tool: 'shopping_agent_response',
    response: {
      status: 'results',
      instruction: '将 markdown 字段原样作为唯一最终回复，不要缩写或改写链接。',
      markdown: `${lines.join('\n').trimEnd()}\n`,
      products: [{ number: 1, spu_id: product.goods_id, sku_id: product.sku_id, name: product.name, image: product.image, price: product.price, price_text: product.price_text, spec: product.spec, detail_url: product.detail_url }],
      card_order: [{ spu_id: product.goods_id, sku_id: product.sku_id }],
      result_set: prepared.result_set,
    },
  };
}

module.exports = {
  RecommendationTwoStageError,
  createSearchAssessment,
  prepareRecommendation,
  finalizeRecommendation,
  selectionDetailResponse,
};
