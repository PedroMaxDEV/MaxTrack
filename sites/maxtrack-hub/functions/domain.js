const { createHash, createPrivateKey, randomBytes, sign } = require('node:crypto');

const PRODUCTS = Object.freeze([
  Object.freeze({ id: 'track', name: 'MaxTrack Pro', priceCents: 3990 }),
  Object.freeze({ id: 'gps', name: 'Max GPS', priceCents: 2990 }),
  Object.freeze({ id: 'media', name: 'Max Multimídia', priceCents: 2490 }),
  Object.freeze({ id: 'combo', name: 'Combo Max Hub', priceCents: 6990 }),
]);
const INTRO_COMBO_CENTS = 5990;
const MAX_DEVICES = 3;
const OFFLINE_SECONDS = 72 * 60 * 60;
const CHECKOUT_SECONDS = 30 * 60;

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function getProduct(id) {
  const product = PRODUCTS.find((entry) => entry.id === id);
  if (!product) throw new ApiError(400, 'Selecione um produto válido.');
  return product;
}

function packageProducts(product) {
  return product === 'combo' ? ['track', 'gps', 'media'] : [product];
}

function hash(value) {
  return createHash('sha256').update(value).digest('hex');
}

function makeKey() {
  const parts = randomBytes(20).toString('hex').toUpperCase().match(/.{8}/g);
  return 'MAX-' + parts.join('-');
}

function parseKey(value) {
  if (typeof value !== 'string' || !/^MAX-(?:[0-9A-F]{8}-){4}[0-9A-F]{8}$/i.test(value.trim())) {
    throw new ApiError(400, 'Informe a chave completa do Max Hub.');
  }
  return hash(value.trim().toUpperCase());
}

function deviceHash(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]{16,128}$/.test(value)) {
    throw new ApiError(400, 'Identificador de dispositivo inválido.');
  }
  return hash(value);
}

function unixTime() {
  return Math.floor(Date.now() / 1000);
}

function isActive(license, now = unixTime()) {
  return Boolean(license && !license.revoked && (license.expiresAt === null || license.expiresAt > now));
}

function ensureActive(license, now) {
  if (!isActive(license, now)) throw new ApiError(403, 'Chave inexistente, expirada ou revogada.');
}

function eligibleIntro(account) {
  return (account.paidOrders || 0) === 0 && !account.introUsed;
}

function grant(license, token, now) {
  return {
    token,
    products: packageProducts(license.product),
    expiresAt: Math.min(now + OFFLINE_SECONDS, license.expiresAt ?? Infinity),
    licenseExpiresAt: license.expiresAt,
  };
}

function leaseSigner(origin, privatePem) {
  let key;
  try {
    key = createPrivateKey(privatePem);
    if (key.asymmetricKeyType !== 'rsa' || key.asymmetricKeyDetails.modulusLength < 2048) throw new Error();
  } catch {
    throw new ApiError(503, 'O serviço de assinatura da licença está indisponível.');
  }
  return (lease, deviceId) => {
    const data = ['maxhub-lease-v1', origin, deviceId, lease.token, [...lease.products].sort().join(','), lease.expiresAt];
    return { ...lease, proof: sign('sha256', Buffer.from(data.join('\n'), 'utf-8'), key).toString('base64') };
  };
}

module.exports = {
  ApiError, PRODUCTS, INTRO_COMBO_CENTS, MAX_DEVICES, CHECKOUT_SECONDS, getProduct, packageProducts,
  hash, makeKey, parseKey, deviceHash, unixTime, isActive, ensureActive, eligibleIntro, grant, leaseSigner,
};
