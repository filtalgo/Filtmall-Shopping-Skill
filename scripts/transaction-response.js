'use strict';

const { publicHTTPS } = require('./url-policy');

const LINK_TAIL_NOTE = '页面信息以打开后的实时展示为准。';
const PENDING_PAYMENT_STATUSES = new Set([
  'UNPAID',
  'WAIT_PAY',
  'PENDING_PAY',
  'PENDING_PAYMENT',
  'PAYMENT_PENDING',
]);

function cleanText(value, fallback = '') {
  const text = String(value ?? '').replace(/[\r\n|]+/g, ' ').trim();
  return text || fallback;
}

function maskIdentifier(value) {
  const text = cleanText(value);
  if (!text) return '工具未返回';
  if (text.length <= 8) return `${text.slice(0, 2)}…${text.slice(-2)}`;
  return `${text.slice(0, 4)}…${text.slice(-4)}`;
}

function firstSafeLink(...values) {
  for (const value of values) {
    const link = publicHTTPS(value);
    if (link) return link;
  }
  return '';
}

function selectedTargetUrl(targets, name) {
  const target = targets?.[name];
  return firstSafeLink(
    target?.channels?.mobile_h5?.url,
    target?.channels?.pc_web?.url,
    target?.url,
  );
}

function paymentLink(payload) {
  return firstSafeLink(
    payload?.selected_buyer_links?.payment,
    payload?.payment_url,
    payload?.buyer_links?.payment,
    selectedTargetUrl(payload?.buyer_link_targets, 'payment'),
  );
}

function orderListLink(payload) {
  return firstSafeLink(
    payload?.selected_buyer_links?.order_list,
    payload?.buyer_links?.order_list,
    selectedTargetUrl(payload?.buyer_link_targets, 'order_list'),
    payload?.result?.selected_buyer_links?.order_list,
    payload?.result?.buyer_links?.order_list,
    selectedTargetUrl(payload?.result?.buyer_link_targets, 'order_list'),
  );
}

function orderPaymentLink(order) {
  return firstSafeLink(
    order?.selected_buyer_links?.payment,
    order?.payment_url,
    order?.buyer_links?.payment,
    selectedTargetUrl(order?.buyer_link_targets, 'payment'),
  );
}

function isPendingPayment(order) {
  const raw = cleanText(order?.orderStatus ?? order?.order_status ?? order?.status).toUpperCase();
  return raw.includes('待支付') || PENDING_PAYMENT_STATUSES.has(raw);
}

function formatAmount(value) {
  if (value === null || value === undefined || value === '') return '暂未提供';
  const text = cleanText(value);
  return /^[¥￥]/u.test(text) ? text : `¥${text}`;
}

function itemSummary(order) {
  const items = Array.isArray(order?.orderItems) && order.orderItems.length
    ? order.orderItems
    : (Array.isArray(order?.items) ? order.items : []);
  if (!items.length) return '暂未提供商品信息';
  const summaries = items.slice(0, 2).map((item) => {
    const name = cleanText(item?.name ?? item?.goodsName ?? item?.title, '商品');
    const sku = cleanText(item?.skuName ?? item?.specification);
    const quantity = Number(item?.num ?? item?.quantity);
    return `${name}${sku ? `（${sku}）` : ''}${Number.isFinite(quantity) && quantity > 0 ? ` ×${quantity}` : ''}`;
  });
  if (items.length > summaries.length) summaries.push(`等 ${items.length} 件商品`);
  return summaries.join('；');
}

function readyResponse(markdown) {
  return {
    status: 'ready',
    instruction: '将 markdown 字段从第一个 # 开始逐字作为唯一最终回复，不得省略、改写或重新生成链接。',
    markdown: `${markdown.trimEnd()}\n`,
  };
}

function renderPreparePaymentResponse(payload) {
  const link = paymentLink(payload);
  if (!link) return null;
  const orderSn = payload?.order_sn ?? payload?.orderSn ?? payload?.result?.order_sn ?? payload?.result?.orderSn;
  const amount = payload?.amount ?? payload?.pay_amount ?? payload?.flowPrice ?? payload?.result?.amount ?? payload?.result?.flowPrice;
  const lines = [
    '## 订单已准备好',
    '',
    `- 订单号：${maskIdentifier(orderSn)}`,
  ];
  if (amount !== null && amount !== undefined && amount !== '') lines.push(`- 应付金额：${formatAmount(amount)}`);
  lines.push(
    '- 支付方式：平台收银台',
    '',
    `[去支付](${link})`,
    '',
    LINK_TAIL_NOTE,
  );
  return readyResponse(lines.join('\n'));
}

function renderOrderListResponse(payload) {
  const orders = Array.isArray(payload?.result?.orders)
    ? payload.result.orders
    : (Array.isArray(payload?.orders) ? payload.orders : []);
  const listLink = orderListLink(payload);
  const lines = ['## 最近订单', ''];
  if (!orders.length) {
    lines.push('当前账号暂无可查询订单。');
  } else {
    lines.push(
      '| 序号 | 订单号 | 下单时间 | 状态 | 金额 | 商品 | 可操作状态 |',
      '| ---: | --- | --- | --- | ---: | --- | --- |',
    );
    orders.forEach((order, index) => {
      const pending = isPendingPayment(order);
      const directPayment = orderPaymentLink(order);
      const action = pending
        ? (directPayment ? '可支付' : (listLink ? '可前往订单页支付' : '暂未返回支付入口'))
        : '可查看详情';
      lines.push(`| ${index + 1} | ${maskIdentifier(order?.sn ?? order?.orderSn)} | ${cleanText(order?.createTime ?? order?.create_time, '暂未提供')} | ${cleanText(order?.orderStatus ?? order?.order_status ?? order?.status, '暂未提供')} | ${formatAmount(order?.flowPrice ?? order?.amount)} | ${itemSummary(order)} | ${action} |`);
    });
  }

  const pendingOrders = orders.filter(isPendingPayment);
  const directPayments = pendingOrders
    .map(order => ({ order, link: orderPaymentLink(order) }))
    .filter(item => item.link)
    .slice(0, 2);
  if (directPayments.length) {
    lines.push('', '### 待支付订单');
    directPayments.forEach(({ order, link }) => {
      lines.push(`- 订单 ${maskIdentifier(order?.sn ?? order?.orderSn)}：[去支付](${link})`);
    });
  } else if (pendingOrders.length && listLink) {
    lines.push('', `待支付订单可以从这里继续处理：[去支付（打开我的订单）](${listLink})`);
  } else if (listLink) {
    lines.push('', `需要查看完整订单或自己操作，可以打开：[我的订单](${listLink})`);
  }
  if (directPayments.length || listLink) lines.push('', LINK_TAIL_NOTE);
  return readyResponse(lines.join('\n'));
}

function attachAgentResponse(payload, response) {
  if (!response) return payload;
  return { ...payload, response };
}

module.exports = {
  LINK_TAIL_NOTE,
  isPendingPayment,
  renderPreparePaymentResponse,
  renderOrderListResponse,
  attachAgentResponse,
};
