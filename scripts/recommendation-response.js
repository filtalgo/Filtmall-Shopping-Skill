'use strict';

const fs = require('fs');
const path = require('path');

const PRICE_DISCLAIMER = '价格可能因账号、地区、会员身份和优惠活动等发生变化。';
const MAX_MODEL_ATTRIBUTES = 12;
const MODEL_ATTRIBUTE_KEY = /品牌|成分|功效|适用|肤质|发质|人群|净含量|规格|分类|类型|包装|香味|香型|质地|肤感|使用方式|使用方法|用法|形态|剂型/u;
const UNSUPPORTED_BRAND_ENDORSEMENT = /知名|口碑|销量|排名|第一|领先|广受|热门|畅销|市场份额|用户评价|消费者认可|官方认证/u;

const CONCEPTS = [
  { key: 'fragrance', label: '留香与香味', query: ['留香', '香味', '香氛', '芳香', '清香'], evidence: ['留香', '香味', '香氛', '芳香', '清香'] },
  {
    key: 'gentle',
    label: '温和低刺激',
    query: ['温和', '低刺激', '不刺激', '敏感肌'],
    evidence: ['温和', '低刺激', '不刺激', '敏感肌', '敏感性皮肤', '敏感性肤质', '所有肤质', '舒缓'],
    sensitiveEvidence: ['敏感肌', '敏感性皮肤', '敏感性肤质', '所有肤质'],
  },
  { key: 'fragrance_free', label: '无香', query: ['无香', '不含香精', '不要香味'], evidence: ['无香', '不含香精', '无香精'] },
  { key: 'hydration', label: '补水保湿', query: ['补水', '保湿', '滋润', '容易干', '干燥'], evidence: ['补水', '保湿', '滋润'] },
  { key: 'fresh', label: '清爽不黏', query: ['清爽', '不黏', '不粘', '黏腻', '不要太黏', '控油'], evidence: ['清爽', '不黏', '不粘', '控油'] },
  { key: 'repair', label: '修护', query: ['修护', '修复', '受损'], evidence: ['修护', '修复', '受损'] },
  { key: 'anti_hair_loss', label: '防脱与防断', query: ['防脱', '防断', '掉发'], evidence: ['防脱', '防断'] },
  { key: 'sun_protection', label: '防晒', query: ['防晒', '防紫外线', 'spf'], evidence: ['防晒', '防紫外线', 'spf'] },
  { key: 'whitening', label: '提亮', query: ['提亮', '美白'], evidence: ['提亮', '美白'] },
  { key: 'acne', label: '控痘', query: ['控痘', '祛痘', '痘肌'], evidence: ['控痘', '祛痘', '痘肌'] },
];

const GENERIC_SPEC_KEYS = new Set(['规格', '默认', '容量', '含量', '净含量', '产品净含量', '包装', '型号']);
const DESCRIPTIVE_SPEC_KEYS = new Set(['颜色', '色号', '口味', '香型', '款式', '版本']);
const UNIT_SPEC_KEYS = new Set(['g', 'kg', 'ml', 'l', '克', '千克', '毫升', '升', '片', '袋', '盒', '支', '瓶', '包', '粒', '枚']);
const DETAIL_FACT_GROUPS = [
  {
    heading: '### 成分、功效与适用信息',
    fields: [
      { label: '主要成分', keys: ['主成分', '成分'] },
      { label: '标注功效', keys: ['功效'] },
      { label: '适合肤质', keys: ['适合肤质', '适用肤质'] },
      { label: '适用发质', keys: ['适用发质'] },
      { label: '适用人群', keys: ['适用人群'] },
      { label: '适用季节', keys: ['适用季节'] },
      { label: '适用范围', keys: ['适用范围'] },
    ],
  },
  {
    heading: '### 使用与商品参数',
    fields: [
      { label: '使用方式', keys: ['使用方式', '使用方法'] },
      { label: '净含量', keys: ['产品净含量', '净含量'] },
      { label: '商品分类', keys: ['分类'] },
      { label: '包装类型', keys: ['包装类型'] },
      { label: '规格类型', keys: ['规格类型'] },
      { label: '香味/香型', keys: ['香味', '香型'] },
      { label: '产地', keys: ['产地'] },
      { label: '保质期', keys: ['保质期（月）', '保质期'] },
    ],
  },
  {
    heading: '### 备案与生产信息',
    fields: [
      { label: '执行标准', keys: ['产品执行的标准编号'] },
      { label: '备案/批准文号', keys: ['备案/批准文号'] },
      { label: '特殊用途化妆品', keys: ['是否为特殊用途化妆品'] },
      { label: '注册人/备案人', keys: ['注册人/备案人的名称'] },
      { label: '生产企业', keys: ['生产企业名称'] },
      { label: '生产许可证', keys: ['生产许可证编号'] },
      { label: '生产日期', keys: ['生产日期'] },
      { label: '商品条形码', keys: ['商品条形码'] },
    ],
  },
];

function loadBrandKnowledge() {
  try {
    const assetPath = path.join(__dirname, '..', 'assets', 'brand-knowledge.json');
    const payload = JSON.parse(fs.readFileSync(assetPath, 'utf8'));
    if (payload?.schemaVersion !== 1 || !Array.isArray(payload.brands)) return [];
    return payload.brands.flatMap((brand) => {
      const brandId = String(brand?.brandId ?? '').trim();
      const brandName = String(brand?.brandName ?? '').replace(/\s+/g, ' ').trim();
      const summaryBody = String(brand?.summary?.body ?? '').replace(/\s+/g, ' ').trim();
      const summaryVersion = Number(brand?.summary?.versionNo);
      if (!brandId || !brandName || !brand?.knowledgeAvailable || !summaryBody || !Number.isInteger(summaryVersion)) return [];
      return [{ brandId, brandName, summaryBody, summaryVersion }];
    });
  } catch {
    return [];
  }
}

const BRAND_KNOWLEDGE = loadBrandKnowledge();

function asArray(value) {
  if (value === undefined || value === null || value === '') return [];
  return Array.isArray(value) ? value : [value];
}

function cleanText(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function boundedText(value, maxLength) {
  const text = cleanText(value);
  if (!text || text.length > maxLength || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(text)) return '';
  return text;
}

function uniqueValues(value) {
  return [...new Set(asArray(value).map(cleanText).filter(Boolean))];
}

function naturalList(values) {
  const items = uniqueValues(values);
  if (items.length <= 1) return items[0] || '';
  return `${items.slice(0, -1).join('、')}和${items.at(-1)}`;
}

function normalizeQuantity(value) {
  return cleanText(value)
    .replace(/(?<=[a-zA-Z\u4e00-\u9fff\d])\s*[xX＊*]\s*(?=\d)/g, '×')
    .replace(/(\d)\s+(?=[a-zA-Z\u4e00-\u9fff])/g, '$1');
}

function flattenFacts(item) {
  const attributes = item.attributes && typeof item.attributes === 'object' ? item.attributes : {};
  return cleanText([item.name, ...Object.entries(attributes).flatMap(([key, value]) => [key, ...asArray(value)])].join(' ')).toLowerCase();
}

function extractBudget(query) {
  const normalized = cleanText(query).replaceAll(',', '');
  const patterns = [
    /(?:预算|价格)?\s*(\d+(?:\.\d+)?)\s*元?\s*(以内|以下|不超过|最多|封顶)/,
    /(?:以内|以下|不超过|最多|封顶)\s*(\d+(?:\.\d+)?)\s*元?/,
    /预算\s*(?:约|大约|差不多)?\s*(\d+(?:\.\d+)?)\s*元?/,
    /(\d+(?:\.\d+)?)\s*元\s*(左右|上下|以内|以下)/,
  ];
  for (const pattern of patterns) {
    const match = normalized.match(pattern);
    if (!match) continue;
    const amount = Number(match[1]);
    if (!Number.isFinite(amount) || amount <= 0) continue;
    const marker = match[2] || '';
    const hard = /以内|以下|不超过|最多|封顶/.test(marker) || /以内|以下|不超过|最多|封顶/.test(match[0]);
    return { amount, hard, text: hard ? `${amount} 元以内` : `${amount} 元左右` };
  }
  return null;
}

function requestedCountInfo(query) {
  const text = cleanText(query);
  const match = text.match(/(?:请|想|要|给我|帮我)?\s*(?:推荐|看看|看|列出|提供|筛选)\s*(?:出|一下|下)?\s*([一二三四五六七八九十\d]+)\s*(?:款|个)/u);
  if (!match) return { count: null, explicit: false };
  const chinese = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 };
  const parsed = Number(match[1]) || chinese[match[1]];
  if (!Number.isInteger(parsed) || parsed <= 0) return { count: null, explicit: false };
  return { count: parsed, explicit: true };
}

function extractRequestedCount(query) {
  return requestedCountInfo(query).count;
}

function extractConcepts(query) {
  const text = cleanText(query).toLowerCase();
  const globalHard = /只看|只考虑|其他都不要|全部必须|都必须/.test(text);
  return CONCEPTS.filter((concept) => concept.query.some((term) => text.includes(term))).map((concept) => {
    const positions = concept.query.map((term) => text.indexOf(term)).filter((index) => index >= 0);
    const first = Math.min(...positions);
    const context = text.slice(Math.max(0, first - 8), first + 12);
    const label = concept.key === 'gentle' && text.includes('敏感肌') ? '敏感肌适用' : concept.label;
    return { ...concept, label, hard: globalHard || concept.key === 'gentle' && text.includes('敏感肌') || /必须|一定要|只要|不能没有|务必/.test(context) };
  });
}

function extractUsage(query) {
  const text = cleanText(query);
  const match = text.match(/(?:一般|平时|大约|约)?\s*((?:每|一)周[^，。；]{0,8}(?:次|片))/);
  return match ? cleanText(match[1]) : '';
}

function conceptEvidence(item, concept, requireHardEvidence = false) {
  const facts = flattenFacts(item);
  const evidence = requireHardEvidence && concept.key === 'gentle' && concept.label === '敏感肌适用'
    ? concept.sensitiveEvidence
    : concept.evidence;
  const matches = evidence.filter((term) => facts.includes(term.toLowerCase()));
  return [...new Set(matches)];
}

function normalizeSpec(spec) {
  if (typeof spec === 'string' || typeof spec === 'number') return normalizeQuantity(spec) || '信息未注明';
  if (!spec || typeof spec !== 'object' || Array.isArray(spec)) return '信息未注明';
  const values = Object.entries(spec).flatMap(([rawKey, rawValue]) => {
    const key = cleanText(rawKey);
    return uniqueValues(rawValue).map((entry) => {
      const value = normalizeQuantity(entry);
      if (!value) return '';
      if (key === '默认' && value === '默认') return '默认规格';
      if (GENERIC_SPEC_KEYS.has(key) || DESCRIPTIVE_SPEC_KEYS.has(key)) return value;
      if (UNIT_SPEC_KEYS.has(key)) return new RegExp(`${key}$`, 'i').test(value) ? value : `${value}${key}`;
      if (key === '尺码') return /码$/u.test(value) ? value : `${value}码`;
      return `${value}（${key}）`;
    });
  }).filter(Boolean);
  return [...new Set(values)].join('、') || '信息未注明';
}

function detailFactValue(attributes, keys) {
  for (const key of keys) {
    const values = uniqueValues(attributes?.[key]);
    if (values.length > 0) return values.join('、');
  }
  return '';
}

function detailFactSections(item) {
  return DETAIL_FACT_GROUPS.flatMap((group) => {
    const facts = group.fields.flatMap((field) => {
      const value = detailFactValue(item.attributes, field.keys);
      return value ? [`- ${field.label}：${normalizeQuantity(value)}`] : [];
    });
    return facts.length > 0 ? [group.heading, '', ...facts, ''] : [];
  });
}

function detailedRecommendationLines(item, copyReason, budget) {
  const supported = item.dimensions.filter((dimension) => dimension.matches.length > 0).map((dimension) => dimension.label);
  const unknown = item.dimensions.filter((dimension) => dimension.matches.length === 0).map((dimension) => dimension.label);
  const lines = ['### 进一步推荐说明', ''];
  lines.push(`- 推荐依据：${sentenceBody(copyReason || fallbackReason(item))}。`);
  if (supported.length > 0) lines.push(`- 明确匹配：${naturalList(supported)}有可核验的商品信息支持。`);
  if (unknown.length > 0) lines.push(`- 仍需留意：${naturalList(unknown)}暂时缺少可核验信息，不能据此承诺实际体验。`);
  if (budget) lines.push(`- 价格关系：当前价格 ${item.priceText}，${budget.hard ? `未超过 ¥${budget.amount} 的预算上限` : `处于 ¥${budget.amount} 左右的参考范围`}。`);
  return lines;
}

function currentSpecLines(item, modelSpec) {
  const lines = [
    '### 当前规格信息',
    '',
    `- 当前选中规格：${modelSpec || item.spec}`,
    `- 当前价格：${item.priceText}`,
  ];
  const stock = Number(item.raw?.stock);
  if (Number.isFinite(stock)) lines.push(`- 库存状态：${stock > 0 ? '有货' : '暂时无货'}（实时情况以商品页为准）`);
  const otherSpecs = uniqueValues(asArray(item.raw?.other_specs).map(normalizeSpec))
    .filter((spec) => spec !== item.spec && spec !== modelSpec);
  if (otherSpecs.length > 0) lines.push(`- 其他可选规格：${otherSpecs.join('、')}`);
  return lines;
}

function validUrl(value) {
  return typeof value === 'string' && /^https?:\/\//i.test(value);
}

function validProductDetailUrl(value, spuId, skuId) {
  if (!validUrl(value)) return false;
  try {
    const url = new URL(value);
    const isFiltmallDetail = /(^|\.)filtalgo\.com$/i.test(url.hostname)
      && url.pathname === '/pages/goods/product/detail';
    if (!isFiltmallDetail) return true;
    const linkedSpuId = cleanText(url.searchParams.get('goodsId'));
    const linkedSkuId = cleanText(url.searchParams.get('skuId'));
    return Boolean(linkedSpuId && linkedSkuId && linkedSpuId === spuId && linkedSkuId === skuId);
  } catch {
    return false;
  }
}

function normalizeBrandName(value) {
  return cleanText(value).toLocaleLowerCase('en-US');
}

function brandFieldValues(item, keys) {
  const attributes = item?.attributes && typeof item.attributes === 'object' ? item.attributes : {};
  return keys.flatMap((key) => uniqueValues(item?.[key] ?? attributes[key]));
}

function titleHasBrandPrefix(title, brandName) {
  const normalizedTitle = normalizeBrandName(title).replace(/^[【\[（(]\s*/u, '');
  return normalizedTitle.startsWith(normalizeBrandName(brandName));
}

function matchBrandKnowledge(item) {
  const ids = new Set(brandFieldValues(item, ['brandId', 'brand_id', '品牌ID', '品牌id']));
  const names = new Set(brandFieldValues(item, ['brandName', 'brand_name', '品牌', '品牌名称']).map(normalizeBrandName));
  return BRAND_KNOWLEDGE.find((brand) => ids.has(brand.brandId)
    || names.has(normalizeBrandName(brand.brandName))
    || titleHasBrandPrefix(item?.name, brand.brandName)) || null;
}

function brandEvidenceRef(item) {
  const brand = item.brandKnowledge;
  return brand ? `brand-summary:${brand.brandId}:v${brand.summaryVersion}` : '';
}

function normalizeItem(item, originalIndex) {
  const price = Number(item.price);
  const brandKnowledge = matchBrandKnowledge(item);
  const spuId = cleanText(item.spu_id);
  const skuId = cleanText(item.recommended_sku_id);
  return {
    originalIndex,
    spuId,
    skuId,
    name: cleanText(item.name),
    price: Number.isFinite(price) ? price : null,
    priceText: cleanText(item.price_text) || (Number.isFinite(price) ? `¥${price}` : '价格信息未注明'),
    image: validUrl(item.image) ? item.image : '',
    spec: normalizeSpec(item.recommended_spec),
    detailUrl: validProductDetailUrl(item.detail_url, spuId, skuId) ? item.detail_url : '',
    attributes: item.attributes && typeof item.attributes === 'object' ? item.attributes : {},
    brandKnowledge,
    priceAdvantage: item.price_advantage,
    raw: item,
  };
}

function scoreItem(item, concepts) {
  if (concepts.length === 0) return { score: 3, dimensions: [], evidenceCount: 0 };
  const dimensions = concepts.map((concept) => {
    const matches = conceptEvidence(item.raw, concept);
    let score = 2.8;
    if (matches.length > 0) {
      const strongFragranceEvidence = concept.key !== 'fragrance' || matches.some((match) => ['留香', '香氛', '芳香'].includes(match));
      const titleEvidence = matches.some((match) => item.name.toLowerCase().includes(match));
      score = strongFragranceEvidence ? (titleEvidence ? 4.5 : 4) : 3.5;
    }
    return { key: concept.key, label: concept.label, score, matches };
  });
  const weighted = dimensions.reduce((sum, dimension, index) => {
    const weight = index === 0 ? (dimensions.length === 1 ? 1 : 0.6) : 0.4 / (dimensions.length - 1);
    return sum + dimension.score * weight;
  }, 0);
  const evidenceCount = dimensions.filter((dimension) => dimension.matches.length > 0).length;
  const cap = dimensions[0].matches.length === 0 ? 3.4 : (evidenceCount < dimensions.length ? 4.4 : 5);
  return { score: Math.min(cap, Math.round(weighted * 10) / 10), dimensions, evidenceCount };
}

function starText(score) {
  if (score >= 4.5) return '★★★★★';
  if (score >= 3.5) return '★★★★☆';
  if (score >= 2.5) return '★★★☆☆';
  if (score >= 1.5) return '★★☆☆☆';
  return '★☆☆☆☆';
}

function normalizePriceAdvantage(item) {
  const advantage = item.priceAdvantage;
  if (!advantage || advantage.status !== 'available') return null;
  const current = Number(advantage.current_landed_price ?? item.price);
  const samples = asArray(advantage.samples).map((sample) => ({
    platform: cleanText(sample?.platform_name),
    comparisonPrice: Number(sample?.comparison_price),
    amount: Number(sample?.advantage_amount),
    rate: Number(sample?.advantage_rate),
    sourceUrl: sample?.source_url,
    collectedAt: cleanText(sample?.collected_at),
  })).filter((sample) => Number.isFinite(current)
    && Number.isFinite(sample.comparisonPrice)
    && sample.comparisonPrice > current
    && Number.isFinite(sample.amount)
    && sample.amount > 0
    && Number.isFinite(sample.rate)
    && sample.rate > 0
    && sample.platform
    && sample.collectedAt
    && validUrl(sample.sourceUrl));
  if (samples.length === 0) return null;
  samples.sort((a, b) => b.comparisonPrice - a.comparisonPrice);
  return { current, ...samples[0] };
}

function overview(item) {
  const clauses = [];
  const descriptions = [];
  const benefits = naturalList(item.attributes['功效']);
  if (benefits) descriptions.push(`主打${benefits}`);

  const fragrance = naturalList(item.attributes['香味']);
  if (fragrance) descriptions.push(`香味为${fragrance}`);

  const audience = ['适用肤质', '适用发质', '适用人群']
    .map((key) => uniqueValues(item.attributes[key]))
    .find((values) => values.length > 0);
  if (audience) {
    const broad = audience.find((value) => /^(所有|全部|全)\S*(肤质|发质|人群)$/u.test(value));
    descriptions.push(`适合${broad || naturalList(audience)}`);
  }
  if (descriptions.length > 0) clauses.push(`商品资料显示，这款商品${descriptions.join('，')}`);

  const netContent = normalizeQuantity(naturalList(item.attributes['产品净含量']));
  const specType = naturalList(item.attributes['规格类型']);
  if (netContent && specType) clauses.push(`净含量为 ${netContent}，属于${specType}`);
  else if (netContent) clauses.push(`净含量为 ${netContent}`);
  else if (specType) clauses.push(`属于${specType}`);

  return clauses.slice(0, 4).join('；');
}

function compactAttributes(attributes) {
  if (!attributes || typeof attributes !== 'object' || Array.isArray(attributes)) return {};
  return Object.fromEntries(Object.entries(attributes).flatMap(([rawKey, rawValue]) => {
    const key = boundedText(rawKey, 40);
    const values = uniqueValues(rawValue).map((value) => boundedText(value, 160)).filter(Boolean);
    return key && MODEL_ATTRIBUTE_KEY.test(key) && values.length > 0 ? [[key, values]] : [];
  }).slice(0, MAX_MODEL_ATTRIBUTES));
}

function modelEvidence(item) {
  const entries = [
    { ref: 'price', label: '当前价格', value: item.priceText },
    { ref: 'spec', label: '规格事实', value: item.raw.recommended_spec },
  ];
  Object.entries(compactAttributes(item.attributes)).forEach(([key, value]) => {
    entries.push({ ref: `attr:${key}`, label: key, value });
  });
  item.dimensions.forEach((dimension) => {
    if (dimension.matches.length > 0) {
      entries.push({ ref: `dimension:${dimension.key}`, label: dimension.label, value: dimension.matches });
    }
  });
  if (item.brandKnowledge) {
    entries.push({
      ref: brandEvidenceRef(item),
      label: `${item.brandKnowledge.brandName}品牌概述`,
      value: item.brandKnowledge.summaryBody,
    });
  }
  return entries;
}

function validEvidenceRefs(value, item) {
  const allowed = new Set(modelEvidence(item).map((entry) => entry.ref));
  return uniqueValues(value).filter((ref) => allowed.has(ref)).slice(0, 6);
}

function requirementSummary(category, concepts, budget, usage) {
  const parts = [];
  if (category) parts.push(`品类：${category}`);
  if (concepts.length > 0) parts.push(`重点：${concepts.map((concept) => concept.label).join('、')}`);
  if (budget) parts.push(`预算：${budget.text}`);
  if (usage) parts.push(`使用频率：${usage}`);
  return parts.length > 0 ? parts : ['按你当前描述的条件筛选可购买商品'];
}

function renderDimension(dimension, dimensionLabels = new Map()) {
  const label = dimensionLabels.get(dimension.key) || dimension.label;
  if (dimension.matches.length === 0) return `- ${label}：暂时无法确认——商品信息未提供可核验证据。`;
  return `- ${label}：${dimension.score.toFixed(1)} 分——商品信息明确包含“${dimension.matches.join('、')}”。`;
}

function renderBudgetDimension(item, budget) {
  if (!budget) return '';
  const limit = budget.hard ? budget.amount : budget.amount * 1.05;
  const fits = Number.isFinite(item.price) && item.price <= limit;
  if (!fits) return `- 预算：不符合——当前价格 ${item.priceText} 超出${budget.hard ? ` ¥${budget.amount}` : ` ¥${budget.amount} 左右`}的范围。`;
  return budget.hard
    ? `- 预算：符合——当前价格 ${item.priceText}，未超过 ¥${budget.amount}。`
    : `- 预算：符合——当前价格 ${item.priceText}，在 ¥${budget.amount} 左右的参考范围内。`;
}

function fallbackReason(item) {
  const matched = item.dimensions.filter((dimension) => dimension.matches.length > 0).map((dimension) => dimension.label);
  const unknown = item.dimensions.filter((dimension) => dimension.matches.length === 0).map((dimension) => dimension.label);
  if (matched.length > 0) {
    return `可核验信息支持${matched.join('、')}；${unknown.length > 0 ? `${unknown.join('、')}缺少明确数据，因此没有作推断。` : '与当前重点匹配。'}`;
  }
  return '符合品类和价格范围，但关键偏好缺少可核验信息，因此保守评分。';
}

function reliablePrimaryNumber(items) {
  return items.length > 0 && items[0].score >= 3.5 && (items.length === 1 || items[0].score - items[1].score >= 0.3) ? 1 : null;
}

function preparedPrimaryNumber(prepared) {
  return Object.prototype.hasOwnProperty.call(prepared, 'primaryEligibleNumber')
    ? prepared.primaryEligibleNumber
    : reliablePrimaryNumber(prepared.items);
}

function resolveDisplayCount(prepared, payload = {}) {
  const available = prepared.items.length;
  if (available === 0) return 0;
  if (prepared.requestedCountExplicit) return Math.min(prepared.requestedCount, available);
  const requested = Number(payload.display_count);
  if (Number.isInteger(requested) && requested >= 1 && requested <= available) return requested;
  return available;
}

function selectDisplayedCandidates(prepared, payload = {}) {
  const count = resolveDisplayCount(prepared, payload);
  return {
    ...prepared,
    items: prepared.items.slice(0, count),
    primaryEligibleNumber: reliablePrimaryNumber(prepared.items),
  };
}

function safeModelText(value, maxLength) {
  const text = boundedText(value, maxLength);
  return text && !/[\r\n]|https?:\/\/|(?:spu|sku|goods)[_-]?id|```|#{2,}/iu.test(text) ? text : '';
}

function groundedModelText(value, maxLength, item, prepared) {
  const text = safeModelText(value, maxLength);
  if (!text) return '';
  const hasUnknownClaim = prepared.concepts.some((concept) => {
    if (conceptEvidence(item.raw, concept).length > 0) return false;
    const mentionsConcept = [...concept.query, ...concept.evidence, concept.label].some((term) => text.includes(term));
    const marksUnknown = /未注明|未标注|没有(?:明确|对应)?证据|证据(?:不足|较弱)|缺少(?:明确|对应)?(?:信息|证据)|无法确认|不作推断/u.test(text);
    return mentionsConcept && !marksUnknown;
  });
  return hasUnknownClaim ? '' : text;
}

function evidenceGroundedModelText(value, maxLength, refs, item, prepared) {
  if (validEvidenceRefs(refs, item).length === 0) return '';
  return groundedModelText(value, maxLength, item, prepared);
}

function brandGroundedModelText(value, refs, item) {
  const expectedRef = brandEvidenceRef(item);
  if (!expectedRef || !uniqueValues(refs).includes(expectedRef)) return '';
  const text = safeModelText(value, 120);
  if (!text) return '';
  const unsupported = text.match(UNSUPPORTED_BRAND_ENDORSEMENT)?.[0];
  if (unsupported && !item.brandKnowledge.summaryBody.includes(unsupported)) return '';
  return text;
}

function normalizeDimensionLabels(prepared, value) {
  const allowed = new Set(prepared.concepts.map((concept) => concept.key));
  const labels = new Map();
  const usedLabels = new Set();
  (Array.isArray(value) ? value : []).forEach((entry) => {
    const key = cleanText(entry?.key);
    const label = safeModelText(entry?.label, 16);
    if (!allowed.has(key) || labels.has(key) || !label || /[:：]/u.test(label) || usedLabels.has(label)) return;
    labels.set(key, label);
    usedLabels.add(label);
  });
  return labels;
}

function safeNoPrimaryText(value) {
  const text = safeModelText(value, 120);
  return text && !/\d(?:\.\d)?\s*分|评分|分差|阈值|封顶|内部规则|模型|代码/u.test(text) ? text : '';
}

function sentenceBody(value) {
  return cleanText(value).replace(/[。！？；，、,.!?\s]+$/gu, '');
}

function fallbackAlternatives(prepared, primaryNumber) {
  const candidates = prepared.items.map((item, index) => ({ item, number: index + 1 }))
    .filter(({ number }) => number !== primaryNumber)
    .slice(primaryNumber ? 0 : 1, primaryNumber ? 2 : 3);
  return candidates.map(({ item, number }) => {
    const dimension = [...item.dimensions]
      .filter((entry) => entry.matches.length > 0)
      .sort((left, right) => right.score - left.score)[0];
    if (dimension) return { number, condition: `你更看重${dimension.label}`, reason: '它在这一维度有明确商品信息支持。' };
    return { number, condition: '你更看重较低的当前价格', reason: `它的当前价格为${item.priceText}。` };
  });
}

function normalizeModelCopy(prepared, payload = {}) {
  const candidateCopies = new Map();
  const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
  candidates.forEach((entry) => {
    const number = Number(entry?.number);
    if (!Number.isInteger(number) || number < 1 || number > prepared.items.length || candidateCopies.has(number)) return;
    const item = prepared.items[number - 1];
    candidateCopies.set(number, {
      recommendedSpec: safeModelText(entry.recommended_spec, 30),
      productOverview: evidenceGroundedModelText(
        entry.product_overview,
        100,
        entry.product_overview_evidence_refs,
        item,
        prepared,
      ),
      brandOverview: brandGroundedModelText(
        entry.brand_overview,
        entry.brand_overview_evidence_refs,
        item,
      ),
      recommendationReason: evidenceGroundedModelText(
        entry.recommendation_reason,
        100,
        entry.recommendation_reason_evidence_refs,
        item,
        prepared,
      ),
    });
  });

  const eligiblePrimary = preparedPrimaryNumber(prepared);
  const requestedPrimary = Number(payload.primary_choice?.number);
  const primaryDescription = requestedPrimary === eligiblePrimary
    ? evidenceGroundedModelText(
      payload.primary_choice?.description,
      100,
      payload.primary_choice?.evidence_refs,
      prepared.items[eligiblePrimary - 1],
      prepared,
    )
    : '';

  const seenAlternatives = new Set();
  const alternatives = (Array.isArray(payload.alternative_choices) ? payload.alternative_choices : []).flatMap((entry) => {
    const number = Number(entry?.number);
    const item = Number.isInteger(number) && number >= 1 && number <= prepared.items.length
      ? prepared.items[number - 1]
      : null;
    const condition = item
      ? evidenceGroundedModelText(entry?.condition, 60, entry?.evidence_refs, item, prepared)
      : '';
    const reason = item
      ? evidenceGroundedModelText(entry?.reason, 60, entry?.evidence_refs, item, prepared)
      : '';
    if (!Number.isInteger(number) || number < 1 || number > prepared.items.length
      || number === eligiblePrimary || seenAlternatives.has(number) || !condition || !reason) return [];
    seenAlternatives.add(number);
    return [{ number, condition, reason }];
  }).slice(0, 2);

  return {
    needsFocus: safeModelText(payload.needs_focus, 120),
    dimensionLabels: normalizeDimensionLabels(prepared, payload.dimension_labels),
    candidateCopies,
    primaryDescription,
    noPrimaryReason: eligiblePrimary === null ? safeNoPrimaryText(payload.no_primary_reason) : '',
    alternatives: alternatives.length > 0 || prepared.items.length < 2
      ? alternatives
      : fallbackAlternatives(prepared, eligiblePrimary),
  };
}

function renderProduct(item, index, primary, copy = {}, dimensionLabels = new Map(), budget = null) {
  const lines = [`#### ${index + 1}. ${item.name}${primary ? '（首选）' : ''}`, ''];
  if (item.image) lines.push(`![${item.name}](${item.image})`, '');
  lines.push(`当前价格：${item.priceText}`);
  lines.push(`推荐规格：${copy.recommendedSpec || item.spec}`);
  lines.push(`商品链接：[打开商品详情](${item.detailUrl})`, '');
  const facts = copy.productOverview || overview(item);
  if (item.brandKnowledge) {
    const brandOverview = copy.brandOverview || item.brandKnowledge.summaryBody;
    lines.push(`品牌概览：${sentenceBody(brandOverview)}。`, '');
  }
  if (facts) lines.push(`商品概览：${sentenceBody(facts)}。`, '');
  lines.push(`综合适配度：${starText(item.score)} ${item.score.toFixed(1)}/5`, '');
  const dimensionLines = item.dimensions.map((dimension) => renderDimension(dimension, dimensionLabels));
  const budgetLine = renderBudgetDimension(item, budget);
  if (budgetLine) dimensionLines.push(budgetLine);
  if (dimensionLines.length > 0) {
    lines.push('关键维度表现：', ...dimensionLines, '');
  }
  lines.push(`推荐理由：${copy.recommendationReason || fallbackReason(item)}`);
  if (item.priceEvidence) {
    const evidence = item.priceEvidence;
    lines.push('', '价格优势：', `- 筛电当前到手价：¥${evidence.current}`, `- ${evidence.platform} 同款同规格：¥${evidence.comparisonPrice}`, `- 在筛电买便宜约 ¥${evidence.amount}，少花约 ${evidence.rate}%`, `- 比价时间：${evidence.collectedAt}`, `- [打开来源链接](${evidence.sourceUrl})`);
  }
  return lines.join('\n');
}

function renderMarkdown(prepared, modelPayload = {}) {
  const { category, concepts, budget, usage, items } = prepared;
  const copy = normalizeModelCopy(prepared, modelPayload);
  const lines = ['### 我理解你的需求', '', ...requirementSummary(category, concepts, budget, usage).map((line) => `- ${line}`), '', '### 你的需求重点', ''];
  if (copy.needsFocus) lines.push(`${sentenceBody(copy.needsFocus)}。`);
  else {
    if (concepts.length > 0) lines.push(`优先核对${concepts.map((concept) => concept.label).join('、')}的真实商品证据，不对缺失信息作推断。`);
    else lines.push('按你已提供的品类和约束筛选；目前没有额外的可评分软偏好。');
    if (budget) lines.push(budget.hard ? `价格不得超过 ¥${budget.amount}。` : `价格以 ¥${budget.amount} 左右为参考。`);
  }
  lines.push('', '### 候选商品', '');
  if (items.length === 0) {
    lines.push('当前没有找到同时满足这些条件、且商品事实足够完整的候选。', '', '### 当前没有合适的首选', '', '当前结果不足以支持可靠首选。你可以放宽一个条件后再试。');
    return lines.join('\n');
  }
  lines.push(`根据以上重点，我筛出了 ${items.length} 款更值得考虑的商品，并按综合适配度从高到低排列。`, '');
  if (prepared.requestedCountExplicit && items.length < prepared.requestedCount) {
    lines.push(`你希望查看 ${prepared.requestedCount} 款；当前只有 ${items.length} 款具备足够的条件证据，以下仅展示这 ${items.length} 款。`, '');
  }
  const primaryNumber = preparedPrimaryNumber(prepared);
  items.forEach((item, index) => {
    lines.push(renderProduct(
      item,
      index,
      primaryNumber === index + 1,
      copy.candidateCopies.get(index + 1),
      copy.dimensionLabels,
      budget,
    ), '');
  });
  if (items.some((item) => item.priceEvidence)) lines.push(PRICE_DISCLAIMER, '');
  if (primaryNumber) {
    const first = items[0];
    const description = copy.primaryDescription || '它在当前可核验条件下综合适配度最高。';
    lines.push('### 如果只买一款', '', `我会选 **${first.name}**。`, '', description, '', `商品链接：[打开商品详情](${first.detailUrl})`);
  } else {
    lines.push(
      '### 当前没有合适的首选',
      '',
      copy.noPrimaryReason || '现有证据不足以把其中一款确定为可靠首选，请根据各商品已明确的信息取舍。',
    );
  }
  if (copy.alternatives.length > 0) {
    lines.push('', '### 其他情况可以这样选', '');
    copy.alternatives.forEach((alternative) => {
      const item = items[alternative.number - 1];
      lines.push(`- 如果${alternative.condition}，可以改选 **${item.name}**，因为${alternative.reason}  `);
      lines.push(`  商品链接：[打开商品详情](${item.detailUrl})。`);
    });
  }
  return `${lines.join('\n').trimEnd()}\n`;
}

function prepareRecommendation(payload, query) {
  const response = payload?.response || {};
  const resultSetSummary = payload?.result?.result_set_summary || response?.result_set_summary;
  const category = cleanText(response?.workflow?.category);
  const budget = extractBudget(query || response.query || '');
  const concepts = extractConcepts(query || response.query || '');
  const usage = extractUsage(query || response.query || '');
  const requested = requestedCountInfo(query || response.query || '');
  const normalized = asArray(response.items)
    .map(normalizeItem)
    .filter((item) => item.name && item.detailUrl && item.price !== null)
    .filter((item) => !budget || item.price <= budget.amount * (budget.hard ? 1 : 1.05))
    .filter((item) => concepts.filter((concept) => concept.hard).every((concept) => conceptEvidence(item.raw, concept, true).length > 0))
    .map((item) => ({ ...item, ...scoreItem(item, concepts) }))
    .sort((a, b) => b.score - a.score || a.originalIndex - b.originalIndex)
    .map((item) => ({ ...item, priceEvidence: normalizePriceAdvantage(item) }));
  return {
    ok: payload?.ok !== false,
    query: cleanText(query || response.query || ''),
    category,
    concepts,
    budget,
    usage,
    requestedCount: requested.count,
    requestedCountExplicit: requested.explicit,
    items: normalized,
    resultSet: resultSetSummary ? {
      result_handle: resultSetSummary.result_handle,
      session_id: resultSetSummary.session_id,
    } : undefined,
  };
}

function selectionDetailResponse(prepared, number, modelPayload = {}) {
  const displayed = selectDisplayedCandidates(prepared, modelPayload);
  if (!Number.isInteger(number) || number < 1 || number > displayed.items.length) {
    throw new Error(`最近一次结果中没有第 ${number} 款商品`);
  }
  const item = displayed.items[number - 1];
  if (!item.detailUrl) throw new Error('当前暂时无法取得这款商品的可靠详情链接');
  const copy = normalizeModelCopy(displayed, modelPayload);
  const rendered = renderProduct(
    item,
    number - 1,
    preparedPrimaryNumber(displayed) === number,
    copy.candidateCopies.get(number),
    copy.dimensionLabels,
    displayed.budget,
  ).split('\n');
  rendered.shift();
  while (rendered[0] === '') rendered.shift();
  const candidateCopy = copy.candidateCopies.get(number) || {};
  const lines = [
    `### 第 ${number} 款商品详情`,
    '',
    `**${item.name}**`,
    '',
    ...rendered,
    '',
    ...detailedRecommendationLines(item, candidateCopy.recommendationReason, displayed.budget),
    '',
    ...currentSpecLines(item, candidateCopy.recommendedSpec),
    '',
    ...detailFactSections(item),
  ];
  const product = productTuples(displayed, modelPayload)[number - 1];
  return {
    ok: prepared.ok,
    tool: 'shopping_agent_response',
    response: {
      status: 'results',
      instruction: '将 markdown 字段原样作为唯一最终回复，不要复述、扩写、缩写或改写链接。',
      markdown: lines.join('\n'),
      products: [product],
      card_order: [{ spu_id: product.spu_id, sku_id: product.sku_id }],
      result_set: prepared.resultSet,
    },
  };
}

function productTuples(prepared, modelPayload = {}) {
  const copy = normalizeModelCopy(prepared, modelPayload);
  return prepared.items.map((item, index) => ({
    number: index + 1,
    spu_id: item.spuId,
    sku_id: item.skuId,
    name: item.name,
    image: item.image,
    price: item.price,
    price_text: item.priceText,
    spec: copy.candidateCopies.get(index + 1)?.recommendedSpec || item.spec,
    detail_url: item.detailUrl,
  }));
}

function finalizeAgentResponse(prepared, modelPayload = {}) {
  const displayed = selectDisplayedCandidates(prepared, modelPayload);
  const markdown = renderMarkdown(displayed, modelPayload);
  const products = productTuples(displayed, modelPayload);
  return {
    ok: prepared.ok,
    tool: 'shopping_agent_response',
    response: {
      status: prepared.items.length > 0 ? 'results' : 'no_results',
      instruction: '将 markdown 字段原样作为唯一最终回复，不要复述、扩写、缩写或重新排序。',
      markdown,
      products,
      card_order: products.map((product) => ({ spu_id: product.spu_id, sku_id: product.sku_id })),
      result_set: prepared.resultSet,
    },
  };
}

function modelTask(prepared) {
  const primaryNumber = reliablePrimaryNumber(prepared.items);
  const requestedDisplayCount = prepared.requestedCountExplicit
    ? Math.min(prepared.requestedCount, prepared.items.length)
    : null;
  return {
    request: prepared.query,
    available_candidate_count: prepared.items.length,
    requested_display_count: requestedDisplayCount,
    constraints: [
      '只填写下方 JSON 槽位；不得生成 Markdown、链接、商品编号以外的内部标识或新增商品。',
      '只能改写候选中明确提供的规格、属性和维度证据；未知信息省略，不推导功效、适用人群、品牌或价格。',
      '只有候选 evidence 含 brand-summary 引用时才填写品牌概览；只能压缩改写该品牌概述，不新增品牌历史、定位、荣誉、知名度、口碑或与当前商品的适配结论。',
      '不得从成分推导未标注功效，不得从使用方式推导肤感、便利性或使用结果；某项需求没有直接证据时明确写未注明或不提。',
      '商品概览、推荐理由、首选描述和次选取舍必须填写对应候选 evidence 中真实存在的 ref；引用只证明来源，正文仍不得超出该证据。',
      'dimension_labels 只能逐键润色给定 scoring_dimensions 的展示名称，不得新增、删除、合并或改变顺序；即使不填写，代码也会按默认名称展示全部评分维度。',
      '每款推荐规格不超过 30 字，品牌概览不超过 120 字，商品概览不超过 100 字，推荐理由不超过 100 字；避免字段名堆叠和重复冒号。',
      'needs_focus 不超过 120 字，只概括用户真正要解决的问题和取舍，不复述字段清单。',
      '如果存在可靠首选，只为给定编号写一段不超过 100 字的首选描述；不得改变首选，也不要复述评分、星级或内部排序。',
      '没有可靠首选时只解释候选证据为什么不足以形成明确优先级，不提评分、分差、阈值、封顶或内部规则。',
      '候选不少于两款时生成 1 至 2 个有真实取舍依据的其他选择，不重复首选。',
      requestedDisplayCount
        ? `用户明确要求展示 ${prepared.requestedCount} 款；display_count 必须填写 ${requestedDisplayCount}，若合格候选不足则展示全部可用候选。`
        : `根据候选之间是否存在对用户有意义的差异，自主填写 1 到 ${prepared.items.length} 的 display_count；不为凑数展示高度重复的候选，也不要沿用固定默认条数。`,
      '只为最终展示范围内、按当前排序从第 1 款开始的候选填写 candidates 文案槽位；不得跳过前排候选或用 display_count 改变排序。',
    ],
    primary_eligible_number: primaryNumber,
    scoring_dimensions: prepared.concepts.map((concept) => ({ key: concept.key, default_label: concept.label })),
    candidates: prepared.items.map((item, index) => ({
      number: index + 1,
      name: item.name,
      recommended_spec_facts: item.raw.recommended_spec,
      deterministic_spec_fallback: item.spec,
      score: item.score,
      evidence: modelEvidence(item),
    })),
    output_schema: {
      display_count: requestedDisplayCount || `从 1 到 ${prepared.items.length} 中选择最终展示数量`,
      needs_focus: '用自然语言概括用户真正要解决的问题和取舍',
      dimension_labels: prepared.concepts.map((concept) => ({
        key: concept.key,
        label: `只润色“${concept.label}”的自然展示名称`,
      })),
      candidates: prepared.items.map((item, index) => ({
        number: index + 1,
        recommended_spec: `只改写第${index + 1}款的真实规格`,
        brand_overview: item.brandKnowledge ? `只压缩改写第${index + 1}款 evidence 中的品牌概述` : null,
        brand_overview_evidence_refs: item.brandKnowledge ? [brandEvidenceRef(item)] : [],
        product_overview: `只概括第${index + 1}款的真实属性`,
        product_overview_evidence_refs: [`第${index + 1}款 evidence 中支持商品概览的 ref`],
        recommendation_reason: `只结合需求说明第${index + 1}款的取舍`,
        recommendation_reason_evidence_refs: [`第${index + 1}款 evidence 中支持推荐理由的 ref`],
      })),
      primary_choice: primaryNumber ? {
        number: primaryNumber,
        description: '为什么只买这一款',
        evidence_refs: [`第${primaryNumber}款 evidence 中支持首选描述的 ref`],
      } : null,
      no_primary_reason: primaryNumber ? null : '解释为什么现有证据不足以形成可靠首选',
      alternative_choices: prepared.items.length > 1 ? [{
        number: 2,
        condition: '什么情况下更适合它',
        reason: '基于真实证据的简短原因',
        evidence_refs: ['该候选 evidence 中支持条件和原因的 ref'],
      }] : [],
    },
  };
}

function buildPreparedAgentResponse(payload, query) {
  const prepared = prepareRecommendation(payload, query);
  if (prepared.items.length === 0) return { prepared: null, response: finalizeAgentResponse(prepared) };
  return {
    prepared,
    response: {
      ok: prepared.ok,
      tool: 'shopping_recommendation_copy_task',
      response: {
        status: 'needs_model_copy',
        instruction: '根据 model_task 只生成一个 JSON 对象，然后调用 recommend finalize；不要直接向用户展示本结果。',
        model_task: modelTask(prepared),
      },
    },
  };
}

function buildAgentResponse(payload, query) {
  return finalizeAgentResponse(prepareRecommendation(payload, query));
}

module.exports = {
  buildAgentResponse,
  buildPreparedAgentResponse,
  extractBudget,
  extractConcepts,
  extractRequestedCount,
  finalizeAgentResponse,
  normalizePriceAdvantage,
  prepareRecommendation,
  selectionDetailResponse,
  starText,
};
