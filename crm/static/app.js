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
  ordersFilter: "upcoming",
  ordersDate: null,
  selectedDate: null,
  dayPeriod: "morning", // визуальный переключатель (без фильтрации)
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

function money(o) {
  if (o.payment?.amount == null) return "—";
  return Number(o.payment.amount).toLocaleString("ru-RU") + " " +
         (o.payment.currency || "RUB");
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

function formatReceivedAt(value) {
  if (!value) return "";
  const m = String(value).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (m) return `${m[3]}.${m[2]}.${m[1].slice(-2)} · ${m[4]}:${m[5]}`;
  return String(value);
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

function isUpcoming(o) {
  if (!o.event?.date) return false;
  const text = String(o.event.date);
  let d;
  let m = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) {
    d = new Date(+m[1], +m[2]-1, +m[3]);
  } else {
    m = text.match(/^(\d{2})\.(\d{2})\.(\d{4})/);
    if (!m) return true;
    d = new Date(+m[3], +m[2]-1, +m[1]);
  }
  const today = new Date();
  today.setHours(0,0,0,0);
  const end = new Date(today);
  end.setDate(end.getDate()+14);
  return d >= today && d <= end;
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
      ${call.audio_url ? `<audio class="call-audio" controls preload="none" src="${esc(call.audio_url)}"></audio>` : `<div class="call-unavailable">MP3 недоступен</div>`}
    </article>
  `;
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
      const old = btn.textContent;
      btn.textContent = "✓ Скопировано";
      setTimeout(() => { btn.textContent = old; }, 1500);
    }
  } catch (e) {
    // буфер обмена недоступен — оставляем как есть
  }
}

function wireCopyButtons() {
  detailEl.querySelectorAll("[data-copy]").forEach(btn => {
    btn.addEventListener("click", () => copyText(btn.dataset.copy, btn));
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
      <div class="sch-row3">${esc(si.time)} · ${esc(o.status || "—")}</div>
    </article>
  `;
}

function orderCard(o) {
  return `
    <article class="card" data-id="${esc(o.order_id)}">
      <div class="topline">
        <div class="date">📅 ${esc(formatEventDate(o.event?.date) || "Дата не указана")}</div>
        <div class="status">${esc(o.status || "—")}${paid(o) && o.payment?.amount != null ? ` · ${esc(money(o))}` : ""}</div>
      </div>
      <div class="card-mainline">
        <div class="name">${esc(o.customer?.name || "Без имени")}</div>
        ${o.event?.qty ? `<div class="players-count">👥 <span>${esc(o.event.qty)}</span></div>` : ""}
      </div>
      <div class="meta">
        🕒 ${esc(o.event?.session || "Сеанс не указан")}
      </div>
      ${o.event?.game ? `<div class="game">🎯 ${esc(o.event.game)}</div>` : ""}
      ${o.event?.tent ? `<div class="meta">🏕 ${esc(o.event.tent)}</div>` : ""}
      ${o.received_at ? `<div class="received-at">Поступило: ${esc(formatReceivedAt(o.received_at))}</div>` : ""}
    </article>
  `;
}

/* ---------- детали ---------- */

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

  detailEl.innerHTML = `
    <div class="detail-title">${esc(c.name || "Заказ")}</div>
    <div class="detail-status"><span class="status">${esc(o.status || "—")}</span></div>

    <div class="grid">
      <div class="item"><div class="label">Заказ</div><div class="value">#${esc(o.order_id)}</div></div>
      <div class="item"><div class="label">Дата</div><div class="value">${esc(formatEventDate(e.date) || "—")}</div></div>
      <div class="item"><div class="label">Сеанс</div><div class="value">${esc(e.session || "—")}</div></div>
      <div class="item"><div class="label">Игроков</div><div class="value">${esc(e.qty || "—")}</div></div>
      <div class="item"><div class="label">Игра</div><div class="value">${esc(e.game || "—")}</div></div>
      <div class="item"><div class="label">Размещение</div><div class="value">${esc(e.tent || "—")}</div></div>
      <div class="item"><div class="label">Оплата</div><div class="value">${money(o)}</div></div>
      <div class="item"><div class="label">Транзакция</div><div class="value">${esc(p.transaction_id || "—")}</div></div>
    </div>

    <div class="actions">
      ${c.phone ? `<a class="action" href="tel:${esc(phoneLink(c.phone))}">📞 ${esc(phoneLink(c.phone))}</a>` : ""}
      ${c.email ? `<button class="action" type="button" data-copy="${esc(c.email)}">✉️ ${esc(c.email)}</button>` : ""}
    </div>

    <section class="calls-section">
      <div class="calls-heading">Звонки</div>
      <div id="callsList" class="calls-list"><div class="empty">Загрузка звонков…</div></div>
    </section>
  `;
  dialog.showModal();
  wireCopyButtons();

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
      ${client.phone ? `<button class="action" type="button" data-copy="${esc(phoneLink(client.phone))}">📞 ${esc(phoneLink(client.phone))}</button>` : ""}
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
          <span class="order-mini-id">#${esc(o.order_id)}</span>
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
  } catch (err) {
    const list = document.getElementById("callsList");
    if (list) list.innerHTML = `<div class="empty">Не удалось загрузить звонки: ${esc(err.message)}</div>`;
  }
}

/* ---------- экран «Расписание» ---------- */

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
  dayInfo.innerHTML = `
    <div class="day-info-title">${esc(fmtDayLong(d))}</div>
    <div class="day-info-body">Сводка дня появится здесь</div>
  `;

  const list = sortOrders(ordersOn(isoDate(d)));
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

function renderOrdersDateStrip() {
  const wrap = document.getElementById("ordersDateStrip");
  if (!wrap) return;
  if (state.ordersFilter !== "date") {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  function onChange(ds) {
    state.ordersDate = ds;
    renderOrders();
  }
  renderDayStrip(wrap, state.ordersDate, onChange);
}

function renderOrders() {
  const box = document.getElementById("ordersList");
  const summary = document.getElementById("ordersSummary");
  let list = state.orders;
  if (state.ordersFilter === "upcoming") list = list.filter(isUpcoming);
  else if (state.ordersFilter === "date") {
    if (!state.ordersDate) state.ordersDate = isoDate(new Date());
    list = list.filter(o => String(o.event?.date || "").slice(0, 10) === state.ordersDate);
  }
  renderOrdersDateStrip();

  if (state.ordersFilter === "upcoming") {
    summary.textContent = `Ближайшие: ${list.length} из ${state.orders.length}`;
  } else if (state.ordersFilter === "date") {
    summary.textContent = `${formatEventDate(state.ordersDate)}: ${list.length} из ${state.orders.length}`;
  } else {
    summary.textContent = `Все: ${list.length}`;
  }

  if (!list.length) {
    box.innerHTML = `<div class="empty">Заказов не найдено</div>`;
    return;
  }

  box.innerHTML = list.map(orderCard).join("");
  box.querySelectorAll(".card").forEach(card => {
    card.addEventListener("click", () => {
      const o = state.orders.find(x => String(x.order_id) === card.dataset.id);
      if (o) openOrder(o);
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
          <div class="bso-row"><span>Заказ</span><span>#${esc(b.order_id || "—")}</span></div>
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

document.querySelectorAll(".day-seg").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".day-seg").forEach(x => x.classList.remove("active"));
    btn.classList.add("active");
    state.dayPeriod = btn.dataset.period;
  });
});

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
