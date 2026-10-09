const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

function authHeaders() {
  return {"X-Telegram-Init-Data": (window.Telegram?.WebApp?.initData) || ""};
}

const state = {
  orders: [],
  clients: [],
  bso: [],
  view: "start",
  ordersFilter: "recent",
  ordersMonth: null,
  ordersDate: null,
  selectedDate: null,
  callsDate: null,
  bsoFilter: "all",
  bsoDate: null,
};

const dialog = document.getElementById("orderDialog");
const detailEl = document.getElementById("detail");

const VIEW_SECTIONS = {
  start: "screen-start",
  schedule: "screen-schedule",
  clients: "screen-clients",
  orders: "screen-orders",
  calls: "screen-calls",
  bso: "screen-bso",
};

const MONTHS_RU = ["Январь","Февраль","Март","Апрель","Май","Июнь","Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"];
const MONTHS_GEN = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"];
const WEEKDAYS_RU = ["Вс","Пн","Вт","Ср","Чт","Пт","Сб"];

/* ---------- утилиты ---------- */

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}

function paid(o) {
  return String(o.status || "").toLowerCase() === "paid";
}

function statusOrAmount(o) {
  if (paid(o) && o.payment?.amount != null) return rub(o);
  return String(o.status || "—");
}

function sessionLabel(session) {
  const s = String(session || "").trim().replace(/^[-\s–—•]+/, "").replace(/[\s;.]+$/, "");
  if (!s) return "—";
  return s.replace(/\s+с\s+/i, " · с ");
}

function rub(o) {
  if (o.payment?.amount == null) return "—";
  return Number(o.payment.amount).toLocaleString("ru-RU") + " ₽";
}

function fmtMoney(n) {
  const num = Number(n);
  if (n == null || isNaN(num)) return "—";
  return num.toLocaleString("ru-RU", {maximumFractionDigits: 2}) + " ₽";
}

function normPhone(v) {
  const d = String(v || "").replace(/\D/g, "");
  if (d.length === 10 && d[0] === "9") return "7" + d;
  if (d.length === 11 && d[0] === "8") return "7" + d.slice(1);
  return d;
}

function phoneLink(v) {
  const p = normPhone(v);
  return p ? "+" + p : "";
}

function phonePretty(v) {
  const p = normPhone(v);
  if (p.length === 11 && p[0] === "7") {
    return `+7 (${p.slice(1, 4)}) ${p.slice(4, 7)}-${p.slice(7, 9)}-${p.slice(9, 11)}`;
  }
  return phoneLink(v);
}

/* --- время поступления: в базе UTC, показываем и группируем по Москве --- */
const MSK_OFFSET_MS = 3 * 3600 * 1000;

function parseTs(value) {
  if (!value) return null;
  const s = String(value).trim().replace(" ", "T");
  const d = new Date(/(Z|[+-]\d{2}(?::?\d{2})?)$/.test(s) ? s : s + "Z");
  return isNaN(d.getTime()) ? null : d;
}

function mskDate(value) {
  const d = parseTs(value);
  if (!d) return "";
  return new Date(d.getTime() + MSK_OFFSET_MS).toISOString().slice(0, 10);
}

function formatReceivedAt(value) {
  if (!value) return "";
  const d = parseTs(value);
  if (!d) return String(value);
  const s = new Date(d.getTime() + MSK_OFFSET_MS);
  const p = n => String(n).padStart(2, "0");
  return `${p(s.getUTCDate())}.${p(s.getUTCMonth() + 1)}.${String(s.getUTCFullYear()).slice(-2)} · ${p(s.getUTCHours())}:${p(s.getUTCMinutes())}`;
}

function formatCallDatetime(value) {
  if (!value) return "";
  const text = String(value).trim();
  const iso = text.includes("T") ? text : text.replace(" ", "T");
  const d = new Date(iso);
  if (isNaN(d.getTime())) return formatReceivedAt(text);
  const p = n => String(n).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${String(d.getFullYear()).slice(-2)} · ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function formatEventDate(value) {
  if (!value) return "";
  const text = String(value);
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return `${iso[3]}.${iso[2]}.${iso[1]}`;
  return text;
}

/* ---------- заказы: порядок и фильтр по дате поступления оплаты ---------- */

function receiptTime(o) {
  const d = parseTs(o?.received_at);
  return d ? d.getTime() : 0;
}

function sortByReceipt(list) {
  return [...list].sort((a, b) => {
    const ta = receiptTime(a), tb = receiptTime(b);
    if (ta !== tb) return tb - ta; // новые сверху
    return String(b.order_id).localeCompare(String(a.order_id));
  });
}

function receiptDays() {
  const set = new Set();
  state.orders.forEach(o => { const d = mskDate(o.received_at); if (d) set.add(d); });
  return [...set].sort().reverse(); // свежие слева
}

function latestReceiptDay() {
  return receiptDays()[0] || "";
}

function formatReceiptDay(iso) {
  const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return String(iso || "");
  const d = new Date(+m[1], +m[2] - 1, +m[3]);
  return `${m[3]}.${m[2]}.${m[1]}, ${WEEKDAYS_RU[d.getDay()]}`;
}



/* ---------- классификация игры / сеанса (дизайн, без БД) ---------- */

function gameClass(game) {
  const g = String(game || "").toLowerCase();
  if (g.includes("пейнтбол")) return "paintball";
  if (g.includes("лазер")) return "lasertag";
  if (g.includes("кидбол")) return "kidball";
  return "other";
}

function sessionInfo(session) {
  const s = String(session || "").toLowerCase();
  if (s.includes("утренн")) return { period: "Утро", time: "09:00–14:45" };
  if (s.includes("вечерн")) return { period: "Вечер", time: "15:15–21:00" };
  return { period: "Сеанс", time: session || "—" };
}

/* ---------- даты ---------- */

function pad2(n) { return String(n).padStart(2, "0"); }

function isoDate(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function mondayOf(d) {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dow = (x.getDay() + 6) % 7; // 0 = Пн … 6 = Вс
  x.setDate(x.getDate() - dow);
  return x;
}

function addDays(d, n) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

function fmtDayLong(d) {
  return `${WEEKDAYS_RU[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]}`;
}

/* ---------- фильтр-полоса дат (ползунок) ---------- */

function renderDayStrip(containerEl, selectedIso, onChange, opts) {
  const o = opts || {};
  const allowAll = !!o.allowAll;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  let html = '<div class="day-strip">';
  if (allowAll) {
    const activeAll = selectedIso == null || selectedIso === "";
    html += `<button class="day-chip all${activeAll ? " active" : ""}" data-date="">Все</button>`;
  }
  for (let i = -30; i <= 7; i++) {
    const day = addDays(today, i);
    const ds = isoDate(day);
    const active = ds === selectedIso;
    const isToday = ds === isoDate(today);
    html += `
      <button class="day-chip${active ? " active" : ""}${isToday ? " today" : ""}" data-date="${ds}">
        <span class="day-chip-dow">${WEEKDAYS_RU[day.getDay()]}</span>
        <span class="day-chip-num">${day.getDate()}</span>
      </button>`;
  }
  html += '</div>';
  containerEl.innerHTML = html;
  containerEl.querySelectorAll(".day-chip").forEach(btn => {
    btn.addEventListener("click", () => onChange(btn.dataset.date));
  });
  const sel = containerEl.querySelector(".day-chip.active");
  if (sel) sel.scrollIntoView({ inline: "center", block: "nearest" });
}

function ordersOn(dateStr) {
  return state.orders.filter(o => o.event?.date && String(o.event.date).slice(0, 10) === dateStr);
}

function dayHasOrders(dateStr) {
  return state.orders.some(o => o.event?.date && String(o.event.date).slice(0, 10) === dateStr);
}

function sortOrders(list) {
  const rank = o => {
    const s = String(o.event?.session || "").toLowerCase();
    if (s.includes("утренн")) return 0;
    if (s.includes("вечерн")) return 1;
    return 2;
  };
  return [...list].sort((a, b) => {
    const r = rank(a) - rank(b);
    if (r) return r;
    return String(a.event?.session || "").localeCompare(String(b.event?.session || ""), "ru");
  });
}

/* ---------- звонки ---------- */

function findClientByPhone(phone) {
  const p = normPhone(phone);
  if (!p) return null;
  return state.clients.find(c => normPhone(c.phone) === p) || null;
}

function orderForCall(call) {
  if (!call.order_id) return null;
  return state.orders.find(o => String(o.order_id) === String(call.order_id)) || null;
}

function callClientInfo(call) {
  const order = orderForCall(call);
  const client = (order && findClientByPhone(order.customer?.phone)) || findClientByPhone(call.phone);
  const name = (order?.customer?.name) || (client?.name) || "";
  return { order, client, name };
}

function callCard(call, options) {
  const opts = (options && typeof options === "object") ? options : {};
  const duration = Number(call.duration_seconds || 0);
  const mm = Math.floor(duration / 60);
  const ss = String(duration % 60).padStart(2, "0");
  const dt = formatCallDatetime(call.call_datetime);
  const showClient = Boolean(opts.showClient);
  const linked = showClient && Boolean(call.order_id);
  const info = showClient ? callClientInfo(call) : null;
  const clientName = linked && info ? info.name : "";
  const idxAttr = opts.index != null ? ` data-call-index="${opts.index}"` : "";
  return `
    <article class="call-card${linked ? " call-card-linked" : ""}"${idxAttr}>
      <div class="call-topline">
        <div class="call-date">📞 ${esc(dt || "Дата не указана")}</div>
        <div class="call-duration">${mm}:${ss}</div>
      </div>
      ${clientName ? `<div class="call-client">👤 ${esc(clientName)}</div>` : ""}
      <div class="call-admin">${esc(call.administrator || "Администратор не указан")}</div>
      <div class="call-phone">${esc(call.phone || "")}</div>
      ${call.audio_url ? `<audio class="call-audio" controls preload="none" src="${esc(call.audio_url)}"></audio>
      <button class="call-link" type="button" data-audio-link="${esc(permanentAudioLink(call.audio_url))}">🔗 Ссылка на запись</button>` : `<div class="call-unavailable">MP3 недоступен</div>`}
    </article>
  `;
}

/* ---------- записи звонков: громкость 50 % и постоянная ссылка на хранилище ---------- */

const CALL_VOLUME = 0.5; // по просьбе Артёма: запись играет вдвое тише
let callAudioCtx = null;
const callGainWired = new WeakSet();

/* Постоянная ссылка на файл: у presigned-ссылки отрезаем «?X-Amz-…» — бакет хранилища
   публичный, без подписи файл отдаётся всегда (проверено 09.10.2026). */
function permanentAudioLink(url) {
  return String(url || "").split("?")[0];
}

/* Громкость. На Android и ПК достаточно HTMLMediaElement.volume; на iPhone это свойство
   не работает (громкость — только кнопками телефона), поэтому там звук идёт через GainNode. */
function setCallVolume(el) {
  if (!el) return;
  try { el.volume = CALL_VOLUME; } catch (e) { /* свойство может быть только для чтения */ }
  if (Math.abs(Number(el.volume) - CALL_VOLUME) < 0.01) return;
  wireGainVolume(el);
}

function wireGainVolume(el) {
  if (callGainWired.has(el)) return;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return;
  try {
    if (!callAudioCtx) callAudioCtx = new Ctx();
    const source = callAudioCtx.createMediaElementSource(el);
    const gain = callAudioCtx.createGain();
    gain.gain.value = CALL_VOLUME;
    source.connect(gain);
    gain.connect(callAudioCtx.destination);
    callGainWired.add(el);
    const resume = () => {
      if (callAudioCtx && callAudioCtx.state === "suspended") callAudioCtx.resume().catch(() => {});
    };
    el.addEventListener("play", resume);
    el.addEventListener("click", resume);
    resume();
  } catch (e) { /* не получилось — пусть играет как есть, но не молчит */ }
}

/* Плеер и кнопка ссылки внутри карточки звонка: гасим всплытие, чтобы на экране «Звонки»
   нажатие на запись не открывало заодно карточку клиента. */
function initCallCards(root) {
  if (!root) return;
  root.querySelectorAll("audio.call-audio").forEach(el => {
    setCallVolume(el);
    ["click", "pointerdown", "mousedown", "touchstart"].forEach(ev =>
      el.addEventListener(ev, e => e.stopPropagation()));
  });
  root.querySelectorAll("[data-audio-link]").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation();
      copyText(btn.dataset.audioLink, btn);
    });
  });
}

let copyToastTimer = null;

function showCopyToast(text) {
  let el = document.getElementById("copyToast");
  if (!el) {
    el = document.createElement("div");
    el.id = "copyToast";
    el.className = "copy-toast";
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.classList.add("on");
  clearTimeout(copyToastTimer);
  copyToastTimer = setTimeout(() => el.classList.remove("on"), 1400);
}

async function copyText(text, btn) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    if (btn) {
      if (btn.tagName === "BUTTON" || btn.tagName === "A") {
        if (!btn.dataset.oldText) btn.dataset.oldText = btn.textContent;
        btn.textContent = "✓ Скопировано";
        clearTimeout(btn._copyTimer);
        btn._copyTimer = setTimeout(() => { btn.textContent = btn.dataset.oldText; }, 1500);
      } else {
        showCopyToast("Скопировано: " + text);
      }
    }
  } catch (e) {
    // буфер обмена недоступен — оставляем как есть
  }
}

function wireCopyButtons() {
  detailEl.querySelectorAll("[data-copy]").forEach(btn => {
    btn.addEventListener("click", () => copyText(btn.dataset.copy, btn));
    if (btn.tagName !== "BUTTON" && btn.tagName !== "A") {
      btn.setAttribute("role", "button");
      btn.setAttribute("tabindex", "0");
      btn.addEventListener("keydown", e => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          copyText(btn.dataset.copy, btn);
        }
      });
    }
  });
}

/* ---------- карточки ---------- */

function scheduleCard(o) {
  const cls = gameClass(o.event?.game);
  const si = sessionInfo(o.event?.session);
  const qty = o.event?.qty ? `${esc(o.event.qty)} чел.` : "";
  const name = esc(o.customer?.name || "Без имени");
  const price = rub(o);
  const phone = normPhone(o.customer?.phone);
  return `
    <article class="sch-card card-${cls}" data-id="${esc(o.order_id)}">
      <div class="sch-row1">
        <span class="sch-period">${esc(si.period)}</span>
        <span class="sch-game">${esc(o.event?.game || "Игра не указана")}</span>
        <span class="sch-price">${price}</span>
      </div>
      <div class="sch-row2">
        <span class="sch-qty">${qty}</span>
        <span class="sch-name">${name}</span>
        ${phone ? `<a class="sch-phone" href="tel:${esc(phoneLink(o.customer.phone))}">📞</a>` : ""}
      </div>
      <div class="sch-row3">${esc(si.time)} · ${esc(statusOrAmount(o))}</div>
    </article>
  `;
}

function orderCard(o) {
  return `
    <article class="card" data-id="${esc(o.order_id)}">
      <div class="topline">
        <div class="date">📅 ${esc(formatEventDate(o.event?.date) || "Дата не указана")}</div>
        <div class="${paid(o) && o.payment?.amount != null ? "sum-pill" : "status"}">${esc(statusOrAmount(o))}</div>
      </div>
      <div class="card-mainline">
        <div class="name">${esc(o.customer?.name || "Без имени")}</div>
        ${o.event?.qty ? `<div class="players-count">👥 <span>${esc(o.event.qty)}</span></div>` : ""}
      </div>
      <div class="meta">
        🕒 ${esc(o.event?.session ? sessionLabel(o.event.session) : "Сеанс не указан")}
      </div>
      ${o.event?.game ? `<div class="game">🎯 ${esc(o.event.game)}</div>` : ""}
      ${o.event?.tent ? `<div class="meta">🏕 ${esc(o.event.tent)}</div>` : ""}
      ${o.received_at ? `<div class="received-at">Поступило: ${esc(formatReceivedAt(o.received_at))}</div>` : ""}
    </article>
  `;
}

/* ---------- детали ---------- */

/* БСО в карточке заказа: появляется сам, когда бланк уже заведён */
async function loadOrderBso(orderId) {
  const slot = document.getElementById("orderBsoSlot");
  if (!slot) return;
  try {
    const r = await fetch(`/api/orders/${encodeURIComponent(orderId)}/bso`, {cache: "no-store", headers: authHeaders()});
    if (!r.ok) return;
    const b = (await r.json()).bso;
    if (!b) return;
    slot.hidden = false;
    slot.innerHTML = `
      <div class="calls-heading">БСО</div>
      <div class="bso-inline">
        <div class="bso-inline-head">
          <span class="bso-inline-num">БСО № ${esc(b.bso_number || "—")}</span>
          <span class="bso-inline-sum">${fmtMoney(b.order_amount)}</span>
        </div>
        <div class="bso-row"><span>Факт игроков</span><span>${esc(b.players_fact ?? "—")}</span></div>
        <div class="bso-row"><span>Зона отдыха</span><span>${fmtMoney(b.rest_zone_amount)}</span></div>
        <div class="bso-row"><span>Дата игры</span><span>${esc(formatEventDate(b.game_date) || "—")}</span></div>
      </div>`;
  } catch (e) { /* нет данных — блок не показываем */ }
}

async function openOrder(o) {
  if (!state.clients.length) {
    await loadClientsData().catch(() => {});
  }
  const phone = normPhone(o.customer?.phone);
  const client = phone ? state.clients.find(c => normPhone(c.phone) === phone) : null;
  if (client) { openClientCard(client.client_id); }
  else { openDetail(o); }
}

async function openDetail(o) {
  const c = o.customer || {};
  const e = o.event || {};
  const p = o.payment || {};
  const sum = paid(o) && p.amount != null ? rub(o) : "";

  detailEl.innerHTML = `
    <div class="detail-title">${esc(c.name || "Заказ")}</div>
    <div class="detail-subtitle">Карточка заказа</div>
    <div class="detail-status">
      ${sum ? `<span class="amount-pill">${esc(sum)}</span>` : `<span class="status">${esc(o.status || "—")}</span>`}
      ${p.transaction_id ? `<span class="txn-id">Номер транзакции ${esc(p.transaction_id)}</span>` : ""}
    </div>

    <div class="key-block">
      <div>
        <div class="key-label">Дата</div>
        <div class="key-value">${esc(formatEventDate(e.date) || "—")}</div>
      </div>
      <div>
        <div class="key-label">Сеанс</div>
        <div class="key-value">${esc(sessionLabel(e.session))}</div>
      </div>
      ${e.qty ? `<div>
        <div class="key-label">Игроков</div>
        <div class="key-qty">${esc(e.qty)}</div>
      </div>` : ""}
      <div>
        <div class="key-label">Тариф</div>
        <div class="key-value">${esc(e.game || "—")}</div>
      </div>
    </div>

    <div class="grid">
      <div class="item item-copy" data-copy="${esc(o.order_id)}"><div class="label">Заказ</div><div class="value">${esc(o.order_id)}</div></div>
      <div class="item"><div class="label">Размещение</div><div class="value">${esc(e.tent || "—")}</div></div>
    </div>

    <div class="actions">
      ${c.phone ? `<button class="action" type="button" data-copy="${esc(phoneLink(c.phone))}">📞 ${esc(phonePretty(c.phone))}</button>` : ""}
      ${c.email ? `<button class="action action-ghost" type="button" data-copy="${esc(c.email)}">✉️ ${esc(c.email)}</button>` : ""}
    </div>

    <section class="bso-in-order" id="orderBsoSlot" hidden></section>

    <section class="calls-section">
      <div class="calls-heading">Звонки</div>
      <div id="callsList" class="calls-list"><div class="empty">Загрузка звонков…</div></div>
    </section>
  `;
  dialog.showModal();
  wireCopyButtons();
  loadOrderBso(o.order_id);

  try {
    const r = await fetch(`/api/orders/${encodeURIComponent(o.order_id)}/calls`, {cache:"no-store", headers: authHeaders()});
    if (!r.ok) throw new Error("HTTP " + r.status);
    const data = await r.json();
    const calls = data.calls || [];
    const list = document.getElementById("callsList");
    if (!calls.length) {
      list.innerHTML = `<div class="empty">Звонков пока нет</div>`;
      return;
    }
    list.innerHTML = calls.map(callCard).join("");
    initCallCards(list);
  } catch (err) {
    const list = document.getElementById("callsList");
    if (list) list.innerHTML = `<div class="empty">Не удалось загрузить звонки: ${esc(err.message)}</div>`;
  }
}

async function openClientCard(clientId) {
  const client = state.clients.find(c => String(c.client_id) === String(clientId));
  if (!client) {
    detailEl.innerHTML = `<div class="detail-title">Клиент не найден</div>`;
    dialog.showModal();
    return;
  }

  const phone = normPhone(client.phone);
  const orders = state.orders
    .filter(o => phone && normPhone(o.customer?.phone) === phone)
    .sort((a, b) => String(b.event?.date || "").localeCompare(String(a.event?.date || "")));

  detailEl.innerHTML = `
    <div class="detail-title">${esc(client.name || "Без имени")}${client.client_id != null ? `<span class="client-id">#${esc(client.client_id)}</span>` : ""}</div>
    <div class="detail-subtitle">Карточка клиента</div>

    <div class="actions">
      ${client.phone ? `<button class="action" type="button" data-copy="${esc(phoneLink(client.phone))}">📞 ${esc(phonePretty(client.phone))}</button>` : ""}
      ${client.email ? `<button class="action" type="button" data-copy="${esc(client.email)}">✉️ ${esc(client.email)}</button>` : ""}
    </div>

    <section class="calls-section">
      <div class="calls-heading">Заказы (${orders.length})</div>
      <div id="clientOrders" class="orders-mini"></div>
    </section>

    <section class="calls-section">
      <div class="calls-heading">Звонки</div>
      <div id="callsList" class="calls-list"><div class="empty">Загрузка звонков…</div></div>
    </section>
  `;
  dialog.showModal();
  wireCopyButtons();

  const ordersBox = document.getElementById("clientOrders");
  if (orders.length) {
    ordersBox.innerHTML = orders.map(o => `
      <article class="order-mini" data-id="${esc(o.order_id)}">
        <div class="order-mini-top">
          <span class="order-mini-id">${esc(o.order_id)}</span>
          <span class="order-mini-date">${esc(formatEventDate(o.event?.date) || "—")}</span>
        </div>
      </article>
    `).join("");
    ordersBox.querySelectorAll(".order-mini").forEach(el => {
      el.addEventListener("click", () => {
        const o = state.orders.find(x => String(x.order_id) === el.dataset.id);
        if (o) openDetail(o);
      });
    });
  } else {
    ordersBox.innerHTML = `<div class="empty">Заказов нет</div>`;
  }

  try {
    const r = await fetch(`/api/clients/${encodeURIComponent(clientId)}/calls`, {cache:"no-store", headers: authHeaders()});
    if (!r.ok) throw new Error("HTTP " + r.status);
    const data = await r.json();
    const calls = data.calls || [];
    const list = document.getElementById("callsList");
    if (!calls.length) { list.innerHTML = `<div class="empty">Звонков нет</div>`; return; }
    list.innerHTML = calls.map(callCard).join("");
    initCallCards(list);
  } catch (err) {
    const list = document.getElementById("callsList");
    if (list) list.innerHTML = `<div class="empty">Не удалось загрузить звонки: ${esc(err.message)}</div>`;
  }
}

/* ---------- экран «Расписание» ---------- */

/* склонение числительных: 1 игра / 2 игры / 6 игр */
function plural(n, one, few, many) {
  const n10 = n % 10, n100 = n % 100;
  if (n10 === 1 && n100 !== 11) return one;
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return few;
  return many;
}

function renderWeek(d) {
  const mon = mondayOf(d);
  const sel = isoDate(d);
  const strip = document.getElementById("weekStrip");
  let html = `<button class="week-arrow" data-shift="-7" aria-label="Предыдущая неделя">‹</button>`;
  for (let i = 0; i < 7; i++) {
    const day = addDays(mon, i);
    const ds = isoDate(day);
    const has = dayHasOrders(ds);
    const active = ds === sel;
    const today = ds === isoDate(new Date());
    html += `
      <button class="week-day${active ? " active" : ""}${today ? " today" : ""}" data-date="${ds}">
        <span class="week-dow">${WEEKDAYS_RU[day.getDay()]}</span>
        <span class="week-num">${day.getDate()}</span>
        <span class="week-dot${has ? " has" : ""}">${has ? "●" : ""}</span>
      </button>`;
  }
  html += `<button class="week-arrow" data-shift="7" aria-label="Следующая неделя">›</button>`;
  strip.innerHTML = html;

  strip.querySelectorAll(".week-day").forEach(btn => {
    btn.addEventListener("click", () => selectDay(btn.dataset.date));
  });
  strip.querySelectorAll(".week-arrow").forEach(btn => {
    btn.addEventListener("click", () => {
      state.selectedDate = addDays(state.selectedDate || new Date(), Number(btn.dataset.shift));
      renderSchedule();
    });
  });
}

function selectDay(dateStr) {
  const [y, m, dd] = dateStr.split("-").map(Number);
  state.selectedDate = new Date(y, m - 1, dd);
  renderSchedule();
}

function shiftMonth(delta) {
  const d = state.selectedDate || new Date();
  const target = new Date(d.getFullYear(), d.getMonth() + delta, 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  const day = Math.min(d.getDate(), lastDay);
  state.selectedDate = new Date(target.getFullYear(), target.getMonth(), day);
  renderSchedule();
}

function renderSchedule() {
  const d = state.selectedDate || new Date();

  document.getElementById("monthLabel").textContent = `${MONTHS_RU[d.getMonth()]} ${d.getFullYear()}`;
  renderWeek(d);

  const dayInfo = document.getElementById("dayInfo");
  const dayList = ordersOn(isoDate(d));
  const games = dayList.length;
  const people = dayList.reduce((sum, o) => {
    const n = parseInt(String(o.event?.qty ?? "").trim(), 10);
    return sum + (Number.isFinite(n) ? n : 0);
  }, 0);
  dayInfo.innerHTML = games ? `
    <div class="day-info-title">${esc(fmtDayLong(d))}</div>
    <div class="day-stats">
      <div class="day-stat"><span class="day-stat-ico">🎯</span><span class="day-stat-num">${games}</span><span class="day-stat-cap">${plural(games, "игра", "игры", "игр")}</span></div>
      <div class="day-stat"><span class="day-stat-ico">👥</span><span class="day-stat-num">${people}</span><span class="day-stat-cap">${plural(people, "человек", "человека", "человек")}</span></div>
    </div>
  ` : `
    <div class="day-info-title">${esc(fmtDayLong(d))}</div>
    <div class="day-info-body">На этот день записей нет</div>
  `;

  const list = sortOrders(dayList);
  const box = document.getElementById("scheduleList");
  if (!list.length) {
    box.innerHTML = `<div class="empty">На этот день записей нет</div>`;
    return;
  }
  box.innerHTML = list.map(scheduleCard).join("");
  box.querySelectorAll(".sch-card").forEach(card => {
    card.addEventListener("click", () => {
      const o = state.orders.find(x => String(x.order_id) === card.dataset.id);
      if (o) openDetail(o);
    });
  });
}

/* ---------- экраны «Заказы» / «Клиенты» / «Звонки» ---------- */

const CAL_DOW = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

function todayMsk() {
  return mskDate(new Date().toISOString());
}

function monthKeyOf(iso) {
  return String(iso || "").slice(0, 7);
}

function monthTitle(mk) {
  const parts = String(mk || "").split("-");
  if (parts.length < 2) return String(mk || "");
  return `${MONTHS_RU[Number(parts[1]) - 1]} ${parts[0]}`;
}

function receiptCounts() {
  const counts = {};
  state.orders.forEach(o => {
    const d = mskDate(o.received_at);
    if (d) counts[d] = (counts[d] || 0) + 1;
  });
  return counts;
}

function receiptDates(list) {
  const set = new Set();
  list.forEach(o => { const d = mskDate(o.received_at); if (d) set.add(d); });
  return [...set].sort().reverse();
}

function renderOrdersCalendar() {
  const wrap = document.getElementById("ordersCalendar");
  if (!wrap) return;
  if (state.ordersFilter !== "date") {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  if (!state.ordersMonth) state.ordersMonth = monthKeyOf(latestReceiptDay() || todayMsk());

  const parts = state.ordersMonth.split("-").map(Number);
  const year = parts[0], month = parts[1];
  const firstDow = (new Date(year, month - 1, 1).getDay() + 6) % 7; // неделя с понедельника
  const daysInMonth = new Date(year, month, 0).getDate();
  const counts = receiptCounts();
  const todayIso = todayMsk();

  let cells = "";
  for (let i = 0; i < firstDow; i++) cells += '<span class="cal-day off empty"></span>';
  for (let day = 1; day <= daysInMonth; day++) {
    const ds = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const n = counts[ds] || 0;
    const cls = ["cal-day"];
    if (!n) cls.push("off");
    if (ds === state.ordersDate) cls.push("active");
    if (ds === todayIso) cls.push("today");
    cells += `<button class="${cls.join(" ")}"${n ? ` data-date="${ds}"` : " disabled"}><span class="cal-num">${day}</span><span class="cal-dot${n ? " has" : ""}"></span></button>`;
  }

  const canNext = state.ordersMonth < monthKeyOf(todayMsk());
  wrap.innerHTML = `
    <div class="cal-head">
      <button class="month-arrow" data-cal="prev" aria-label="Предыдущий месяц">\u2039</button>
      <div class="month-label">${esc(monthTitle(state.ordersMonth))}</div>
      <button class="month-arrow" data-cal="next" aria-label="Следующий месяц"${canNext ? "" : " disabled"}>\u203A</button>
    </div>
    <div class="cal-dow">${CAL_DOW.map(t => `<span>${t}</span>`).join("")}</div>
    <div class="cal-grid">${cells}</div>`;

  wrap.querySelector('[data-cal="prev"]').addEventListener("click", () => shiftOrdersMonth(-1));
  const next = wrap.querySelector('[data-cal="next"]');
  if (next && !next.disabled) next.addEventListener("click", () => shiftOrdersMonth(1));
  wrap.querySelectorAll(".cal-day[data-date]").forEach(btn => {
    btn.addEventListener("click", () => {
      state.ordersDate = btn.dataset.date;
      renderOrders();
    });
  });
}

function shiftOrdersMonth(delta) {
  const parts = String(state.ordersMonth || "").split("-").map(Number);
  const d = new Date(parts[0], parts[1] - 1 + delta, 1);
  const mk = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  if (mk > monthKeyOf(todayMsk())) return; // вперёд не листаем: оплату вперёд не получают
  state.ordersMonth = mk;
  // Только календарь: renderOrders() заново выставил бы месяц по выбранной дате и стрелка бы «не нажалась».
  renderOrdersCalendar();
}

function renderOrders() {
  const box = document.getElementById("ordersList");
  const summary = document.getElementById("ordersSummary");
  let list = sortByReceipt(state.orders);
  let summaryText = "";

  if (state.ordersFilter === "date") {
    const days = receiptDates(state.orders);
    if (!state.ordersDate || days.indexOf(state.ordersDate) === -1) state.ordersDate = days[0] || "";
    state.ordersMonth = monthKeyOf(state.ordersDate) || state.ordersMonth;
    list = list.filter(o => mskDate(o.received_at) === state.ordersDate);
    summaryText = `Предоплаты за ${formatReceiptDay(state.ordersDate)}: ${list.length}`;
    renderOrdersCalendar();
  } else {
    const mk = monthKeyOf(todayMsk());
    state.ordersMonth = mk;
    list = list.filter(o => monthKeyOf(mskDate(o.received_at)) === mk);
    summaryText = list.length
      ? `Ближайшие: ${list.length} за ${monthTitle(mk).toLowerCase()}`
      : `За ${monthTitle(mk).toLowerCase()} предоплат пока нет`;
    renderOrdersCalendar();
  }

  summary.textContent = summaryText;

  if (!list.length) {
    box.innerHTML = state.ordersFilter === "date" ? `<div class="empty">Заказов не найдено</div>` : "";
    return;
  }

  box.innerHTML = list.map(orderCard).join("");
  box.querySelectorAll(".card").forEach(card => {
    card.addEventListener("click", () => {
      const o = state.orders.find(x => String(x.order_id) === card.dataset.id);
      if (o) openDetail(o); // карточка заказа (как в расписании), не карточка клиента
    });
  });
}

function renderClients() {
  const box = document.getElementById("clientsList");
  const summary = document.getElementById("clientsSummary");
  const clients = state.clients;
  if (!clients.length) {
    box.innerHTML = `<div class="empty">Клиентов нет</div>`;
    summary.textContent = "Клиентов нет";
    return;
  }
  summary.textContent = `Клиентов: ${clients.length}`;
  box.innerHTML = clients.map(c => `
    <article class="card" data-cid="${esc(c.client_id)}">
      <div class="card-mainline"><div class="name">${esc(c.name || "Без имени")}</div></div>
      <div class="meta">📞 ${esc(c.phone || "—")} · заказов: ${esc(c.orders_count ?? 0)} · звонков: ${esc(c.calls_count ?? 0)}</div>
      ${c.last_call_at ? `<div class="meta">🕒 Последний звонок: ${esc(formatCallDatetime(c.last_call_at))}</div>` : ""}
    </article>
  `).join("");
  box.querySelectorAll(".card").forEach(card => {
    card.addEventListener("click", () => openClientCard(card.dataset.cid));
  });
}

function callsDateLabel() {
  const todayIso = isoDate(new Date());
  return state.callsDate === todayIso ? "сегодня" : (formatEventDate(state.callsDate) || state.callsDate);
}

function renderCallsToday() {
  const box = document.getElementById("callsTodayList");
  const summary = document.getElementById("callsSummary");
  const calls = state.callsToday || [];
  const label = callsDateLabel();
  if (!calls.length) {
    summary.textContent = `Звонков за ${label}: 0`;
    box.innerHTML = `<div class="empty">Звонков за ${label} нет</div>`;
    return;
  }
  summary.textContent = `Звонков за ${label}: ${calls.length}`;
  box.innerHTML = calls.map((c, i) => callCard(c, { showClient: true, index: i })).join("");
  initCallCards(box);
  box.querySelectorAll(".call-card").forEach(card => {
    card.addEventListener("click", () => {
      const call = calls[Number(card.dataset.callIndex)];
      if (!call) return;
      const info = callClientInfo(call);
      if (info.client) openClientCard(info.client.client_id);
      else if (info.order) openDetail(info.order);
    });
  });
}

/* ---------- карточки БСО ---------- */

function bsoCard(b) {
  const pay = Number(b.payment_amount) || 0;
  const amt = Number(b.order_amount) || 0;
  const total = Math.round((pay + amt) * 100) / 100;
  const name = b.order_customer_name || b.customer_name || "Без имени";
  const nameEl = b.client_id != null
    ? `<button class="bso-client" type="button" data-client-id="${esc(b.client_id)}">👤 ${esc(name)}</button>`
    : `<div class="bso-client">👤 ${esc(name)}</div>`;
  return `
    <article class="bso-card">
      <button class="bso-toggle" type="button" aria-expanded="false">
        <div class="bso-toggle-main">
          <div class="bso-toggle-title">БСО № ${esc(b.bso_number || "—")}</div>
          <div class="bso-toggle-date">${esc(formatEventDate(b.game_date) || "—")}</div>
        </div>
        <div class="bso-toggle-total">${fmtMoney(total)}</div>
        <span class="bso-chevron">▾</span>
      </button>
      <div class="bso-body" hidden>
        ${nameEl}
        <div class="bso-details">
          <div class="bso-row"><span>Заказ</span><span>${esc(b.order_id || "—")}</span></div>
          <div class="bso-row"><span>Игроков (факт)</span><span>${esc(b.players_fact ?? "—")}</span></div>
          <div class="bso-row"><span>Зона отдыха</span><span>${fmtMoney(b.rest_zone_amount)}</span></div>
        </div>
        <div class="bso-foot">
          <div class="bso-row"><span>Бронь</span><span>${fmtMoney(b.payment_amount)}</span></div>
          <div class="bso-row"><span>Сумма заказа</span><span>${fmtMoney(b.order_amount)}</span></div>
          <div class="bso-row bso-grand"><span>Итого</span><span>${fmtMoney(pay)} + ${fmtMoney(amt)} = ${fmtMoney(total)}</span></div>
        </div>
      </div>
    </article>
  `;
}

function renderBsoDateStrip() {
  const wrap = document.getElementById("bsoDateStrip");
  if (!wrap) return;
  if (state.bsoFilter !== "date") {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  function onChange(ds) {
    state.bsoDate = ds;
    renderBso();
  }
  renderDayStrip(wrap, state.bsoDate, onChange);
}

function renderBso() {
  const box = document.getElementById("bsoList");
  const summary = document.getElementById("bsoSummary");
  renderBsoDateStrip();
  let list = state.bso;
  const byDate = state.bsoFilter === "date" && state.bsoDate;
  if (byDate) {
    list = list.filter(b => String(b.game_date || "").slice(0, 10) === state.bsoDate);
  }
  if (!list.length) {
    summary.textContent = "БСО нет";
    box.innerHTML = `<div class="empty">БСО пока нет</div>`;
    return;
  }
  summary.textContent = byDate
    ? `БСО за ${formatEventDate(state.bsoDate)}: ${list.length}`
    : `БСО: ${list.length}`;
  box.innerHTML = list.map(bsoCard).join("");
  box.querySelectorAll(".bso-toggle").forEach(btn => {
    btn.addEventListener("click", () => {
      const card = btn.closest(".bso-card");
      const body = card.querySelector(".bso-body");
      const expanded = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", String(!expanded));
      body.hidden = expanded;
    });
  });
  box.querySelectorAll(".bso-client[data-client-id]").forEach(btn => {
    btn.addEventListener("click", () => openClientCard(btn.dataset.clientId));
  });
}

/* ---------- навигация ---------- */

function show(view) {
  state.view = view;
  Object.entries(VIEW_SECTIONS).forEach(([k, id]) => {
    const el = document.getElementById(id);
    if (el) el.hidden = (k !== view);
  });
  const nav = document.getElementById("bottomNav");
  nav.hidden = (view === "start");
  document.querySelectorAll(".nav-item[data-go]").forEach(b => {
    b.classList.toggle("active", b.dataset.go === view);
  });
  const navMore = document.getElementById("navMore");
  if (navMore) navMore.classList.toggle("active", view === "clients" || view === "bso");
  const moreMenu = document.getElementById("moreMenu");
  if (moreMenu) moreMenu.hidden = true;

  if (view === "schedule") renderSchedule();
  else if (view === "clients") renderClients();
  else if (view === "orders") renderOrders();
  else if (view === "calls") { renderCallsScreen(); }
  else if (view === "bso") renderBso();
  window.scrollTo(0, 0);
}

/* ---------- загрузка данных ---------- */

async function loadClientsData() {
  const r = await fetch("/api/clients?limit=500", {cache:"no-store", headers: authHeaders()});
  if (!r.ok) throw new Error("HTTP " + r.status);
  const data = await r.json();
  state.clients = data.clients || [];
}

async function loadOrdersData() {
  const r = await fetch("/api/orders?limit=200", {cache:"no-store", headers: authHeaders()});
  if (!r.ok) throw new Error("HTTP " + r.status);
  const data = await r.json();
  state.orders = data.orders || [];
}

async function loadBsoData() {
  const r = await fetch("/api/bso?limit=500", {cache:"no-store", headers: authHeaders()});
  if (!r.ok) throw new Error("HTTP " + r.status);
  const data = await r.json();
  state.bso = data.bso || [];
}

async function loadCallsForDate(dateStr) {
  const box = document.getElementById("callsTodayList");
  const summary = document.getElementById("callsSummary");
  summary.textContent = "Загрузка звонков…";
  box.innerHTML = `<div class="empty">Загрузка звонков…</div>`;
  try {
    const q = dateStr ? `?date=${encodeURIComponent(dateStr)}` : "";
    const r = await fetch(`/api/calls/today${q}`, {cache:"no-store", headers: authHeaders()});
    if (!r.ok) throw new Error("HTTP " + r.status);
    const data = await r.json();
    state.callsToday = data.calls || [];
    renderCallsToday();
  } catch (e) {
    summary.textContent = "Ошибка загрузки";
    box.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

function renderCallsScreen() {
  const strip = document.getElementById("callsDateStrip");
  function onChange(ds) {
    state.callsDate = ds;
    renderDayStrip(strip, state.callsDate, onChange);
    loadCallsForDate(ds);
  }
  renderDayStrip(strip, state.callsDate, onChange);
  loadCallsForDate(state.callsDate);
}

function loadWeekendSummary() {
  const el = document.getElementById("weekendCount");
  if (!el) return;
  try {
    fetch("/api/summary/weekend", {cache:"no-store", headers: authHeaders()})
      .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(data => { el.textContent = Number(data.people || 0).toLocaleString("ru-RU"); })
      .catch(() => { el.textContent = "—"; });
  } catch (e) {
    el.textContent = "—";
  }
}

async function init() {
  const now = new Date();
  state.selectedDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  state.callsDate = isoDate(new Date());

  await Promise.all([
    loadOrdersData().catch(() => {}),
    loadClientsData().catch(() => {}),
    loadBsoData().catch(() => {}),
  ]);
  loadWeekendSummary();

  if (state.view !== "start") show(state.view);
}

/* ---------- события ---------- */

document.querySelectorAll("[data-go]").forEach(btn => {
  btn.addEventListener("click", () => show(btn.dataset.go));
});

const navMore = document.getElementById("navMore");
const moreMenu = document.getElementById("moreMenu");
if (navMore && moreMenu) {
  navMore.addEventListener("click", (e) => {
    e.stopPropagation();
    moreMenu.hidden = !moreMenu.hidden;
  });
  document.addEventListener("click", (e) => {
    if (!moreMenu.hidden && !moreMenu.contains(e.target) && e.target !== navMore) {
      moreMenu.hidden = true;
    }
  });
}

document.getElementById("prevMonth").addEventListener("click", () => shiftMonth(-1));
document.getElementById("nextMonth").addEventListener("click", () => shiftMonth(1));

document.querySelectorAll("#ordersFilterRow .chip").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#ordersFilterRow .chip").forEach(x => x.classList.remove("active"));
    btn.classList.add("active");
    state.ordersFilter = btn.dataset.ofilter;
    renderOrders();
  });
});

document.querySelectorAll("#bsoFilterRow .chip").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#bsoFilterRow .chip").forEach(x => x.classList.remove("active"));
    btn.classList.add("active");
    state.bsoFilter = btn.dataset.bsofilter;
    if (state.bsoFilter === "date" && !state.bsoDate) state.bsoDate = isoDate(new Date());
    renderBso();
  });
});

document.getElementById("closeDialog").addEventListener("click", () => dialog.close());
dialog.addEventListener("click", e => { if (e.target === dialog) dialog.close(); });

init();
