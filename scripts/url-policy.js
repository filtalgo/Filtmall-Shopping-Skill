'use strict';

const net = require('node:net');

function publicHTTPS(value) {
  try {
    const url = new URL(String(value || '').trim());
    if (url.protocol !== 'https:' || url.username || url.password || url.hash || (url.port && url.port !== '443')) return '';
    if (unsafeHost(url.hostname)) return '';
    return String(value).trim();
  } catch {
    return '';
  }
}

function filtalgoProductDetail(value, spuId, skuId) {
  const normalized = publicHTTPS(value);
  if (!normalized) return '';
  const url = new URL(normalized);
  if (!filtalgoHost(url.hostname) || url.pathname !== '/pages/goods/product/detail') return '';
  return url.searchParams.get('goodsId') === String(spuId) && url.searchParams.get('skuId') === String(skuId)
    ? normalized
    : '';
}

function filtalgoHost(value) {
  const host = normalizeHost(value);
  return new Set(['m.filtalgo.com', 'dev-m.filtalgo.com', 'pre-m.filtalgo.com']).has(host);
}

function unsafeHost(value) {
  const host = normalizeHost(value);
  if (!host || host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local') || host.endsWith('.internal')) return true;
  const family = net.isIP(host);
  if (!family) return false;
  if (family === 4) {
    const parts = host.split('.').map(Number);
    return parts[0] === 0 || parts[0] === 10 || parts[0] === 127
      || (parts[0] === 169 && parts[1] === 254)
      || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31)
      || (parts[0] === 192 && parts[1] === 168)
      || parts[0] >= 224;
  }
  return host === '::' || host === '::1' || host.startsWith('fe80:') || host.startsWith('fc') || host.startsWith('fd');
}

function normalizeHost(value) {
  return String(value || '').replace(/^\[|\]$/g, '').toLowerCase();
}

module.exports = { publicHTTPS, filtalgoProductDetail, filtalgoHost, unsafeHost };
