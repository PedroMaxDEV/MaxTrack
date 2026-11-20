const { createHmac, timingSafeEqual } = require('node:crypto');
const { ApiError } = require('./domain');

function verifiedPaymentId(req, secret) {
  const dataId = req.query['data.id'];
  const requestId = req.get('x-request-id');
  const signature = req.get('x-signature');
  if (typeof dataId !== 'string' || !/^[0-9]{1,24}$/.test(dataId) ||
      !requestId || !/^[A-Za-z0-9_-]{1,128}$/.test(requestId) || !signature || !secret) {
    throw new ApiError(401, 'Assinatura da notificação inválida.');
  }
  const fields = new Map();
  for (const part of signature.split(',')) {
    const [key, value] = part.trim().split('=');
    if (fields.has(key)) throw new ApiError(401, 'Assinatura da notificação inválida.');
    fields.set(key, value);
  }
  const ts = fields.get('ts') || '';
  const rawSig = fields.get('v1') || '';
  if (!/^\d{1,16}$/.test(ts) || !/^[a-f\d]{64}$/i.test(rawSig)) {
    throw new ApiError(401, 'Assinatura da notificação inválida.');
  }
  const signed = `id:${dataId};request-id:${requestId};ts:${ts};`;
  const expected = createHmac('sha256', secret).update(signed).digest();
  if (!timingSafeEqual(expected, Buffer.from(rawSig, 'hex'))) {
    throw new ApiError(401, 'Assinatura da notificação inválida.');
  }
  return dataId;
}

async function mpRequest(path, token, options = {}) {
  const { method = 'GET', body, orderId } = options;
  const headers = { Authorization: `Bearer ${token}`, Accept: 'application/json' };
  if (body) headers['Content-Type'] = 'application/json';
  if (orderId) headers['X-Idempotency-Key'] = orderId;
  try {
    const response = await fetch(`https://api.mercadopago.com${path}`, {
      method, headers, body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(12_000),
    });
    if (response.status === 404 && method === 'GET') return null;
    if (!response.ok) {
      console.error('Mercado Pago API', method, response.status);
      throw new Error('provider response');
    }
    return await response.json();
  } catch {
    throw new ApiError(502, 'O Mercado Pago está indisponível. Tente novamente em instantes.');
  }
}

function checkoutOrigin(value) {
  let url;
  try { url = new URL(value); } catch { throw new ApiError(503, 'Configure o endereço da loja.'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new ApiError(503, 'Configure o endereço HTTPS da loja.');
  }
  return url.origin;
}

async function createPreference(order, product, origin, token, sandbox) {
  const backUrl = (status) => `${origin}/?pedido=${encodeURIComponent(order.id)}&pagamento=${status}#conta`;
  const result = await mpRequest('/checkout/preferences', token, {
    method: 'POST',
    orderId: order.id,
    body: {
      items: [{ id: product.id, title: product.name, currency_id: 'BRL', quantity: 1, unit_price: order.priceCents / 100 }],
      external_reference: order.id,
      metadata: { max_order_id: order.id, max_product: product.id },
      notification_url: `${origin}/api/webhook?source_news=webhooks`,
      back_urls: { success: backUrl('sucesso'), pending: backUrl('pendente'), failure: backUrl('falha') },
      auto_return: 'approved',
      expires: true,
      expiration_date_to: new Date(order.checkoutUntil * 1000).toISOString(),
    },
  });
  const checkoutUrl = sandbox ? result.sandbox_init_point : result.init_point;
  if (typeof checkoutUrl !== 'string' || !/^https:\/\/(?:www\.|sandbox\.)?mercadopago\.com(?:\.br)?\//i.test(checkoutUrl)) {
    throw new ApiError(502, 'O Mercado Pago retornou um link de pagamento inválido.');
  }
  return { url: checkoutUrl, preferenceId: String(result.id) };
}

function paymentMatches(payment, order, id, sandbox) {
  const amount = payment.transaction_amount;
  return String(payment.id) === id &&
    payment.external_reference === order.id &&
    payment.metadata?.max_order_id === order.id &&
    payment.metadata?.max_product === order.product &&
    payment.live_mode === !sandbox &&
    payment.currency_id === 'BRL' &&
    typeof amount === 'number' && Math.abs(amount * 100 - order.priceCents) < 0.001;
}

function paymentState(payment) {
  if (['charged_back', 'refunded'].includes(payment.status) || payment.transaction_amount_refunded > 0) return 'refunded';
  if (payment.status === 'approved') return 'approved';
  if (['pending', 'in_process', 'authorized', 'in_mediation'].includes(payment.status)) return 'pending';
  return 'rejected';
}

module.exports = { verifiedPaymentId, mpRequest, checkoutOrigin, createPreference, paymentMatches, paymentState };
