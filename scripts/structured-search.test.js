'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  bindProductIdentity,
  buildPayload,
  buildStructuredRequest,
  runStructuredSearch,
  selectCategoryAdapter,
} = require('./structured-search');

const adapters = [{
  adapter_name: '个人护理',
  config_version: '个人护理:v5',
  covered_categories: ['面膜', '洗发水'],
}];

const adapterContext = {
  config_version: '个人护理:v5',
  filters: [
    { field: 'category', label: '类目', operators: [{ op: 'eq' }], options: [{ label: '面膜', value: '面膜' }] },
    { field: 'price', label: '价格', operators: [{ op: 'lte' }] },
    { field: 'brand', label: '品牌', operators: [{ op: 'eq' }], options: [{ label: '颐花品', value: 'brand-1' }] },
    { field: 'parameter:effect', label: '功效', operators: [{ op: 'eq' }], options: [{ label: '保湿', value: '保湿' }] },
    {
      field: 'parameter:skin',
      label: '适合肤质',
      operators: [{ op: 'eq' }],
      options: [
        { label: '中性及干性肤质', value: '中性及干性肤质' },
        { label: '干性肤质', value: '干性肤质' },
      ],
    },
  ],
  ranking_preferences: [
    { field: 'parameter:effect', strategy: 'enum_value_score' },
    { field: 'parameter:skin', strategy: 'enum_value_score' },
  ],
};

test('selects the longest category embedded in the request profile', () => {
  assert.deepEqual(
    selectCategoryAdapter(adapters, '想买护肤品', { category: '保湿面膜' }),
    { adapterName: '个人护理', category: '面膜', configVersion: '个人护理:v5' },
  );
});

test('converts profile constraints to filters and omits the duplicated retrieval query', () => {
  const request = buildStructuredRequest({
    query: '想买保湿面膜，100元以内，干性皮肤用',
    profile: {
      category: '保湿面膜',
      audience: '干性皮肤',
      needs: ['补水', '保湿'],
      budget: { max: 100, currency: 'CNY' },
    },
    selection: { adapterName: '个人护理', category: '面膜', configVersion: '个人护理:v5' },
    adapterContext,
    limit: 10,
  });

  assert.equal(request.retrieval_query, undefined);
  assert.deepEqual(request.filters, [
    { field: 'category', op: 'eq', source: 'user', value: '面膜' },
    { field: 'price', op: 'lte', source: 'user', value: 100 },
    { field: 'parameter:effect', op: 'eq', source: 'user', value: '保湿' },
  ]);
  assert.equal(new Set(request.filters.map((filter) => filter.field)).size, request.filters.length);
  assert.deepEqual(request.ranking_preferences, [{
    field: 'parameter:skin',
    strategy: 'enum_value_score',
    params: { values: [{ value: '干性肤质', score: 1 }] },
  }]);
});

test('binds authoritative lookup URLs to both product and sku identities', () => {
  const bound = bindProductIdentity(
    'https://m.filtalgo.com/pages/goods/product/detail?channel_id=skill&skuId=sku-old',
    'spu-1',
    'sku-1',
  );
  const parsed = new URL(bound);
  assert.equal(parsed.searchParams.get('goodsId'), 'spu-1');
  assert.equal(parsed.searchParams.get('skuId'), 'sku-1');
});

test('builds recommendation-compatible response items with lookup links', () => {
  const payload = buildPayload({
    query: '面膜100元以内',
    selection: { adapterName: '个人护理', category: '面膜' },
    toolsUsed: ['start_product_search', 'lookup_catalog'],
    startResult: {
      session_id: 'session-1',
      result_handle: 'result-1',
      summary: { applied_filters: [], returned_count: 1, total_candidates: 1 },
      items: [{
        spu_id: 'spu-1',
        default_sku_id: 'sku-1',
        title: '保湿面膜',
        price: 45,
        currency: 'CNY',
        inventory: 10,
        skus: [{ sku_id: 'sku-1', price: 45, specs: { 规格: '5片' } }],
        spu_attributes: { 功效: ['保湿'] },
      }],
    },
    lookupProducts: [{
      id: 'sku-1',
      selected_url: 'https://m.filtalgo.com/pages/goods/product/detail?channel_id=skill&skuId=sku-1',
      variants: [{ id: 'sku-1', sku: 'sku-1' }],
    }],
  });

  assert.equal(payload.response.count, 1);
  assert.equal(payload.response.items[0].name, '保湿面膜');
  assert.match(payload.response.items[0].detail_url, /goodsId=spu-1/);
  assert.match(payload.response.items[0].detail_url, /skuId=sku-1/);
});

test('runs one structured search and enriches its returned sku ids', () => {
  const calls = [];
  const invoke = (args) => {
    calls.push(args);
    if (args[1] === 'adapters') return { result: { adapters } };
    if (args[1] === 'context') return { result: { adapter: adapterContext } };
    if (args[1] === 'start') {
      return {
        result: {
          session_id: 'session-1',
          result_handle: 'result-1',
          summary: { applied_filters: [], returned_count: 1, total_candidates: 1 },
          items: [{ spu_id: 'spu-1', default_sku_id: 'sku-1', title: '保湿面膜', price: 45, skus: [{ sku_id: 'sku-1' }] }],
        },
      };
    }
    if (args[1] === 'lookup') {
      return { result: { products: [{ id: 'sku-1', selected_url: 'https://m.filtalgo.com/pages/goods/product/detail?skuId=sku-1' }] } };
    }
    throw new Error(`unexpected call: ${args.join(' ')}`);
  };

  const payload = runStructuredSearch({ query: '面膜', profile: { category: '面膜' }, limit: 10, invoke });
  assert.equal(payload.response.count, 1);
  assert.deepEqual(calls.map((args) => args[1]), ['adapters', 'context', 'start', 'lookup']);
  const startBody = JSON.parse(calls[2][calls[2].indexOf('--body') + 1]);
  assert.equal(startBody.retrieval_query, undefined);
});
