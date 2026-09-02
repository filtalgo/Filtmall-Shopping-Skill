#!/usr/bin/env node

const path = require('path');
const fs = require('fs');
const os = require('os');
const crypto = require('crypto');
const { spawnSync } = require('child_process');
const {
  createSearchAssessment,
  prepareRecommendation,
  finalizeRecommendation,
  selectionDetailResponse,
} = require('./recommendation-two-stage');

const cli = path.join(__dirname, '..', 'assets', 'filtalgo-cli.cjs');
const inputArgs = process.argv.slice(2);
const stateDirectory = path.join(os.tmpdir(), 'filtmall-shopping-recommendations');
const stateLifetimeMs = 15 * 60 * 1000;

function optionValue(args, name) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : '';
}

function statePath(token) {
  if (!/^[0-9a-f-]{36}$/i.test(token)) throw new Error('推荐上下文无效，请重新搜索');
  return path.join(stateDirectory, `${token}.json`);
}

function cleanupExpiredStates() {
  if (!fs.existsSync(stateDirectory)) return;
  const now = Date.now();
  fs.readdirSync(stateDirectory, { withFileTypes: true }).forEach((entry) => {
    if (!entry.isFile() || !/^[0-9a-f-]{36}\.json$/i.test(entry.name)) return;
    const file = path.join(stateDirectory, entry.name);
    try {
      if (now - fs.statSync(file).mtimeMs > stateLifetimeMs) fs.unlinkSync(file);
    } catch {}
  });
}

function storeState(state) {
  fs.mkdirSync(stateDirectory, { recursive: true, mode: 0o700 });
  cleanupExpiredStates();
  const token = crypto.randomUUID();
  fs.writeFileSync(statePath(token), `${JSON.stringify(state)}\n`, { encoding: 'utf8', flag: 'wx', mode: 0o600 });
  return token;
}

function loadState(token) {
  const file = statePath(token);
  const stat = fs.statSync(file);
  if (Date.now() - stat.mtimeMs > stateLifetimeMs) {
    fs.unlinkSync(file);
    throw new Error('推荐上下文已过期，请重新搜索');
  }
  return { file, state: JSON.parse(fs.readFileSync(file, 'utf8')) };
}

function saveState(file, state) {
  fs.writeFileSync(file, `${JSON.stringify(state)}\n`, { encoding: 'utf8', mode: 0o600 });
}

function productRefIdentity(args) {
  const value = optionValue(args, '--product-ref');
  if (!value) return null;
  try {
    const url = new URL(value);
    if (!/(^|\.)filtalgo\.com$/i.test(url.hostname) || url.pathname !== '/pages/goods/product/detail') return null;
    const spuId = String(url.searchParams.get('goodsId') || '').trim();
    const skuId = String(url.searchParams.get('skuId') || '').trim();
    if (!spuId || !skuId || !/^[\w-]+$/u.test(spuId) || !/^[\w-]+$/u.test(skuId)) return null;
    return { sourceUrl: url.toString(), spuId, skuId };
  } catch {
    return null;
  }
}

function lookupArgsForProductRef(args, identity) {
  if (!identity || args[0] !== 'search-tools' || args[1] !== 'lookup') return args;
  const index = args.indexOf('--product-ref');
  return [...args.slice(0, index), ...args.slice(index + 2), '--ids', identity.skuId];
}

function bindMobileUrl(target, sourceUrl) {
  if (!target || typeof target !== 'object') return;
  target.url = sourceUrl;
}

function bindProductRefLookup(payload, identity) {
  const products = payload?.result?.products;
  if (!identity || !Array.isArray(products)) return payload;
  products.forEach((product) => {
    const variants = Array.isArray(product?.variants) ? product.variants : [];
    const identities = new Set([product?.id, ...variants.flatMap((variant) => [variant?.id, variant?.sku])]
      .filter(Boolean).map(String));
    if (!identities.has(identity.skuId)) return;
    product.spu_id = identity.spuId;
    product.recommended_sku_id = identity.skuId;
    product.url = identity.sourceUrl;
    product.detail_url = identity.sourceUrl;
    product.selected_url = identity.sourceUrl;
    if (product.metadata && typeof product.metadata === 'object') product.metadata.selected_url = identity.sourceUrl;
    bindMobileUrl(product.buyer_link_targets?.channels?.mobile_h5, identity.sourceUrl);
    bindMobileUrl(product.metadata?.buyer_link_targets?.channels?.mobile_h5, identity.sourceUrl);
    variants.forEach((variant) => {
      if (![variant?.id, variant?.sku].filter(Boolean).map(String).includes(identity.skuId)) return;
      variant.url = identity.sourceUrl;
      variant.selected_url = identity.sourceUrl;
      bindMobileUrl(variant.buyer_link_targets?.channels?.mobile_h5, identity.sourceUrl);
    });
  });
  return payload;
}

if (inputArgs[0] === 'recommend') {
  const action = inputArgs[1];
  if (!['prepare', 'finalize', 'detail'].includes(action)) {
    process.stderr.write('无法生成购物回复：推荐阶段无效\n');
    process.exit(1);
  }
  try {
    const rawPayload = fs.readFileSync(0, 'utf8').trim();
    const modelPayload = rawPayload ? JSON.parse(rawPayload) : {};
    if (action === 'prepare') {
      const searchToken = optionValue(inputArgs, '--search-ref');
      const { state } = loadState(searchToken);
      if (state?.stage !== 'search_results') throw new Error('搜索上下文无效，请重新搜索');
      const preparedResult = prepareRecommendation(state.search, modelPayload);
      const preparedRef = storeState({ stage: 'recommendation_prepared', prepared: preparedResult.prepared, finalPayload: null });
      preparedResult.response.response.prepared_ref = preparedRef;
      preparedResult.response.response.finalize_command = `node "${__filename.replaceAll('\\', '/')}" recommend finalize --prepared-ref "${preparedRef}" --json`;
      preparedResult.response.response.finalize_input = '把 model_task.output_schema 对应的单个 JSON 对象通过标准输入传给 finalize_command。';
      process.stdout.write(`${JSON.stringify(preparedResult.response, null, 2)}\n`);
      process.exit(0);
    }
    const token = optionValue(inputArgs, '--prepared-ref');
    const { file, state } = loadState(token);
    if (state?.stage !== 'recommendation_prepared') throw new Error('推荐上下文无效，请重新搜索');
    const prepared = state.prepared;
    if (action === 'detail') {
      const number = Number(optionValue(inputArgs, '--number'));
      const response = selectionDetailResponse(prepared, number, state.finalPayload || {});
      fs.utimesSync(file, new Date(), new Date());
      process.stdout.write(`${JSON.stringify(response, null, 2)}\n`);
      process.exit(0);
    }
    const response = finalizeRecommendation(prepared, modelPayload);
    response.response.selection_ref = token;
    response.response.selection_command = `node "${__filename.replaceAll('\\', '/')}" recommend detail --prepared-ref "${token}" --number "<候选编号>" --json`;
    saveState(file, { stage: 'recommendation_prepared', prepared, finalPayload: modelPayload });
    process.stdout.write(`${JSON.stringify(response, null, 2)}\n`);
    process.exit(0);
  } catch (error) {
    process.stderr.write(`无法生成购物回复：${error.message}\n`);
    process.exit(1);
  }
}

const renderAgentResponse = inputArgs.includes('--agent-response');
const readsRequestProfile = renderAgentResponse && inputArgs.includes('--request-profile-stdin');
let requestProfile = null;
if (readsRequestProfile) {
  try {
    const rawProfile = fs.readFileSync(0, 'utf8').trim();
    const parsedProfile = rawProfile ? JSON.parse(rawProfile) : {};
    requestProfile = parsedProfile?.request_profile || parsedProfile;
    if (!requestProfile || typeof requestProfile !== 'object' || Array.isArray(requestProfile)) throw new Error('需求画像必须为 JSON 对象');
  } catch (error) {
    process.stderr.write(`无法生成购物回复：需求画像无效（${error.message}）\n`);
    process.exit(1);
  }
}
const cliArgs = inputArgs.filter((arg) => arg !== '--agent-response' && arg !== '--request-profile-stdin');
const productRef = productRefIdentity(cliArgs);
const effectiveCliArgs = lookupArgsForProductRef(cliArgs, productRef);
const captureOutput = renderAgentResponse || Boolean(productRef);
const result = spawnSync(process.execPath, [cli, ...effectiveCliArgs], {
  stdio: captureOutput ? ['inherit', 'pipe', 'pipe'] : 'inherit',
  encoding: captureOutput ? 'utf8' : undefined,
  maxBuffer: 16 * 1024 * 1024,
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

if (productRef) {
  if (result.status !== 0) {
    process.stdout.write(result.stdout || '');
    process.stderr.write(result.stderr || '');
    process.exit(result.status === null ? 1 : result.status);
  }
  try {
    const payload = bindProductRefLookup(JSON.parse(result.stdout), productRef);
    process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
    process.exit(0);
  } catch (error) {
    process.stderr.write(`无法查询商品详情：${error.message}\n`);
    process.exit(1);
  }
}

if (renderAgentResponse) {
  if (result.status !== 0) {
    process.stdout.write(result.stdout || '');
    process.stderr.write(result.stderr || '');
    process.exit(result.status === null ? 1 : result.status);
  }

  try {
    const payload = JSON.parse(result.stdout);
    if (requestProfile) payload.request_profile = requestProfile;
    const command = cliArgs[0];
    if (command !== 'search') {
      throw new Error('--agent-response 目前只用于 search 命令');
    }
    const query = cliArgs[1] || payload?.response?.query || '';
    const assessmentResult = createSearchAssessment(payload, query);
    if (assessmentResult.search) {
      const searchRef = storeState({ stage: 'search_results', search: assessmentResult.search });
      assessmentResult.response.response.search_ref = searchRef;
      assessmentResult.response.response.prepare_command = `node "${__filename.replaceAll('\\', '/')}" recommend prepare --search-ref "${searchRef}" --json`;
      assessmentResult.response.response.prepare_input = '把 model_task.output_schema 对应的单个 JSON 对象通过标准输入传给 prepare_command。';
    }
    process.stdout.write(`${JSON.stringify(assessmentResult.response, null, 2)}\n`);
  } catch (error) {
    process.stderr.write(`无法生成购物回复：${error.message}\n`);
    process.stdout.write(result.stdout || '');
    process.exit(1);
  }
}

process.exit(result.status === null ? 1 : result.status);
