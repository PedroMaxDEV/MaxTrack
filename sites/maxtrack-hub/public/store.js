const byId = id => document.getElementById(id);
const dialog = byId("account-dialog");
const productNames = {
  track: "MaxTrack Pro",
  gps: "Max GPS",
  media: "Max Multimídia",
  combo: "Combo Max Hub",
};
const prices = { track: 3990, gps: 2990, media: 2490, combo: 6990, intro: 5990 };
const priceFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const numberFormat = new Intl.NumberFormat("pt-BR");
const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" });
const money = cents => priceFormat.format(cents / 100);
const orderStates = {
  created: "Aguardando pagamento", pending: "Aguardando pagamento",
  in_process: "Em análise", approved: "Pagamento aprovado", paid: "Pagamento aprovado",
  cancelled: "Cancelado", canceled: "Cancelado", rejected: "Recusado",
  refunded: "Reembolsado", charged_back: "Estornado", expired: "Expirado", review: "Em revisão",
};
let auth;
let sdk;
let user;
let account;
let pendingProduct = "";
let checkoutReturn = checkoutReturnMessage();
let adminOrders = [];
let orderCursor = "";
let accountTab = "overview";
let lastBuyerCount;
let noticeTimer;
let accountLoading = false;

function selectAccountTab(tab) {
  if (tab === "admin" && account?.admin !== true) tab = "overview";
  accountTab = tab;
  for (const button of document.querySelectorAll("[data-account-tab]")) {
    const selected = button.dataset.accountTab === tab;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    byId(button.getAttribute("aria-controls")).hidden = !selected;
  }
}

function saleNotice(title, detail) {
  if (dialog.open || document.hidden) return;
  clearTimeout(noticeTimer);
  byId("sale-title").textContent = title;
  byId("sale-detail").textContent = detail;
  byId("sale-notice").hidden = false;
  noticeTimer = setTimeout(() => { byId("sale-notice").hidden = true; }, 6500);
}

function node(tag, text = "", className = "") {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function message(text = "", error = false) {
  const line = byId("account-message");
  line.textContent = text;
  line.dataset.error = error;
}

function showAccount(product = "") {
  pendingProduct = product;
  byId("sale-notice").hidden = true;
  selectAccountTab(checkoutReturn ? "orders" : "overview");
  byId("login-intro").textContent = product
    ? `Entre para conferir ${productNames[product]} e seguir para o pagamento.`
    : "Seus produtos, downloads e pedidos em um só lugar.";
  if (!dialog.open) dialog.showModal();
  if (product) {
    message(user ? "Confira o pedido antes de continuar." : `Entre com Google para comprar ${productNames[product]}.`);
  } else if (!checkoutReturn) message();
  renderCheckout();
}

function checkoutReturnMessage() {
  const params = new URLSearchParams(location.search);
  if (!["pagamento", "collection_status", "payment_id"].some(key => params.has(key))) return "";
  return "A confirmação de pagamento aparece em Meus pedidos. Se ainda estiver aguardando, atualize a conta em instantes.";
}

async function responseError(response) {
  const details = await response.json().catch(() => null);
  if (typeof details?.error === "string") return details.error;
  if (response.status === 401) return "Entre novamente para acessar sua conta.";
  if (response.status === 403) return "Sua conta não tem acesso a este recurso.";
  return "O serviço da loja está indisponível. Tente novamente em instantes.";
}

async function request(path, { method = "GET", data, authorize = true, binary = false } = {}) {
  const headers = new Headers();
  if (authorize) {
    if (!user) throw new Error("Entre com Google para continuar.");
    headers.set("Authorization", `Bearer ${await user.getIdToken()}`);
  }
  if (data) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, {
    method, headers, credentials: "same-origin", cache: "no-store",
    body: data ? JSON.stringify(data) : undefined,
  });
  if (!response.ok) throw new Error(await responseError(response));
  const type = response.headers.get("Content-Type") || "";
  if (binary) {
    if (!/^application\/(vnd\.android\.package-archive|octet-stream)\b/i.test(type)) {
      throw new Error("O APK ainda não está disponível. Tente novamente em instantes.");
    }
    return response.blob();
  }
  if (!type.includes("application/json")) throw new Error("A API da loja ainda não está configurada neste ambiente.");
  return response.json();
}

function renderCatalog() {
  for (const element of document.querySelectorAll("[data-price]")) {
    element.textContent = money(prices[element.dataset.price]);
  }
  const intro = !user || account?.eligibleIntro === true;
  const effective = intro ? prices.intro : prices.combo;
  byId("offer-note").hidden = !intro;
  byId("combo-regular").hidden = !intro || effective >= prices.combo;
  byId("combo-price-label").textContent = intro ? "Primeira compra" : "Pagamento único";
  byId("featured-price").textContent = money(effective);
  const savings = prices.track + prices.gps + prices.media - effective;
  byId("combo-savings").textContent = savings > 0
    ? `Economize ${money(savings)} comprando os três juntos${intro ? " na primeira compra" : ""}.`
    : "Os três produtos reunidos em uma única chave.";
  renderCheckout();
}

async function loadCatalog() {
  try {
    const catalog = await request("/catalog", { authorize: false });
    for (const product of catalog.products || []) {
      if (product.id in productNames && Number.isSafeInteger(product.priceCents) && product.priceCents > 0) {
        prices[product.id] = product.priceCents;
      }
    }
    if (Number.isSafeInteger(catalog.introComboCents) && catalog.introComboCents > 0) {
      prices.intro = catalog.introComboCents;
    }
    if (Number.isSafeInteger(catalog.buyers) && catalog.buyers >= 0) {
      const count = byId("buyer-count");
      count.textContent = catalog.buyers === 1 ? "1 pessoa já comprou" : `${numberFormat.format(catalog.buyers)} pessoas já compraram`;
      count.hidden = catalog.buyers === 0;
      if (lastBuyerCount !== undefined && catalog.buyers > lastBuyerCount) {
        const change = catalog.buyers - lastBuyerCount;
        saleNotice(change === 1 ? "Mais um motorista com Max Hub" : `${numberFormat.format(change)} novos compradores confirmados`,
          "Compras confirmadas desde a última consulta à loja.");
      }
      lastBuyerCount = catalog.buyers;
    }
  } catch {
    // The catalog remains readable in a static preview.
  }
  renderCatalog();
}

function renderCheckout() {
  const panel = byId("checkout-panel");
  panel.hidden = !pendingProduct || !user;
  document.querySelector(".account-nav").hidden = !panel.hidden;
  if (!panel.hidden) {
    for (const view of document.querySelectorAll(".account-view")) view.hidden = true;
  }
  byId("confirm-checkout").disabled = accountLoading || !account;
  if (panel.hidden) return;
  const intro = pendingProduct === "combo" && account?.eligibleIntro === true;
  byId("checkout-title").textContent = productNames[pendingProduct];
  const value = money(intro ? prices.intro : prices[pendingProduct]);
  const condition = intro ? " · oferta de primeira compra" : "";
  byId("checkout-copy").textContent = `${value} por pagamento único${condition}. O desconto e o valor final são validados pelo servidor.`;
}

function displayDate(value) {
  if (value === undefined || value === null) return "";
  const input = typeof value === "number" && value < 10 ** 12 ? value * 1000 : value;
  const date = new Date(input);
  return Number.isNaN(date.getTime()) ? "" : dateFormat.format(date);
}

function licenseIsActive(license) {
  if (license.revoked || license.revokedAt || license.active === false || ["expired", "revoked", "inactive"].includes(license.status)) return false;
  if (!license.expiresAt) return true;
  let expiration = license.expiresAt;
  if (typeof expiration === "number" && expiration < 10 ** 12) expiration *= 1000;
  return new Date(expiration) > new Date();
}

function listFor(container, entries, emptyText, itemView) {
  container.replaceChildren();
  if (!entries.length) {
    container.append(node("p", emptyText));
    return;
  }
  const list = node("ul", "", "account-list");
  for (const entry of entries) list.append(itemView(entry));
  container.append(list);
}

function copyLine(value, copyLabel = "Copiar chave") {
  const line = node("div", "", "key-line");
  const key = node("code", value);
  const button = node("button", copyLabel, "inline-action");
  button.type = "button";
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(value);
      message("Copiado para a área de transferência.");
    } catch {
      getSelection()?.selectAllChildren(key);
      message("Selecione o texto e copie com Ctrl+C, ou mantenha pressionado no celular.");
    }
  });
  line.append(key, button);
  return line;
}

function licenseRow(license) {
  const row = node("li");
  const active = licenseIsActive(license);
  const expires = displayDate(license.expiresAt);
  row.append(node("strong", productNames[license.product] || license.product || "Licença"));
  row.append(node("p", active ? expires ? `Ativa até ${expires}` : "Ativa" : "Inativa"));
  if (active && typeof license.key === "string" && license.key) {
    const details = node("details", "", "license-details");
    details.append(node("summary", "Ver chave de ativação"), copyLine(license.key));
    row.append(details);
  }
  return row;
}

function orderRow(order, admin = false) {
  const row = node("li");
  const title = productNames[order.product] || order.product || "Pedido";
  const status = orderStates[order.status] || order.status || "Aguardando pagamento";
  const amount = order.amountCents ?? order.priceCents;
  const metadata = [status];
  if (Number.isSafeInteger(amount)) metadata.push(money(amount));
  const date = displayDate(order.createdAt);
  if (date) metadata.push(date);
  row.append(node("strong", title), node("p", metadata.join(" · ")));
  const details = admin ? [order.email, order.id] : [order.id];
  const identifier = details.filter(Boolean).join(" · ");
  if (identifier) row.append(node("p", identifier));
  if (admin && order.reviewReason) row.append(node("p", order.reviewReason));
  return row;
}

function testLicenseRow(license) {
  const row = node("li");
  const name = productNames[license.product] || "Licença de teste";
  const expires = displayDate(license.expiresAt);
  const metadata = [licenseIsActive(license) ? "Ativa" : "Inativa"];
  if (expires) metadata.push(`Até ${expires}`);
  if (license.label) metadata.push(license.label);
  row.append(node("strong", name), node("p", metadata.join(" · ")));
  if (license.id) row.append(copyLine(license.id, "Copiar ID"));
  return row;
}

function renderAccount() {
  byId("login-panel").hidden = Boolean(user);
  byId("customer-panel").hidden = !user;
  byId("account-identity").textContent = user
    ? user.email || user.displayName || "Conta conectada"
    : "Entre para acompanhar seus produtos e suas compras.";
  byId("account-title").textContent = user ? "Sua central de bordo." : "Bem-vindo à cabine.";
  byId("tab-admin").hidden = account?.admin !== true;
  const licenses = Array.isArray(account?.licenses) ? account.licenses : [];
  const orders = Array.isArray(account?.orders) ? account.orders : [];
  listFor(byId("licenses"), licenses, "Nenhuma chave disponível.", licenseRow);
  listFor(byId("orders"), orders, "Nenhum pedido encontrado.", order => orderRow(order));
  const gps = licenses.some(license => ["gps", "combo"].includes(license.product) && licenseIsActive(license));
  byId("download-apk").hidden = !gps;
  const active = new Set();
  for (const license of licenses.filter(licenseIsActive)) {
    for (const product of license.product === "combo" ? ["track", "gps", "media"] : [license.product]) active.add(product);
  }
  const name = user?.displayName?.split(" ")[0] || "motorista";
  byId("customer-avatar").textContent = name[0].toUpperCase();
  byId("customer-greeting").textContent = `Olá, ${name}.`;
  byId("summary-products").textContent = account ? active.size : "—";
  byId("summary-orders").textContent = account ? orders.length : "—";
  byId("account-summary").textContent = account
    ? active.size ? "Tudo pronto para preparar sua próxima viagem." : "Escolha o que vai fazer parte da sua cabine."
    : accountLoading ? "Buscando seus produtos e pedidos…" : "Sua conta ainda não carregou. Tente Atualizar conta.";
  byId("account-next-title").textContent = active.size ? "Seu próximo passo" : "Monte sua cabine";
  byId("account-next-copy").textContent = active.size
    ? "Baixe o Hub e abra Meus produtos para consultar sua ativação."
    : "Conheça os produtos na vitrine. Suas compras confirmadas vão aparecer aqui.";
  selectAccountTab(accountTab);
  renderCatalog();
}

async function loadAccount() {
  const current = user;
  if (!current) return false;
  if (accountLoading) return false;
  accountLoading = true;
  byId("customer-panel").setAttribute("aria-busy", "true");
  renderAccount();
  try {
    const information = await request("/account");
    if (user !== current) return false;
    account = information;
    renderAccount();
    return true;
  } catch (error) {
    if (user === current) message(error.message, true);
    return false;
  } finally {
    accountLoading = false;
    byId("customer-panel").setAttribute("aria-busy", "false");
    if (user === current) renderAccount();
    else if (user) loadAccount();
  }
}

async function withButton(button, action) {
  if (button.disabled) return;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    await action();
  } catch (error) {
    message(error.message, true);
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

function connectFirebase() {
  return fetch("/__/firebase/init.json", { cache: "no-store" }).then(async response => {
    if (!response.ok) throw new Error("Login disponível depois de configurar e executar o site no Firebase.");
    const config = await response.json().catch(() => null);
    if (!config?.projectId || !config?.apiKey || !config?.authDomain) {
      throw new Error("Configure o login Google no projeto Firebase para continuar.");
    }
    let appSdk;
    try {
      [appSdk, sdk] = await Promise.all([
        import("https://www.gstatic.com/firebasejs/12.6.0/firebase-app.js"),
        import("https://www.gstatic.com/firebasejs/12.6.0/firebase-auth.js"),
      ]);
    } catch {
      throw new Error("Não foi possível carregar o login Google. Confira sua conexão e tente novamente.");
    }
    auth = sdk.getAuth(appSdk.initializeApp(config));
    sdk.onAuthStateChanged(auth, next => {
      user = next;
      account = null;
      selectAccountTab(checkoutReturn ? "orders" : "overview");
      adminOrders = [];
      orderCursor = "";
      byId("admin-order-list").replaceChildren();
      byId("admin-license-list").replaceChildren();
      byId("admin-more-orders").hidden = true;
      byId("admin-key-result").replaceChildren();
      byId("admin-key-result").hidden = true;
      renderAccount();
      if (next) {
        loadAccount();
        if (pendingProduct) message("Confira o pedido antes de continuar.");
      }
    });
  });
}

// Start initialization while the visitor browses; keep failure visible on demand.
let firebaseError;
const firebaseReady = connectFirebase().catch(error => { firebaseError = error; });
function friendlyLoginError(error) {
  return ({
    "auth/popup-closed-by-user": "A janela do Google foi fechada.",
    "auth/popup-blocked": "Permita janelas pop-up para entrar com Google.",
    "auth/unauthorized-domain": "Este domínio precisa ser autorizado no Firebase Authentication.",
    "auth/operation-not-allowed": "Ative o provedor Google no Firebase Authentication.",
  })[error.code] || error.message;
}

function redirectToCheckout(url) {
  let destination;
  try { destination = new URL(url); } catch { throw new Error("O link de pagamento é inválido."); }
  const domain = destination.hostname.toLowerCase();
  const providers = ["mercadopago.com.br", "mercadopago.com"];
  if (destination.protocol !== "https:" || destination.username || destination.password
    || !providers.some(provider => domain === provider || domain.endsWith(`.${provider}`))) {
    throw new Error("O link de pagamento é inválido.");
  }
  location.assign(destination.href);
}

async function downloadWindows(button) {
  const note = byId("windows-status");
  note.textContent = "Consultando a versão do Windows…";
  try {
    const response = await fetch("/downloads/update.json", { cache: "no-store" });
    if (!response.ok) throw new Error();
    const release = await response.json();
    let file;
    if (typeof release.path === "string" && release.path.startsWith("/downloads/releases/")) {
      file = new URL(release.path, location.origin);
    }
    if (!file || file.origin !== location.origin || !/^\/downloads\/releases\/[a-zA-Z0-9._/-]+\.exe$/.test(file.pathname)) throw new Error();
    const link = node("a");
    link.href = file.href;
    link.download = file.pathname.split("/").pop();
    link.click();
    note.textContent = `Download do Max Hub ${typeof release.version === "string" ? release.version : ""} solicitado.`;
  } catch {
    note.textContent = "O instalador para Windows ainda não está disponível neste ambiente.";
    if (!note.getBoundingClientRect().height || Math.abs(button.getBoundingClientRect().top - note.getBoundingClientRect().top) > 300) {
      note.scrollIntoView({ block: "center" });
    }
  }
}

for (const button of document.querySelectorAll("[data-download=windows]")) {
  button.addEventListener("click", () => withButton(button, () => downloadWindows(button)));
}
for (const button of document.querySelectorAll("[data-buy]")) {
  button.addEventListener("click", () => showAccount(button.dataset.buy));
}
byId("account-button").addEventListener("click", () => showAccount());
for (const button of document.querySelectorAll("[data-open-account]")) {
  button.addEventListener("click", () => showAccount());
}
byId("close-account").addEventListener("click", () => dialog.close());
dialog.addEventListener("close", () => {
  checkoutReturn = "";
  pendingProduct = "";
  message();
});
byId("google-login").addEventListener("click", event => withButton(event.currentTarget, async () => {
  await firebaseReady;
  if (!auth) {
    // Retry a transient configuration or SDK fetch error.
    await connectFirebase().catch(error => { firebaseError = error; });
    if (!auth) throw firebaseError;
  }
  try {
    const provider = new sdk.GoogleAuthProvider();
    provider.setCustomParameters({ prompt: "select_account" });
    await sdk.signInWithPopup(auth, provider);
  } catch (error) {
    throw new Error(friendlyLoginError(error), { cause: error });
  }
}));
byId("logout").addEventListener("click", event => withButton(event.currentTarget, async () => {
  await sdk.signOut(auth);
  message("Sessão encerrada.");
}));
byId("refresh-account").addEventListener("click", event => withButton(event.currentTarget, async () => {
  if (!user) return;
  await user.getIdToken(true);
  if (await loadAccount()) message("Conta atualizada.");
}));
byId("confirm-checkout").addEventListener("click", event => withButton(event.currentTarget, async () => {
  if (!pendingProduct || !account) return;
  const order = await request("/checkout", { method: "POST", data: { product: pendingProduct } });
  redirectToCheckout(order.url);
}));
byId("download-apk").addEventListener("click", event => withButton(event.currentTarget, async () => {
  const blob = await request("/download/apk", { binary: true });
  const url = URL.createObjectURL(blob);
  const link = node("a");
  link.href = url;
  link.download = "MaxGPS-Android.apk";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
  message("Download do APK solicitado.");
}));
byId("claim-form").addEventListener("submit", event => {
  event.preventDefault();
  const form = event.currentTarget;
  return withButton(form.querySelector("button"), async () => {
    await request("/account/claim", { method: "POST", data: { key: byId("claim-key").value.trim() } });
    form.reset();
    if (await loadAccount()) message("Chave vinculada à sua conta.");
  });
});
for (const button of document.querySelectorAll("[data-account-tab]")) {
  button.addEventListener("click", () => selectAccountTab(button.dataset.accountTab));
  button.addEventListener("keydown", event => {
    const buttons = [...document.querySelectorAll("[data-account-tab]")].filter(item => !item.hidden);
    const index = buttons.indexOf(button);
    let next;
    if (event.key === "ArrowRight") next = buttons[(index + 1) % buttons.length];
    if (event.key === "ArrowLeft") next = buttons[(index + buttons.length - 1) % buttons.length];
    if (event.key === "Home") next = buttons[0];
    if (event.key === "End") next = buttons[buttons.length - 1];
    if (next) {
      event.preventDefault();
      selectAccountTab(next.dataset.accountTab);
      next.focus();
    }
  });
}
for (const button of document.querySelectorAll("[data-account-open]")) {
  button.addEventListener("click", () => selectAccountTab(button.dataset.accountOpen));
}
byId("cancel-checkout").addEventListener("click", () => {
  pendingProduct = "";
  renderCheckout();
  selectAccountTab("overview");
  message();
});
byId("close-sale").addEventListener("click", () => {
  clearTimeout(noticeTimer);
  byId("sale-notice").hidden = true;
});
byId("demo-sale").addEventListener("click", () => {
  if (account?.admin !== true) return;
  dialog.close();
  saleNotice("Demonstração da animação", "Exemplo visual · esta mensagem não representa uma compra.");
});

const animatedSections = document.querySelectorAll(".section-intro, .combo, .product, .setup-inner, .faq-section");
if ("IntersectionObserver" in window && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) {
      entry.target.classList.add("revealed");
      observer.unobserve(entry.target);
    }
  }, { threshold: .08 });
  for (const section of animatedSections) {
    section.classList.add("reveal");
    observer.observe(section);
  }
}
setInterval(() => {
  if (!document.hidden) loadCatalog();
}, 45000);
async function getAdminOrders(cursor = "") {
  const current = user;
  const path = cursor ? `/admin/orders?cursor=${encodeURIComponent(cursor)}` : "/admin/orders";
  const data = await request(path);
  if (user !== current || !account?.admin) return;
  const received = Array.isArray(data.orders) ? data.orders : [];
  adminOrders = cursor ? [...adminOrders, ...received] : received;
  orderCursor = data.cursor || "";
  byId("admin-more-orders").hidden = !orderCursor;
  listFor(byId("admin-order-list"), adminOrders, "Nenhum pedido encontrado.", order => orderRow(order, true));
}

async function getAdminLicenses() {
  const current = user;
  const data = await request("/admin/licenses");
  if (user !== current || !account?.admin) return;
  const licenses = Array.isArray(data.licenses) ? data.licenses.filter(license => license.source === "test") : [];
  listFor(byId("admin-license-list"), licenses, "Nenhuma licença de teste encontrada.", testLicenseRow);
}

byId("admin-orders").addEventListener("click", event => withButton(event.currentTarget, getAdminOrders));
byId("admin-more-orders").addEventListener("click", event => withButton(event.currentTarget, () => getAdminOrders(orderCursor)));
byId("admin-licenses").addEventListener("click", event => withButton(event.currentTarget, getAdminLicenses));
byId("admin-create").addEventListener("submit", event => {
  event.preventDefault();
  const form = event.currentTarget;
  return withButton(form.querySelector("button"), async () => {
    const created = await request("/admin/licenses", {
      method: "POST",
      data: { product: byId("test-product").value, days: Number(byId("test-days").value), label: byId("test-label").value.trim() },
    });
    const result = byId("admin-key-result");
    result.replaceChildren(node("p", "Compartilhe a chave com a pessoa que vai testar."), copyLine(created.key),
      copyLine(created.id, "Copiar ID"));
    result.hidden = false;
    byId("revoke-id").value = created.id;
    message("Chave de teste criada.");
  });
});
byId("admin-revoke").addEventListener("submit", event => {
  event.preventDefault();
  const form = event.currentTarget;
  const id = byId("revoke-id").value.trim();
  if (!window.confirm("Revogar esta chave? A licença será desativada na próxima validação do Hub.")) return;
  return withButton(form.querySelector("button"), async () => {
    await request("/admin/revoke", { method: "POST", data: { id } });
    form.reset();
    message("Chave revogada.");
    await getAdminLicenses();
  });
});

loadCatalog();
if (checkoutReturn || location.hash === "#conta") {
  showAccount();
  message(checkoutReturn);
}
