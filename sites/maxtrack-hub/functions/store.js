const { randomBytes, randomUUID } = require('node:crypto');
const { FieldValue } = require('firebase-admin/firestore');
const {
  ApiError, INTRO_COMBO_CENTS, MAX_DEVICES, CHECKOUT_SECONDS, getProduct, packageProducts,
  hash, makeKey, parseKey, deviceHash, unixTime, isActive, ensureActive, eligibleIntro, grant,
} = require('./domain');
const { paymentMatches, paymentState } = require('./mercado-pago');

const CHECKOUT_LEASE = 25;
const ORDER_ID = /^[0-9a-f-]{36}$/;
const HASH_ID = /^[a-f0-9]{64}$/;

function displayOrder(doc, admin = false) {
  const order = doc.data();
  const result = {
    id: doc.id, product: order.product, status: order.status === 'creating' ? 'pending' : order.status,
    createdAt: order.createdAt, priceCents: order.priceCents, introductory: order.introductory,
  };
  if (admin) {
    result.email = order.email;
    result.paymentId = order.paymentId || null;
    result.approvedAt = order.approvedAt || null;
    result.reviewReason = order.reviewReason || null;
    result.duplicatePaymentId = order.duplicatePaymentId || null;
  }
  return result;
}

function displayLicense(doc) {
  const license = doc.data();
  return {
    id: doc.id, key: license.key, product: license.product, expiresAt: license.expiresAt,
    active: isActive(license), revoked: license.revoked, source: license.source, label: license.label,
  };
}

class Store {
  constructor(db, sandbox = false) {
    this.db = db;
    const root = sandbox ? db.collection('testStore').doc('mercadoPago') : db;
    this.accounts = root.collection('accounts');
    this.orders = root.collection('orders');
    this.licenses = root.collection('licenses');
    this.tokens = root.collection('activationTokens');
    this.payments = root.collection('payments');
    this.stats = root.collection('storeStats').doc('public');
  }

  async buyers() {
    return (await this.stats.get()).get('buyers') || 0;
  }

  async account(user) {
    const [person, orders, licenses] = await Promise.all([
      this.accounts.doc(user.uid).get(),
      this.orders.where('uid', '==', user.uid).orderBy('createdAt', 'desc').limit(100).get(),
      this.licenses.where('uid', '==', user.uid).get(),
    ]);
    return {
      orders: orders.docs.map((doc) => displayOrder(doc)),
      licenses: licenses.docs.map(displayLicense),
      admin: user.maxAdmin === true,
      eligibleIntro: eligibleIntro(person.data() || {}),
    };
  }

  async purchases(cursor) {
    let query = this.orders.orderBy('createdAt', 'desc');
    if (cursor) {
      if (typeof cursor !== 'string' || !ORDER_ID.test(cursor)) throw new ApiError(400, 'Página inválida.');
      const start = await this.orders.doc(cursor).get();
      if (!start.exists) throw new ApiError(400, 'Página inválida.');
      query = query.startAfter(start);
    }
    const results = (await query.limit(101).get()).docs;
    return {
      orders: results.slice(0, 100).map((doc) => displayOrder(doc, true)),
      cursor: results.length > 100 ? results[99].id : null,
    };
  }

  async testKeys() {
    const results = await this.licenses.where('source', '==', 'test').orderBy('createdAt', 'desc').limit(100).get();
    return { licenses: results.docs.map(displayLicense) };
  }

  async reserveCheckout(user, product) {
    const accountRef = this.accounts.doc(user.uid);
    const freshOrderRef = this.orders.doc(randomUUID());
    const lease = randomUUID();
    const now = unixTime();
    return this.db.runTransaction(async (transaction) => {
      const account = (await transaction.get(accountRef)).data() || {};
      const priorId = account.checkout?.[product.id];
      const priorRef = priorId ? this.orders.doc(priorId) : null;
      const prior = priorRef ? (await transaction.get(priorRef)).data() : null;
      if (prior?.checkoutUntil > now && ['creating', 'pending', 'rejected'].includes(prior.status)) {
        if (prior.url) return { url: prior.url };
        if (prior.leaseUntil > now) throw new ApiError(409, 'Checkout sendo preparado. Tente novamente em instantes.');
        transaction.update(priorRef, { lease, leaseUntil: now + CHECKOUT_LEASE });
        return { ...prior, lease };
      }
      const introductory = product.id === 'combo' && eligibleIntro(account);
      const order = {
        id: freshOrderRef.id, uid: user.uid, email: user.email, product: product.id,
        priceCents: introductory ? INTRO_COMBO_CENTS : product.priceCents,
        introductory, status: 'creating', createdAt: now, checkoutUntil: now + CHECKOUT_SECONDS,
        lease, leaseUntil: now + CHECKOUT_LEASE, url: null,
      };
      transaction.create(freshOrderRef, order);
      transaction.set(accountRef, { checkout: { [product.id]: order.id } }, { merge: true });
      return order;
    });
  }

  async finishCheckout(order, details) {
    const ref = this.orders.doc(order.id);
    return this.db.runTransaction(async (transaction) => {
      const latest = (await transaction.get(ref)).data();
      if (latest.url) return latest.url;
      if (latest.lease !== order.lease) throw new ApiError(409, 'Checkout atualizado. Clique em comprar novamente.');
      transaction.update(ref, { ...details, status: latest.status === 'creating' ? 'pending' : latest.status, leaseUntil: 0 });
      return details.url;
    });
  }

  async releaseCheckout(order) {
    const ref = this.orders.doc(order.id);
    await this.db.runTransaction(async (transaction) => {
      const latest = (await transaction.get(ref)).data();
      if (latest.lease === order.lease && !latest.url) transaction.update(ref, { leaseUntil: 0 });
    });
  }

  async recordPayment(payment, id, sandbox) {
    const orderId = payment.external_reference;
    if (typeof orderId !== 'string' || !ORDER_ID.test(orderId)) return;
    const updated = Date.parse(payment.date_last_updated || payment.date_created || '');
    if (!Number.isFinite(updated)) throw new ApiError(502, 'Pagamento recebido sem data de atualização.');
    const paymentRef = this.payments.doc(id);
    const orderRef = this.orders.doc(orderId);
    const state = paymentState(payment);
    const key = makeKey();
    const licenseId = parseKey(key);
    const now = unixTime();
    await this.db.runTransaction(async (transaction) => {
      const [orderDoc, paymentDoc] = await transaction.getAll(orderRef, paymentRef);
      const order = orderDoc.data();
      const previous = paymentDoc.data();
      if (!order || previous?.updated > updated || previous?.state === 'refunded' ||
          (previous?.updated === updated && previous?.state === state)) return;
      if (!paymentMatches(payment, order, id, sandbox)) {
        transaction.update(orderRef, { reviewReason: 'O pagamento não corresponde ao pedido esperado.' });
        return;
      }
      const accountRef = this.accounts.doc(order.uid);
      const account = (await transaction.get(accountRef)).data() || {};
      transaction.set(paymentRef, { orderId, state, updated });
      if (state === 'refunded' && order.paymentId === id && order.status === 'approved') {
        transaction.update(orderRef, { status: 'refunded', refundedAt: now });
        transaction.update(this.licenses.doc(order.licenseId), { revoked: true, revokedAt: now });
        transaction.update(accountRef, { activeOrders: Math.max(0, (account.activeOrders || 0) - 1) });
        if (account.activeOrders === 1) transaction.set(this.stats, { buyers: FieldValue.increment(-1) }, { merge: true });
        return;
      }
      if (state === 'approved') {
        if (order.paymentId === id && order.status === 'approved') return;
        if (order.paymentId || (order.introductory && account.introUsed && account.introUsed !== orderId)) {
          transaction.update(orderRef, {
            duplicatePaymentId: id, reviewReason: 'Pagamento duplicado ou promoção já utilizada. Verifique no Mercado Pago.',
            status: order.paymentId ? order.status : 'review',
          });
          return;
        }
        transaction.create(this.licenses.doc(licenseId), {
          key, uid: order.uid, product: order.product, orderId, expiresAt: null,
          source: 'purchase', label: '', revoked: false, createdAt: now,
        });
        transaction.update(orderRef, {
          status: 'approved', paymentId: id, licenseId, approvedAt: now,
          reviewReason: FieldValue.delete(),
        });
        transaction.set(accountRef, {
          paidOrders: (account.paidOrders || 0) + 1,
          activeOrders: (account.activeOrders || 0) + 1,
          ...(order.introductory ? { introUsed: orderId } : {}),
        }, { merge: true });
        if (!account.activeOrders) transaction.set(this.stats, { buyers: FieldValue.increment(1) }, { merge: true });
        return;
      }
      if (!order.paymentId && ['creating', 'pending'].includes(order.status)) {
        const status = state === 'refunded' ? 'refunded' : state;
        transaction.update(orderRef, { status });
      }
    });
  }

  async createTestKey(admin, product, days, label) {
    getProduct(product);
    const length = days ?? 30;
    if (!Number.isInteger(length) || length < 1 || length > 365 || typeof (label ?? '') !== 'string' || (label || '').length > 100) {
      throw new ApiError(400, 'Use uma duração entre 1 e 365 dias e um nome de até 100 caracteres.');
    }
    const now = unixTime();
    const key = makeKey();
    const id = parseKey(key);
    const expiresAt = now + length * 86400;
    await this.licenses.doc(id).create({
      key, product, label: (label || '').trim(), uid: null, source: 'test', revoked: false,
      createdAt: now, createdBy: admin.uid, expiresAt,
    });
    return { key, id, expiresAt };
  }

  async revokeKey(id) {
    if (typeof id !== 'string' || !HASH_ID.test(id)) throw new ApiError(400, 'Identificador de chave inválido.');
    const ref = this.licenses.doc(id);
    await this.db.runTransaction(async (transaction) => {
      if (!(await transaction.get(ref)).exists) throw new ApiError(404, 'Chave não encontrada.');
      transaction.update(ref, { revoked: true, revokedAt: unixTime() });
    });
  }

  async claimKey(user, key) {
    const licenseRef = this.licenses.doc(parseKey(key));
    await this.db.runTransaction(async (transaction) => {
      const license = (await transaction.get(licenseRef)).data();
      ensureActive(license);
      if (license.uid === user.uid) return;
      if (license.source !== 'test' || license.uid) throw new ApiError(403, 'A chave pertence a outra conta.');
      transaction.update(licenseRef, { uid: user.uid });
    });
  }

  async hasProduct(uid, product) {
    const found = await this.licenses.where('uid', '==', uid).get();
    return found.docs.some((doc) => {
      const license = doc.data();
      return isActive(license) && packageProducts(license.product).includes(product);
    });
  }

  async activate(key, deviceId) {
    const id = parseKey(key);
    const device = deviceHash(deviceId);
    const token = randomBytes(32).toString('base64url');
    const tokenId = hash(token);
    const licenseRef = this.licenses.doc(id);
    const now = unixTime();
    return this.db.runTransaction(async (transaction) => {
      const license = (await transaction.get(licenseRef)).data();
      ensureActive(license, now);
      const devices = license.devices || {};
      if (!devices[device] && Object.keys(devices).length >= MAX_DEVICES) {
        throw new ApiError(409, 'A chave já está ativa em três dispositivos.');
      }
      if (devices[device]) transaction.delete(this.tokens.doc(devices[device]));
      transaction.update(licenseRef, { devices: { ...devices, [device]: tokenId } });
      transaction.create(this.tokens.doc(tokenId), { licenseId: id, device });
      return grant(license, token, now);
    });
  }

  async refresh(token, deviceId) {
    const device = deviceHash(deviceId);
    if (typeof token !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(token)) {
      throw new ApiError(403, 'Ativação inválida. Use sua chave para ativar novamente.');
    }
    const tokenId = hash(token);
    const tokenRef = this.tokens.doc(tokenId);
    return this.db.runTransaction(async (transaction) => {
      const activation = (await transaction.get(tokenRef)).data();
      if (activation?.device !== device) throw new ApiError(403, 'Ativação indisponível para este dispositivo.');
      const license = (await transaction.get(this.licenses.doc(activation.licenseId))).data();
      ensureActive(license);
      if (license.devices?.[device] !== tokenId) throw new ApiError(403, 'Ative a chave novamente neste dispositivo.');
      return grant(license, token, unixTime());
    });
  }
}

module.exports = { Store };
