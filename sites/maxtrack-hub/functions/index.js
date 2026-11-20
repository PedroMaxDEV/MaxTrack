const { join } = require('node:path');
const { readFile } = require('node:fs/promises');
const { initializeApp } = require('firebase-admin/app');
const { getAuth } = require('firebase-admin/auth');
const { getFirestore } = require('firebase-admin/firestore');
const { onRequest } = require('firebase-functions/v2/https');
const { defineBoolean, defineSecret, defineString } = require('firebase-functions/params');
const { ApiError, PRODUCTS, INTRO_COMBO_CENTS, getProduct, leaseSigner } = require('./domain');
const { verifiedPaymentId, mpRequest, checkoutOrigin, createPreference } = require('./mercado-pago');
const { Store } = require('./store');

initializeApp();
const liveStore = new Store(getFirestore());
const testStore = new Store(getFirestore(), true);
const storeOrigin = defineString('STORE_ORIGIN');
const mercadoPagoSandbox = defineBoolean('MP_SANDBOX', { default: false });
const accessToken = defineSecret('MP_ACCESS_TOKEN');
const webhookSecret = defineSecret('MP_WEBHOOK_SECRET');
const licenseSigningKey = defineSecret('LICENSE_SIGNING_KEY');

function licenseProof() {
  return leaseSigner(checkoutOrigin(storeOrigin.value()), licenseSigningKey.value());
}

async function authenticated(req, admin = false) {
  const match = /^Bearer ([A-Za-z0-9_.-]+)$/.exec(req.get('authorization') || '');
  if (!match || match[1].length > 8000) throw new ApiError(401, 'Entre com sua conta Google.');
  let decoded;
  try {
    decoded = await getAuth().verifyIdToken(match[1], true);
  } catch {
    throw new ApiError(401, 'Sua sessão expirou. Entre com o Google de novo.');
  }
  if (decoded.firebase?.sign_in_provider !== 'google.com' || !decoded.email_verified || !decoded.email) {
    throw new ApiError(403, 'Entre com uma conta Google verificada.');
  }
  if (admin && decoded.maxAdmin !== true) throw new ApiError(403, 'Acesso reservado à administração.');
  return decoded;
}

async function checkout(req, body, store, sandbox) {
  const user = await authenticated(req);
  const product = getProduct(body.product);
  const origin = checkoutOrigin(storeOrigin.value());
  const order = await store.reserveCheckout(user, product);
  if (order.url) return { url: order.url };
  try {
    const details = await createPreference(order, product, origin, accessToken.value(), sandbox);
    return { url: await store.finishCheckout(order, details) };
  } catch (error) {
    await store.releaseCheckout(order);
    throw error;
  }
}

async function webhook(req, store, sandbox) {
  if ((req.query.type || req.body?.type) !== 'payment') return { received: true };
  const id = verifiedPaymentId(req, webhookSecret.value());
  const payment = await mpRequest(`/v1/payments/${id}`, accessToken.value());
  if (!payment) throw new ApiError(502, 'O pagamento ainda não está disponível para consulta.');
  await store.recordPayment(payment, id, sandbox);
  return { received: true };
}

async function download(req, res, store) {
  const user = await authenticated(req);
  if (!(await store.hasProduct(user.uid, 'gps'))) {
    throw new ApiError(403, 'O APK está disponível para licenças ativas de Max GPS ou do Combo.');
  }
  let apk;
  try {
    apk = await readFile(join(__dirname, 'private', 'MaxGPS-Android.apk'));
  } catch (error) {
    if (error.code === 'ENOENT') throw new ApiError(404, 'APK ainda não publicado. Tente novamente mais tarde.');
    throw error;
  }
  res.set('Content-Disposition', 'attachment; filename="MaxGPS-Android.apk"');
  res.type('application/vnd.android.package-archive').send(apk);
}

exports.api = onRequest({
  region: 'us-central1',
  memory: '512MiB',
  maxInstances: 10,
  timeoutSeconds: 45,
  secrets: [accessToken, webhookSecret, licenseSigningKey],
}, async (req, res) => {
  res.set('Cache-Control', 'private, no-store');
  res.set('X-Content-Type-Options', 'nosniff');
  const path = req.path.replace(/^\/api(?=\/|$)/, '').replace(/\/$/, '');
  const method = `${req.method} ${path}`;
  const body = req.body ?? {};
  try {
    const sandbox = mercadoPagoSandbox.value();
    const store = sandbox ? testStore : liveStore;
    if (req.method === 'POST' && method !== 'POST /webhook' &&
        (!req.is('application/json') || typeof body !== 'object' || Array.isArray(body) || req.rawBody?.length > 8192)) {
      throw new ApiError(400, 'Envie os dados no formato JSON.');
    }
    let result;
    switch (method) {
      case 'GET /catalog':
        result = { products: PRODUCTS, introComboCents: INTRO_COMBO_CENTS, buyers: await store.buyers() };
        break;
      case 'GET /account':
        result = await store.account(await authenticated(req));
        break;
      case 'POST /account/claim':
        await store.claimKey(await authenticated(req), body.key);
        result = { ok: true };
        break;
      case 'POST /checkout':
        result = await checkout(req, body, store, sandbox);
        break;
      case 'POST /webhook':
        result = await webhook(req, store, sandbox);
        break;
      case 'GET /download/apk':
        await download(req, res, store);
        return;
      case 'GET /admin/orders':
        await authenticated(req, true);
        result = await store.purchases(req.query.cursor);
        break;
      case 'GET /admin/licenses':
        await authenticated(req, true);
        result = await store.testKeys();
        break;
      case 'POST /admin/licenses':
        result = await store.createTestKey(await authenticated(req, true), body.product, body.days, body.label);
        break;
      case 'POST /admin/revoke':
        await authenticated(req, true);
        await store.revokeKey(body.id);
        result = { ok: true };
        break;
      case 'POST /activate': {
        const attachProof = licenseProof();
        result = attachProof(await store.activate(body.key, body.deviceId), body.deviceId);
        break;
      }
      case 'POST /license/refresh': {
        const attachProof = licenseProof();
        result = attachProof(await store.refresh(body.token, body.deviceId), body.deviceId);
        break;
      }
      default:
        throw new ApiError(404, 'Recurso não encontrado.');
    }
    res.json(result);
  } catch (error) {
    if (error instanceof ApiError) res.status(error.status).json({ error: error.message });
    else {
      console.error('Max Hub API', path, error.code || error.name);
      res.status(500).json({ error: 'Serviço temporariamente indisponível.' });
    }
  }
});
