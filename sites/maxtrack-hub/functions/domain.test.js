const test = require('node:test');
const assert = require('node:assert/strict');
const { createHmac, generateKeyPairSync, verify } = require('node:crypto');
const { eligibleIntro, makeKey, parseKey, isActive, grant, leaseSigner } = require('./domain');
const { verifiedPaymentId, paymentMatches, paymentState, checkoutOrigin } = require('./mercado-pago');

test('keys are high entropy, case-insensitive, and avoid plaintext IDs', () => {
  const key = makeKey();
  assert.match(key, /^MAX-(?:[0-9A-F]{8}-){4}[0-9A-F]{8}$/);
  assert.equal(parseKey(key), parseKey(`  ${key.toLowerCase()}  `));
  assert.notEqual(parseKey(key), parseKey(makeKey()));
  assert.throws(() => parseKey('../bad/path'), { status: 400 });
});

test('activation deadlines, expiry and first-purchase eligibility', () => {
  const lifetime = { product: 'combo', revoked: false, expiresAt: null };
  const testKey = { product: 'gps', revoked: false, expiresAt: 500 };
  assert.deepEqual(grant(lifetime, 'token', 100), {
    token: 'token', products: ['track', 'gps', 'media'], expiresAt: 100 + 72 * 3600, licenseExpiresAt: null,
  });
  assert.equal(grant(testKey, 'token', 100).expiresAt, 500);
  assert.equal(isActive(testKey, 500), false);
  assert.equal(isActive({ ...lifetime, revoked: true }, 100), false);
  assert.equal(eligibleIntro({ activeOrders: 0, paidOrders: 1 }), false);
  assert.equal(eligibleIntro({ activeOrders: 0, paidOrders: 0 }), true);
});

test('webhook binds the receipt and request ID to their signature', () => {
  const secret = 'test-secret';
  const ts = '1742505638683';
  const id = '12345';
  const requestId = 'bb56a2f1-6aae-46ac-982e-9dcd3581d08e';
  const digest = createHmac('sha256', secret).update(`id:${id};request-id:${requestId};ts:${ts};`).digest('hex');
  const headers = { 'x-request-id': requestId, 'x-signature': `ts=${ts},v1=${digest}` };
  const req = { query: { 'data.id': id }, get: (name) => headers[name] };
  assert.equal(verifiedPaymentId(req, secret), id);
  assert.throws(() => verifiedPaymentId({ ...req, query: { 'data.id': '12344' } }, secret), { status: 401 });
  assert.throws(() => verifiedPaymentId(req, 'wrong-secret'), { status: 401 });
  headers['x-request-id'] = 'different';
  assert.throws(() => verifiedPaymentId(req, secret), { status: 401 });
});

test('payment confirmation checks receipt, mode, order, currency, and exact price', () => {
  const order = { id: 'order-id', product: 'combo', priceCents: 5990 };
  const payment = {
    id: 12345, external_reference: order.id, metadata: { max_order_id: order.id, max_product: order.product },
    live_mode: true, currency_id: 'BRL', transaction_amount: 59.90, status: 'approved',
  };
  assert.equal(paymentMatches(payment, order, '12345', false), true);
  assert.equal(paymentMatches(payment, order, '12345', true), false);
  assert.equal(paymentMatches({ ...payment, transaction_amount: 59.89 }, order, '12345', false), false);
  assert.equal(paymentMatches({ ...payment, currency_id: 'USD' }, order, '12345', false), false);
  assert.equal(paymentMatches({ ...payment, metadata: { ...payment.metadata, max_product: 'track' } }, order, '12345', false), false);
  assert.equal(paymentState(payment), 'approved');
  assert.equal(paymentState({ ...payment, transaction_amount_refunded: 1 }), 'refunded');
  assert.equal(paymentState({ ...payment, status: 'charged_back' }), 'refunded');
  assert.equal(paymentState({ ...payment, status: 'pending' }), 'pending');
});

test('checkout callback uses a configured HTTPS origin only', () => {
  assert.equal(checkoutOrigin('https://loja.web.app/'), 'https://loja.web.app');
  assert.throws(() => checkoutOrigin('http://localhost:5000'), { status: 503 });
  assert.throws(() => checkoutOrigin('https://loja.web.app/rota'), { status: 503 });
});

test('signed offline grant binds origin, device, token, product set and expiration', () => {
  const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
  const origin = 'https://loja.web.app';
  const device = 'my-desktop-device';
  const lease = { token: 'opaqueToken', products: ['track', 'gps', 'media'], expiresAt: 1000 };
  const attachProof = leaseSigner(origin, privateKey.export({ type: 'pkcs8', format: 'pem' }));
  const result = attachProof(lease, device);
  const signed = Buffer.from(`maxhub-lease-v1\n${origin}\n${device}\nopaqueToken\ngps,media,track\n1000`);
  const proof = Buffer.from(result.proof, 'base64');
  assert.equal(verify('sha256', signed, publicKey, proof), true);
  assert.equal(verify('sha256', Buffer.from(signed + '1'), publicKey, proof), false);
  assert.throws(() => leaseSigner(origin, 'bad PEM'), { status: 503 });
});
