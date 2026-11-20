const test = require('node:test');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const { createHmac, generateKeyPairSync, randomUUID, verify } = require('node:crypto');

test('Google account, checkout webhook, test keys, revocation and APK entitlement', {
  skip: !process.env.FIRESTORE_EMULATOR_HOST || !process.env.FIREBASE_AUTH_EMULATOR_HOST,
  timeout: 45_000,
}, async (t) => {
  const origin = 'https://maxhub.example';
  const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
  process.env.STORE_ORIGIN = origin;
  process.env.MP_SANDBOX = 'true';
  process.env.MP_ACCESS_TOKEN = 'sandbox-fixture';
  process.env.MP_WEBHOOK_SECRET = 'webhook-fixture';
  process.env.LICENSE_SIGNING_KEY = privateKey.export({ type: 'pkcs8', format: 'pem' });
  const { api } = require('./index');
  const { getAuth } = require('firebase-admin/auth');
  const express = require(require.resolve('express', { paths: [require.resolve('firebase-functions')] }));
  const app = express();
  app.use(express.json());
  app.use(api);
  const server = app.listen(0, '127.0.0.1');
  t.after(() => server.close());
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}/api`;
  const salt = randomUUID();
  const email = `${salt}@example.com`;

  async function googleLogin() {
    const emulator = `http://${process.env.FIREBASE_AUTH_EMULATOR_HOST}/identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key=fake-key`;
    const idToken = JSON.stringify({ sub: salt, email, email_verified: true });
    const response = await fetch(emulator, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        postBody: new URLSearchParams({ providerId: 'google.com', id_token: idToken }).toString(),
        requestUri: 'http://localhost', returnIdpCredential: true, returnSecureToken: true,
      }),
    });
    const result = await response.json();
    assert.equal(response.status, 200, JSON.stringify(result.error));
    return result;
  }

  async function call(path, { token, status = 200, body, headers = {} } = {}) {
    const request = await fetch(base + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const response = request.headers.get('content-type')?.includes('application/json') ? await request.json() : await request.text();
    assert.equal(request.status, status, JSON.stringify(response));
    return response;
  }

  const session = await googleLogin();
  const token = session.idToken;
  assert.equal((await call('/account', { token })).eligibleIntro, true);
  await call('/admin/orders', { token, status: 403 });
  await call('/download/apk', { token, status: 403 });
  await getAuth().setCustomUserClaims(session.localId, { maxAdmin: true });
  const adminToken = (await googleLogin()).idToken;
  assert.equal((await call('/account', { token: adminToken })).admin, true);

  const created = await call('/admin/licenses', { token: adminToken, body: { product: 'combo', days: 7, label: 'Teste' } });
  await call('/account/claim', { token, body: { key: created.key } });
  const body = { key: created.key, deviceId: 'desktop-lab-fixture-01' };
  const grant = await call('/activate', { body });
  assert.deepEqual(grant.products, ['track', 'gps', 'media']);
  const signed = `maxhub-lease-v1\n${origin}\n${body.deviceId}\n${grant.token}\ngps,media,track\n${grant.expiresAt}`;
  assert.equal(verify('sha256', Buffer.from(signed), publicKey, Buffer.from(grant.proof, 'base64')), true);
  const refresh = { token: grant.token, deviceId: body.deviceId };
  assert.equal((await call('/license/refresh', { body: refresh })).token, grant.token);
  await call('/license/refresh', { status: 403, body: { ...refresh, deviceId: 'desktop-lab-fixture-02' } });
  await call('/admin/revoke', { token: adminToken, body: { id: created.id } });
  await call('/license/refresh', { status: 403, body: refresh });

  let preference;
  let currentPayment;
  const realFetch = global.fetch;
  global.fetch = (url, options) => {
    if (url === 'https://api.mercadopago.com/checkout/preferences') {
      preference = JSON.parse(options.body);
      return Promise.resolve(Response.json({ id: 'sandbox-pref-id', sandbox_init_point: 'https://sandbox.mercadopago.com/checkout/' }));
    }
    if (url === 'https://api.mercadopago.com/v1/payments/5500123') {
      return Promise.resolve(Response.json(currentPayment));
    }
    return realFetch(url, options);
  };
  t.after(() => { global.fetch = realFetch; });
  const buyersBefore = (await call('/catalog')).buyers;
  const checkout = await call('/checkout', { token, body: { product: 'combo' } });
  assert.equal(checkout.url, 'https://sandbox.mercadopago.com/checkout/');
  assert.equal(preference.items[0].unit_price, 59.90);
  assert.equal((await call('/checkout', { token, body: { product: 'combo' } })).url, checkout.url);
  currentPayment = {
    id: 5500123, external_reference: preference.external_reference, metadata: preference.metadata,
    live_mode: false, status: 'approved', transaction_amount: 59.90, currency_id: 'BRL',
    date_last_updated: '2026-01-01T00:00:00Z',
  };
  const requestId = randomUUID();
  const ts = String(Date.now());
  const signature = createHmac('sha256', process.env.MP_WEBHOOK_SECRET)
    .update(`id:${currentPayment.id};request-id:${requestId};ts:${ts};`).digest('hex');
  const path = `/webhook?type=payment&data.id=${currentPayment.id}`;
  const callback = { headers: { 'x-request-id': requestId, 'x-signature': `ts=${ts},v1=${signature}` }, body: {} };
  await call(path, { status: 401, body: {} });
  currentPayment.transaction_amount = 59.89;
  await call(path, callback);
  assert.equal((await call('/account', { token })).licenses.filter((item) => item.source === 'purchase').length, 0);
  currentPayment.transaction_amount = 59.90;
  await call(path, callback);
  await call(path, callback);
  let account = await call('/account', { token });
  assert.equal(account.licenses.filter((item) => item.source === 'purchase').length, 1);
  assert.equal(account.orders[0].status, 'approved');
  assert.equal(account.eligibleIntro, false);
  assert.equal((await call('/catalog')).buyers, buyersBefore + 1);
  assert.equal((await call('/admin/orders', { token: adminToken })).orders.some((order) => order.email === email), true);
  const download = await realFetch(base + '/download/apk', { headers: { Authorization: `Bearer ${token}` } });
  assert.ok([200, 404].includes(download.status), 'A licença concede acesso ao endpoint do APK');
  if (download.ok) {
    assert.match(download.headers.get('Content-Disposition'), /MaxGPS-Android\.apk/);
    assert.equal(Buffer.from(await download.arrayBuffer()).subarray(0, 2).toString(), 'PK');
  }
  process.env.MP_SANDBOX = 'false';
  assert.equal((await call('/account', { token })).orders.length, 0, 'Sandbox orders are separate from live sales');
  await call('/download/apk', { token, status: 403 });
  process.env.MP_SANDBOX = 'true';

  currentPayment = { ...currentPayment, status: 'refunded', date_last_updated: '2026-01-01T00:01:00Z' };
  await call(path, callback);
  account = await call('/account', { token });
  assert.equal(account.orders[0].status, 'refunded');
  assert.equal(account.licenses.find((item) => item.source === 'purchase').revoked, true);
  assert.equal((await call('/catalog')).buyers, buyersBefore);
  await call('/download/apk', { token, status: 403 });
});
