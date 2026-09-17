'use strict';

const { filtalgoProductDetail } = require('./url-policy');

const FIELD_MASK = Object.freeze(['title', 'price', 'currency', 'brand', 'category', 'inventory',
  'spu_attributes', 'skus', 'price_advantage', 'image', 'sku_images', 'price_advantage_source_urls', 'buyer_links']);
const TEXT = {
  'zh-CN': {
    unavailable: '已找到商品，但当前暂时无法获取可靠的商品详情，请稍后重试。',
    partial: '部分商品详情暂不可用，本次仅展示能够核验的商品；因此可展示数量可能少于你的要求。',
    instruction: '将 markdown 原样作为唯一最终回复；不要重新搜索或登录。',
  },
  'en-US': {
    unavailable: 'Products were found, but reliable product details are temporarily unavailable. Please try again later.',
    partial: 'Some product details are unavailable, so only verifiable products are shown and the list may be shorter than requested.',
    instruction: 'Return markdown as the only user-visible response; do not search again or sign in.',
  },
};
const id = value => typeof value === 'string' && /^[\w.:-]+$/.test(value) ? value : '';
const priceValid = value => (typeof value === 'number' || (typeof value === 'string' && value.trim() !== ''))
  && Number.isFinite(Number(value)) && Number(value) >= 0;

function boundUrl(value, spu, sku) {
  return filtalgoProductDetail(value, spu, sku);
}

function localeOf(payload) { return payload?.request_profile?.locale === 'en-US' ? 'en-US' : 'zh-CN'; }
function unavailable(payload) { throw new Error(TEXT[localeOf(payload)].unavailable); }

function convert(item, index) {
  const spu = id(item?.spu_id);
  const skus = Array.isArray(item?.skus) ? item.skus.filter(s => s && typeof s === 'object' && !Array.isArray(s)) : [];
  const skuId = id(item?.default_sku_id) || (skus.length === 1 ? id(skus[0]?.sku_id) : '');
  const matches = skus.filter(s => id(s?.sku_id) === skuId);
  const sku = matches[0];
  if (!spu || !skuId || matches.length !== 1 || (sku.spu_id !== undefined && sku.spu_id !== spu)) return null;
  const links = [sku.buyer_link_targets?.channels?.mobile_h5?.url, sku.detail_url,
    item.buyer_link_targets?.channels?.mobile_h5?.url, item.detail_url, item.selected_url];
  const link = links.map(value => boundUrl(value, spu, skuId)).find(Boolean);
  // A missing SKU price must not borrow another variant's price.
  const price = sku.price;
  const name = sku.title || item.title;
  if (!link || !priceValid(price) || typeof name !== 'string' || !name.trim()) return null;
  const currency = sku.currency || item.currency || 'CNY';
  return {
    rank: index + 1, spu_id: spu, recommended_sku_id: skuId, name,
    price: Number(price), price_text: `${currency === 'CNY' ? '¥' : `${currency} `}${Number(price)}`,
    stock: sku.inventory ?? item.inventory, image: sku.image || item.image || '',
    recommended_spec: sku.specs || {}, other_specs: skus.filter(s => s.sku_id !== skuId).map(s => s.specs || {}),
    attributes: item.spu_attributes || {}, brand_name: typeof item.brand === 'string' ? item.brand : undefined,
    brand_id: item.brand_id, detail_url: link, price_advantage: item.price_advantage,
  };
}

function hydrateSearch(payload, callHydrate) {
  if (payload?.ok !== true) return unavailable(payload);
  const result = payload.result || {};
  const source = result.session_id && result.result_handle ? result
    : result.result_set_summary || payload.response?.result_set_summary || {};
  const response = payload.response || {};
  const original = Array.isArray(response.items) ? response.items : [];
  const summary = result.result_set_summary?.summary || result.summary || {};
  if (!original.length && summary.returned_count === 0 && !result.page_info?.has_more) return payload;
  const session = id(source.session_id), handle = id(source.result_handle);
  let items;
  let count;
  if (!session || !handle) {
    items = original.filter(item => id(item.spu_id) && id(item.recommended_sku_id)
      && typeof item.name === 'string' && item.name.trim() && priceValid(item.price)
      && boundUrl(item.detail_url, item.spu_id, item.recommended_sku_id));
    count = original.length;
  } else {
    let hydrated;
    try {
      hydrated = callHydrate(['search-tools', 'hydrate', '--session-id', session, '--result-handle', handle,
        '--all', '--field-mask', FIELD_MASK.join(','), '--json']);
    } catch { return unavailable(payload); }
    const data = hydrated?.result;
    if (hydrated?.ok !== true || !Array.isArray(data?.items) || data.session_id !== session
      || data.result_handle !== handle || data.page_info?.has_more !== false) return unavailable(payload);
    count = data.items.length;
    const counts = new Map();
    data.items.forEach(item => counts.set(item?.spu_id, (counts.get(item?.spu_id) || 0) + 1));
    items = data.items.filter(item => counts.get(item?.spu_id) === 1).map(convert).filter(Boolean);
  }
  if (!items.length) return unavailable(payload);
  return { ...payload, response: { ...response, items,
    ...(items.length < count ? { availability_notice: TEXT[localeOf(payload)].partial } : {}) } };
}

function unavailableResponse(locale = 'zh-CN') {
  const copy = TEXT[locale === 'en-US' ? 'en-US' : 'zh-CN'];
  return { ok: false, tool: 'shopping_agent_response', response: { status: 'details_unavailable',
    instruction: copy.instruction,
    markdown: `${copy.unavailable}\n`, products: [], card_order: [] } };
}

module.exports = { FIELD_MASK, hydrateSearch, unavailableResponse };
