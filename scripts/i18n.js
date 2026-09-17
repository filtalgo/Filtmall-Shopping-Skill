'use strict';

const MESSAGES = {
  'zh-CN': {
    understood: '我理解你的需求', focus: '你的需求重点', candidates: '候选商品', nearest: '最接近的备选',
    price: '当前价格', spec: '推荐规格', currentSpec: '当前规格', productLink: '商品链接', openDetail: '打开商品详情',
    brandOverview: '品牌概览', productOverview: '商品概览', fit: '综合适配度', dimensions: '关键维度表现', reason: '推荐理由',
    priceAdvantage: '价格优势', filtmallPrice: '筛电当前到手价', comparison: '同款同规格', saving: '在筛电买便宜约', less: '少花约', comparedAt: '比价时间', source: '打开来源链接',
    priceDisclaimer: '价格可能因账号、地区、会员身份和优惠活动等发生变化。',
    linkTailNote: '页面信息以打开后的实时展示为准。',
    candidateIntro: n => `根据以上需求，我筛出了 ${n} 款更值得考虑的商品，并按综合适配度从高到低排列。`,
    nearestIntro: n => `当前没有完全满足全部条件的商品。以下 ${n} 款仅作为预算和品类范围内的近似备选，并按综合适配度排列。`,
    shortfall: (wanted, actual) => `你希望查看 ${wanted} 款；当前只有 ${actual} 款具备足够证据，因此只展示这些候选。`,
    primaryHeading: '如果只买一款', choose: name => `我会选 **${name}**。`, noPrimaryHeading: '当前没有合适的首选',
    nearestNoPrimary: '这些商品都没有被验证为完全满足全部条件，因此不直接给出首选。你可以选择放宽一个最不重要的条件后再试。',
    alternatives: '其他情况可以这样选', alternative: (condition, name, reason) => `- 如果${condition}，可以改选 **${name}**，因为${reason}  `,
    noResults: '当前没有找到同时满足这些条件、且商品事实足够完整的候选。', noResultAction: '当前结果不足以支持可靠首选。你可以放宽一个条件后再试。',
    selectedSpec: '当前选中规格', stock: '库存状态', inStock: '有货', outOfStock: '暂时无货', liveNote: '实时情况以商品页为准', otherSpecs: '其他可选规格',
    detailHeading: n => `第 ${n} 款商品详情`, further: '进一步推荐说明', parameters: '商品参数',
    finalInstruction: '将 markdown 字段原样作为唯一最终回复，不添加前缀或后缀。', detailInstruction: '将 markdown 字段原样作为唯一最终回复，不要缩写或改写链接。',
    fields: ['品类', '适用类别', '核心需求', '肤感偏好', '选择优先级', '预算', '使用频率'], currentNeed: '当前需求',
  },
  'en-US': {
    understood: 'What I understood', focus: 'Your priorities', candidates: 'Candidate products', nearest: 'Closest alternatives',
    price: 'Current price', spec: 'Recommended option', currentSpec: 'Current option', productLink: 'Product link', openDetail: 'Open product details',
    brandOverview: 'Brand overview', productOverview: 'Product overview', fit: 'Overall fit', dimensions: 'Key dimensions', reason: 'Why it fits',
    priceAdvantage: 'Price comparison', filtmallPrice: 'Filtmall current price', comparison: 'same product and option', saving: 'Approximate saving on Filtmall', less: 'about', comparedAt: 'Compared at', source: 'Open source',
    priceDisclaimer: 'Prices may vary by account, region, membership and promotion.',
    linkTailNote: 'Information on the opened page reflects the latest available details.',
    candidateIntro: n => `I found ${n} product${n === 1 ? '' : 's'} worth considering, ordered by overall fit.`,
    nearestIntro: n => `No product fully matched every condition. These ${n} option${n === 1 ? ' is' : 's are'} the closest alternatives within the category and hard budget.`,
    shortfall: (wanted, actual) => `You requested ${wanted}; only ${actual} candidate${actual === 1 ? '' : 's'} had enough evidence to show.`,
    primaryHeading: 'If choosing one', choose: name => `I would choose **${name}**.`, noPrimaryHeading: 'No reliable first choice',
    nearestNoPrimary: 'None of these products was verified to meet every condition, so I am not naming a first choice. You can relax one lower-priority condition and try again.',
    alternatives: 'Other ways to choose', alternative: (condition, name, reason) => `- If ${condition}, consider **${name}**, because ${reason}  `,
    noResults: 'No candidate both matched the conditions and had enough verifiable product facts.', noResultAction: 'There is not enough evidence for a reliable first choice. You can relax one condition and try again.',
    selectedSpec: 'Selected option', stock: 'Availability', inStock: 'In stock', outOfStock: 'Out of stock', liveNote: 'check the product page for current availability', otherSpecs: 'Other options',
    detailHeading: n => `Product ${n} details`, further: 'Additional recommendation notes', parameters: 'Product facts',
    finalInstruction: 'Return markdown as the only user-visible response without a prefix or suffix.', detailInstruction: 'Return markdown as the only user-visible response without shortening or rewriting links.',
    fields: ['Category', 'Suitable for', 'Core needs', 'Texture preference', 'Selection priority', 'Budget', 'Usage frequency'], currentNeed: 'Current request',
  },
};

function locale(value) { return value === 'en-US' ? 'en-US' : 'zh-CN'; }
function messages(value) { return MESSAGES[locale(value)]; }

module.exports = { locale, messages };
