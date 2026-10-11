#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Собирает статический макет Zarnica CRM mini app (все экраны) в один HTML-файл.

Зачем: файл импортируется в Figma (плагин html.to.design) и служит источником
для SVG-выгрузки по экранам (svg/*.svg), которую Figma открывает без плагинов.

Данные — вымышленные (никаких реальных клиентов).
CSS берётся из боевого crm/static/style.css БЕЗ изменений, поэтому геометрия
и цвета совпадают с приложением; отличия только в блоке «MOCK ONLY» ниже.
"""
import re
import pathlib

ROOT = pathlib.Path("/opt/data/zcminiapp")
OUT = ROOT / "figma"
OUT.mkdir(exist_ok=True)

W, H = 390, 844
VERSION = (ROOT / "VERSION").read_text().strip() if (ROOT / "VERSION").exists() else "?"

# --------------------------------------------------------------------------
# данные макета (вымышленные)
# --------------------------------------------------------------------------

def rub(n):
    s = f"{n:,}".replace(",", "\u00a0")
    return f"{s} ₽"


ORDERS = [
    dict(order_id="10428", status="paid", amount=23400, txn="4f1c-8a72-2b90",
         name="Королёва Мария", phone="+7 (912) 345-67-89", email="koroleva.m@example.com",
         date="2026-10-10", game="Пейнтбол «Штурм»", tent="Беседка №3",
         session="- Утренний с 9:00 до 14:45;", qty="12", recv="05.10.26 · 14:24",
         recv_iso="2026-10-05"),
    dict(order_id="10427", status="paid", amount=15800, txn="77aa-31de-90c4",
         name="Гаврилов Артём", phone="+7 (903) 118-22-04", email="gavrilov@example.com",
         date="2026-10-10", game="Лазертаг «Цитадель»", tent="Шатёр №1",
         session="- Вечерний с 15:15 до 21:00;", qty="8", recv="05.10.26 · 12:07",
         recv_iso="2026-10-05"),
    dict(order_id="10426", status="new", amount=None, txn=None,
         name="Ерёмина Ольга", phone="+7 (921) 447-90-13", email=None,
         date="2026-10-11", game="Кидбол «Малыш»", tent=None,
         session="- Утренний с 9:00 до 14:45;", qty="6", recv="05.10.26 · 10:41",
         recv_iso="2026-10-05"),
    dict(order_id="10425", status="paid", amount=31200, txn="c920-5f6b-1188",
         name="Северов Илья", phone="+7 (911) 208-77-31", email="severov.i@example.com",
         date="2026-10-12", game="Пейнтбол «Штурм»", tent="Беседка №2",
         session="- Вечерний с 15:15 до 21:00;", qty="16", recv="04.10.26 · 19:52",
         recv_iso="2026-10-04"),
    dict(order_id="10424", status="paid", amount=9750, txn="1bd4-77aa-6620",
         name="Титова Алина", phone="+7 (900) 305-14-76", email=None,
         date="2026-10-09", game="Лазертаг «Цитадель»", tent=None,
         session="- Утренний с 9:00 до 14:45;", qty="5", recv="04.10.26 · 15:10",
         recv_iso="2026-10-04"),
]

SCHEDULE_DAY = [ORDERS[0], ORDERS[1], ORDERS[2], ORDERS[4]]

CLIENTS = [
    dict(client_id=1187, name="Королёва Мария", phone="+7 (912) 345-67-89", orders=7, calls=4, last="10.09.26 · 18:12"),
    dict(client_id=1186, name="Гаврилов Артём", phone="+7 (903) 118-22-04", orders=4, calls=2, last="02.10.26 · 11:35"),
    dict(client_id=1179, name="Ерёмина Ольга", phone="+7 (921) 447-90-13", orders=3, calls=1, last="28.09.26 · 16:04"),
    dict(client_id=1174, name="Северов Илья", phone="+7 (911) 208-77-31", orders=9, calls=6, last="04.10.26 · 09:47"),
    dict(client_id=1168, name="Титова Алина", phone="+7 (900) 305-14-76", orders=2, calls=1, last=None),
    dict(client_id=1161, name="Мельников Пётр", phone="+7 (925) 771-03-58", orders=5, calls=3, last="21.09.26 · 20:26"),
]

CALLS = [
    dict(dt="05.10.26 · 14:19", dur=184, client="Королёва Мария", admin="Администратор: Дарья К.", phone="+7 (912) 345-67-89", audio=True),
    dict(dt="05.10.26 · 12:02", dur=96, client="Гаврилов Артём", admin="Администратор: Дарья К.", phone="+7 (903) 118-22-04", audio=True),
    dict(dt="05.10.26 · 10:37", dur=41, client=None, admin="Администратор не указан", phone="+7 (921) 447-90-13", audio=False),
    dict(dt="05.10.26 · 09:58", dur=274, client="Северов Илья", admin="Администратор: Ирина П.", phone="+7 (911) 208-77-31", audio=True),
]

BSO = [
    dict(num="000214", date="10.10.2026", pay=23400, amt=6800, name="Королёва Мария", client_id=1187,
         order="10428", players="13", rest=3400),
    dict(num="000213", date="10.10.2026", pay=15800, amt=0, name="Гаврилов Артём", client_id=1186,
         order="10427", players="8", rest=0),
    dict(num="000212", date="09.10.2026", pay=9750, amt=1200, name="Титова Алина", client_id=1168,
         order="10424", players="5", rest=1200),
]

WEEK = [  # 05.10.2026 = понедельник
    ("Пн", 5, False), ("Вт", 6, False), ("Ср", 7, True), ("Чт", 8, False),
    ("Пт", 9, True), ("Сб", 10, True), ("Вс", 11, True),
]

DAY_STRIP = [  # 05.10.2026 — сегодня
    ("Вс", 4, False), ("Пн", 5, True), ("Вт", 6, False), ("Ср", 7, False), ("Чт", 8, False),
    ("Пт", 9, False), ("Сб", 10, False), ("Вс", 11, False),
]

CAL_DOW = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
# октябрь 2026: 1-е — четверг (смещение 3 от понедельника)
CAL_OFFSET = 3
CAL_DAYS = 31
CAL_ACTIVE = 4  # выбранное число поступлений
CAL_COUNTED = {4, 5}  # дни, где есть предоплаты

# --------------------------------------------------------------------------
# markup-хелперы (повторяют crm/static/app.js)
# --------------------------------------------------------------------------

def session_info(session):
    s = (session or "").lower()
    if "утренн" in s:
        return "Утро", "09:00–14:45"
    if "вечерн" in s:
        return "Вечер", "15:15–21:00"
    return "Сеанс", session or "—"


def session_label(session):
    s = re.sub(r"^[-\s–—•]+", "", (session or "").strip())
    s = re.sub(r"[\s;.]+$", "", s)
    if not s:
        return "—"
    return re.sub(r"\s+с\s+", " · с ", s, flags=re.I)


def game_class(game):
    g = (game or "").lower()
    if "пейнтбол" in g:
        return "paintball"
    if "лазер" in g:
        return "lasertag"
    if "кидбол" in g:
        return "kidball"
    return "other"


def event_date(iso):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", iso or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else ""


def status_or_amount(o):
    if o["status"] == "paid" and o["amount"] is not None:
        return rub(o["amount"])
    return o["status"] or "—"


def schedule_card(o):
    period, time_ = session_info(o["session"])
    qty = f'{o["qty"]} чел.' if o.get("qty") else ""
    return f'''
    <article class="sch-card card-{game_class(o["game"])}">
      <div class="sch-row1">
        <span class="sch-period">{period}</span>
        <span class="sch-game">{o["game"] or "Игра не указана"}</span>
        <span class="sch-price">{rub(o["amount"]) if o["amount"] else "—"}</span>
      </div>
      <div class="sch-row2">
        <span class="sch-qty">{qty}</span>
        <span class="sch-name">{o["name"]}</span>
        <a class="sch-phone">📞</a>
      </div>
      <div class="sch-row3">{time_} · {status_or_amount(o)}</div>
    </article>'''.strip()


def order_card(o):
    paid = o["status"] == "paid" and o["amount"] is not None
    pill = f'<span class="sum-pill">{rub(o["amount"])}</span>' if paid else f'<span class="status">{o["status"]}</span>'
    qty = f'<div class="players-count">👥 <span>{o["qty"]}</span></div>' if o.get("qty") else ""
    tx = f'<div class="game">🎯 {o["game"]}</div>' if o.get("game") else ""
    tent = f'<div class="meta">🏕 {o["tent"]}</div>' if o.get("tent") else ""
    return f'''
    <article class="card">
      <div class="topline">
        <div class="date">📅 {event_date(o["date"]) or "Дата не указана"}</div>
        {pill}
      </div>
      <div class="card-mainline">
        <div class="name">{o["name"] or "Без имени"}</div>
        {qty}
      </div>
      <div class="meta">🕒 {session_label(o["session"])}</div>
      {tx}
      {tent}
      <div class="received-at">Поступило: {o["recv"]}</div>
    </article>'''.strip()


def call_card(c, show_client=False):
    mm, ss = divmod(c["dur"], 60)
    client = f'<div class="call-client">👤 {c["client"]}</div>' if (show_client and c["client"]) else ""
    audio = ('<div class="call-audio-mock">▶  ▍▍▍▍▍▍▍▍▍▍   0:00 / 3:04</div>' if c["audio"]
             else '<div class="call-unavailable">MP3 недоступен</div>')
    return f'''
    <article class="call-card">
      <div class="call-topline">
        <div class="call-date">📞 {c["dt"]}</div>
        <div class="call-duration">{mm}:{ss:02d}</div>
      </div>
      {client}
      <div class="call-admin">{c["admin"]}</div>
      <div class="call-phone">{c["phone"]}</div>
      {audio}
    </article>'''.strip()


def money(n):
    return f"{n:,} ₽".replace(",", "\u00a0") if n else "—"


def bso_card(b, expanded=False):
    total = b["pay"] + b["amt"]
    return f'''
    <article class="bso-card">
      <button class="bso-toggle" aria-expanded="{'true' if expanded else 'false'}">
        <div class="bso-toggle-main">
          <div class="bso-toggle-title">БСО № {b["num"]}</div>
          <div class="bso-toggle-date">{b["date"]}</div>
        </div>
        <div class="bso-toggle-total">{money(total)}</div>
        <span class="bso-chevron">▾</span>
      </button>
      <div class="bso-body"{"" if expanded else " hidden"}>
        <button class="bso-client">👤 {b["name"]}</button>
        <div class="bso-details">
          <div class="bso-row"><span>Заказ</span><span>{b["order"]}</span></div>
          <div class="bso-row"><span>Игроков (факт)</span><span>{b["players"]}</span></div>
          <div class="bso-row"><span>Зона отдыха</span><span>{money(b["rest"])}</span></div>
        </div>
        <div class="bso-foot">
          <div class="bso-row"><span>Бронь</span><span>{money(b["pay"])}</span></div>
          <div class="bso-row"><span>Сумма заказа</span><span>{money(b["amt"])}</span></div>
          <div class="bso-row bso-grand"><span>Итого</span><span>{money(b["pay"])} + {money(b["amt"])} = {money(total)}</span></div>
        </div>
      </div>
    </article>'''.strip()


def bottom_nav(active):
    items = [("schedule", "📅", "Расписание"), ("orders", "📋", "Заказы"),
             ("calls", "📞", "Звонки"), ("more", "•••", "ЕЩЕ")]
    html = '<nav class="bottom-nav">'
    for key, ico, label in items:
        cls = "nav-item active" if key == active else "nav-item"
        html += f'<button class="{cls}"><span class="nav-ico">{ico}</span><span>{label}</span></button>'
    return html + "</nav>"


# --------------------------------------------------------------------------
# экраны
# --------------------------------------------------------------------------

def screen_start():
    return '''
    <section class="screen screen-start">
      <header class="start-header">
        <div class="brand">ЗАРНИЦАКЛАБ</div>
        <h1 class="start-title">CRM</h1>
        <div class="start-sub">mini app</div>
      </header>
      <div class="start-grid">
        <button class="start-btn"><span class="start-ico">📅</span><span>Расписание</span></button>
        <button class="start-btn"><span class="start-ico">👥</span><span>Клиенты</span></button>
        <button class="start-btn"><span class="start-ico">📋</span><span>Заказы</span></button>
        <button class="start-btn"><span class="start-ico">📞</span><span>Звонки</span></button>
        <button class="start-btn start-btn-wide"><span class="start-ico">🧾</span><span>БСО</span></button>
      </div>
    </section>'''


def plural(n, one, few, many):
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and (n100 < 12 or n100 > 14):
        return few
    return many


def screen_schedule(with_records=True, day="Сб, 10 октября", active_num=10, today_num=5):
    week = ""
    for dow, num, has in WEEK:
        cls = "week-day"
        if num == active_num:
            cls += " active"
        if num == today_num:
            cls += " today"
        dot = f'<span class="week-dot has">●</span>'
        week += (f'<button class="{cls}"><span class="week-dow">{dow}</span>'
                 f'<span class="week-num">{num}</span>{dot}</button>')

    if with_records:
        games, people = len(SCHEDULE_DAY), sum(int(o["qty"]) for o in SCHEDULE_DAY)
        day_info = f'''
      <div class="day-info-title">{day}</div>
      <div class="day-stats">
        <div class="day-stat"><span class="day-stat-ico">🎯</span><span class="day-stat-num">{games}</span><span class="day-stat-cap">{plural(games, "игра", "игры", "игр")}</span></div>
        <div class="day-stat"><span class="day-stat-ico">👥</span><span class="day-stat-num">{people}</span><span class="day-stat-cap">{plural(people, "человек", "человека", "человек")}</span></div>
      </div>'''
        cards = '<section class="schedule-list">' + "".join(schedule_card(o) for o in SCHEDULE_DAY) + "</section>"
    else:
        day_info = f'''
      <div class="day-info-title">{day}</div>
      <div class="day-info-body">На этот день записей нет</div>'''
        cards = '<section class="schedule-list"><div class="empty">На этот день записей нет</div></section>'

    return f'''
    <section class="screen">
      <header class="screen-header">
        <div class="header-row">
          <div>
            <div class="brand">ЗАРНИЦАКЛАБ</div>
            <h1>Расписание</h1>
          </div>
          <div class="weekend">
            <div class="weekend-label">Ожидаем в выходные</div>
            <div class="weekend-value">👥 <span>38</span></div>
          </div>
        </div>
      </header>
      <div class="period-row">
        <div class="month-nav">
          <button class="month-arrow">‹</button>
          <button class="month-label">Октябрь 2026</button>
          <button class="month-arrow">›</button>
        </div>
        <button class="icon-btn">☷</button>
        <button class="cta-btn">＋ Новая запись</button>
      </div>
      <div class="week"><button class="week-arrow">‹</button>{week}<button class="week-arrow">›</button></div>
      <div class="day-info">{day_info}</div>
      {cards}
      {bottom_nav("schedule")}
    </section>'''


def screen_clients():
    cards = "".join(f'''
    <article class="card">
      <div class="card-mainline"><div class="name">{c["name"]}</div></div>
      <div class="meta">📞 {c["phone"]} · заказов: {c["orders"]} · звонков: {c["calls"]}</div>
      {f'<div class="meta">🕒 Последний звонок: {c["last"]}</div>' if c["last"] else ""}
    </article>'''.strip() for c in CLIENTS)
    return f'''
    <section class="screen">
      <header class="screen-header">
        <div class="brand">ЗАРНИЦАКЛАБ</div>
        <h1>Клиенты</h1>
      </header>
      <div class="summary">Клиентов: {len(CLIENTS)}</div>
      <section class="orders">{cards}</section>
      {bottom_nav("more")}
    </section>'''


def orders_calendar():
    cells = '<span class="cal-day off empty"></span>' * CAL_OFFSET
    for day in range(1, CAL_DAYS + 1):
        n = day in CAL_COUNTED
        cls = "cal-day" + ("" if n else " off")
        if day == CAL_ACTIVE:
            cls += " active"
        if day == 5:
            cls += " today"
        dot = f'<span class="cal-dot{" has" if n else ""}"></span>'
        cells += f'<button class="{cls}"><span class="cal-num">{day}</span>{dot}</button>'
    return f'''
      <div class="cal-wrap">
        <div class="cal-head">
          <button class="month-arrow">‹</button>
          <div class="month-label">Октябрь 2026</div>
          <button class="month-arrow" disabled>›</button>
        </div>
        <div class="cal-dow">{"".join(f"<span>{d}</span>" for d in CAL_DOW)}</div>
        <div class="cal-grid">{cells}</div>
      </div>'''


def screen_orders(mode="recent"):
    if mode == "recent":
        chips = '<button class="chip active">Ближайшие</button><button class="chip">Найти по дате</button>'
        summary = "Ближайшие: 5 за октябрь"
        list_html = "".join(order_card(o) for o in ORDERS)
        cal = ""
    else:
        chips = '<button class="chip">Ближайшие</button><button class="chip active">Найти по дате</button>'
        summary = "Предоплаты за 04.10.2026, Вс: 2"
        list_html = "".join(order_card(o) for o in ORDERS if o["recv_iso"] == "2026-10-04")
        cal = orders_calendar()
    return f'''
    <section class="screen">
      <header class="screen-header">
        <div class="brand">ЗАРНИЦАКЛАБ</div>
        <h1>Заказы</h1>
      </header>
      <div class="filter-row">{chips}</div>
      {cal}
      <div class="summary">{summary}</div>
      <section class="orders">{list_html}</section>
      {bottom_nav("orders")}
    </section>'''


def screen_calls():
    strip = ""
    for dow, num, active in DAY_STRIP:
        cls = "day-chip" + (" active" if active else "") + (" today" if active else "")
        strip += (f'<button class="{cls}"><span class="day-chip-dow">{dow}</span>'
                  f'<span class="day-chip-num">{num}</span></button>')
    cards = "".join(call_card(c, show_client=True) for c in CALLS)
    return f'''
    <section class="screen">
      <header class="screen-header">
        <div class="brand">ЗАРНИЦАКЛАБ</div>
        <h1>Звонки</h1>
      </header>
      <div class="day-strip-wrap"><div class="day-strip">{strip}</div></div>
      <div class="summary">Звонков за сегодня: {len(CALLS)}</div>
      <section class="orders">{cards}</section>
      {bottom_nav("calls")}
    </section>'''


def screen_bso(mode="all"):
    if mode == "all":
        chips = '<button class="chip active">Все</button><button class="chip">Выбор даты</button>'
        summary = f"БСО: {len(BSO)}"
        strip = ""
        cards = bso_card(BSO[0]) + bso_card(BSO[1]) + bso_card(BSO[2])
    elif mode == "date":
        chips = '<button class="chip">Все</button><button class="chip active">Выбор даты</button>'
        summary = f"БСО за 10.10.2026: 2"
        strip = '<div class="day-strip" style="margin-top:-2px">' + "".join(
            f'<button class="day-chip{" active" if active else ""}"><span class="day-chip-dow">{dow}</span>'
            f'<span class="day-chip-num">{num}</span></button>'
            for dow, num, active in [("Пн", 5, False), ("Вт", 6, False), ("Ср", 7, False), ("Чт", 8, False),
                                     ("Пт", 9, False), ("Сб", 10, True), ("Вс", 11, False), ("Пн", 12, False)]
        ) + "</div>"
        cards = bso_card(BSO[0]) + bso_card(BSO[1])
    else:  # expanded
        chips = '<button class="chip active">Все</button><button class="chip">Выбор даты</button>'
        summary = f"БСО: {len(BSO)}"
        strip = ""
        cards = bso_card(BSO[0], expanded=True) + bso_card(BSO[1])
    wrap = f'<div class="day-strip-wrap">{strip}</div>' if strip else ""
    return f'''
    <section class="screen">
      <header class="screen-header">
        <div class="brand">ЗАРНИЦАКЛАБ</div>
        <h1>БСО</h1>
      </header>
      <div class="filter-row">{chips}</div>
      {wrap}
      <div class="summary">{summary}</div>
      <section class="orders">{cards}</section>
      {bottom_nav("more")}
    </section>'''


def dialog_order():
    o = ORDERS[0]
    body = f'''
    <div class="detail-title">Королёва Мария</div>
    <div class="detail-subtitle">Карточка заказа</div>
    <div class="detail-status">
      <span class="amount-pill">23 400 ₽</span>
      <span class="txn-id">Номер транзакции 4f1c-8a72-2b90</span>
    </div>
    <div class="key-block">
      <div><div class="key-label">Дата</div><div class="key-value">10.10.2026</div></div>
      <div><div class="key-label">Сеанс</div><div class="key-value">Утренний · с 9:00 до 14:45</div></div>
      <div><div class="key-label">Игроков</div><div class="key-qty">12</div></div>
      <div><div class="key-label">Тариф</div><div class="key-value">Пейнтбол «Штурм»</div></div>
    </div>
    <div class="grid">
      <div class="item"><div class="label">Заказ</div><div class="value">10428</div></div>
      <div class="item"><div class="label">Размещение</div><div class="value">Беседка №3</div></div>
    </div>
    <div class="actions">
      <button class="action">📞 +7 (912) 345-67-89</button>
      <button class="action action-ghost">✉️ koroleva.m@example.com</button>
    </div>
    <section class="bso-in-order">
      <div class="calls-heading">БСО</div>
      <div class="bso-inline">
        <div class="bso-inline-head">
          <span class="bso-inline-num">БСО № 000214</span>
          <span class="bso-inline-sum">30 200 ₽</span>
        </div>
        <div class="bso-row"><span>Факт игроков</span><span>13</span></div>
        <div class="bso-row"><span>Зона отдыха</span><span>3 400 ₽</span></div>
        <div class="bso-row"><span>Дата игры</span><span>10.10.2026</span></div>
      </div>
    </section>
    <section class="calls-section">
      <div class="calls-heading">Звонки</div>
      <div class="calls-list">
        {call_card(CALLS[0])}
        {call_card(CALLS[1])}
      </div>
    </section>'''
    return f'<div class="dialog-body"><button class="close">×</button>{body}</div>'


def dialog_client():
    orders = [o for o in ORDERS if o["name"] == "Королёва Мария"] + [ORDERS[3], ORDERS[4]]
    mini = "".join(f'''
      <article class="order-mini">
        <div class="order-mini-top"><span class="order-mini-id">{o["order_id"]}</span>
        <span class="order-mini-date">{event_date(o["date"])}</span></div>
      </article>'''.strip() for o in orders)
    body = f'''
    <div class="detail-title">Королёва Мария<span class="client-id">#1187</span></div>
    <div class="detail-subtitle">Карточка клиента</div>
    <div class="actions">
      <button class="action">📞 +7 (912) 345-67-89</button>
      <button class="action action-ghost">✉️ koroleva.m@example.com</button>
    </div>
    <section class="calls-section">
      <div class="calls-heading">Заказы ({len(orders)})</div>
      <div class="orders-mini">{mini}</div>
    </section>
    <section class="calls-section">
      <div class="calls-heading">Звонки</div>
      <div class="calls-list">{call_card(CALLS[0])}</div>
    </section>'''
    return f'<div class="dialog-body"><button class="close">×</button>{body}</div>'


def more_menu():
    return f'''
    <section class="screen">
      <header class="screen-header">
        <div class="brand">ЗАРНИЦАКЛАБ</div>
        <h1>Заказы</h1>
      </header>
      <div class="filter-row"><button class="chip active">Ближайшие</button><button class="chip">Найти по дате</button></div>
      <div class="summary">Клиентов: {len(CLIENTS)}</div>
      <section class="orders">{order_card(ORDERS[0])}</section>
      <div class="more-menu">
        <button class="more-item"><span class="more-ico">👥</span><span>Клиенты</span></button>
        <button class="more-item"><span class="more-ico">🧾</span><span>БСО</span></button>
      </div>
      {bottom_nav("more")}
    </section>'''


FRAMES = [
    ("01 · Старт", None, screen_start()),
    ("02 · Расписание — день с записями", None, screen_schedule(True)),
    ("03 · Расписание — пустой день (состояние)", None, screen_schedule(False, "Вт, 6 октября", 6, 5)),
    ("04 · Клиенты", None, screen_clients()),
    ("05 · Заказы — Ближайшие", None, screen_orders("recent")),
    ("06 · Заказы — Найти по дате (календарь)", None, screen_orders("date")),
    ("07 · Звонки", None, screen_calls()),
    ("08 · БСО — список", None, screen_bso("all")),
    ("09 · БСО — раскрытая карточка", None, screen_bso("expanded")),
    ("10 · Меню «ЕЩЕ»", None, more_menu()),
    ("11 · Диалог заказа", screen_orders("recent"), dialog_order()),
    ("12 · Диалог клиента", screen_clients(), dialog_client()),
]

CSS = (ROOT / "crm" / "static" / "style.css").read_text()

MOCK_CSS = """
/* ---------- MOCK ONLY: только для макета, в приложении этого нет ---------- */
*{box-sizing:border-box}
body{margin:0;background:#22252b;color:#9aa08f;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.mock-head{padding:26px 30px 6px}
.mock-head h1{margin:0;font-size:22px;letter-spacing:.01em;color:#e8e9e3}
.mock-head .sub{color:#9aa08f;font-size:13px;margin-top:6px;line-height:1.5;max-width:1000px}
.mock-grid{display:flex;flex-wrap:wrap;gap:34px 30px;padding:24px 30px 60px;align-items:flex-start}
.capture{width:390px}
.cap{font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#9aa08f;margin-bottom:10px}
.frame{position:relative;width:390px;height:844px;overflow:hidden;background:#f1f0e9;color:#242720;border-radius:20px;
  box-shadow:0 10px 40px rgba(0,0,0,.35)}
.frame .bottom-nav{position:absolute}
.frame .screen-start{min-height:790px}
.frame .screen[hidden]{display:none}
.mock-dim{position:absolute;left:0;right:0;top:0;bottom:0;background:rgba(0,0,0,.45)}
.mock-modal{position:absolute;left:11px;right:11px;top:12px}
.mock-modal .dialog-body{border-radius:18px}
.call-audio-mock{width:100%;margin-top:10px;background:#e9e8e1;border-radius:8px;padding:7px 10px;
  font-size:12px;color:#6b6e64;letter-spacing:.02em}
"""


def build():
    frames_html = []
    for title, back, markup in FRAMES:
        name = title.split(" · ")[1]
        if back:
            inner = (f'<main class="app">{back}</main>'
                     f'<div class="mock-dim"></div>'
                     f'<div class="mock-modal">{markup}</div>')
        else:
            inner = f'<main class="app">{markup}</main>'
        frames_html.append(
            f'<div class="capture" data-frame="{name}">'
            f'<div class="cap">{title}</div>'
            f'<div class="frame" data-screen="{name}">{inner}</div>'
            f'</div>'
        )
    html = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ЗарницаКлаб CRM — макет для Figma (v{VERSION})</title>
<style>
{CSS}
{MOCK_CSS}
</style>
</head>
<body>
<div class="mock-head">
  <h1>ЗарницаКлаб · CRM mini app — макет v{VERSION}</h1>
  <div class="sub">Все экраны приложения в натуральную величину (390 × 844), данные вымышленные.
  Импорт в Figma: плагин <b>html.to.design</b> (указывает файл/URL) либо файлы из папки <b>svg/</b> (перетащить в Figma).
  CSS взят из боевого crm/static/style.css — цвета, шрифты и отступы совпадают с приложением.</div>
</div>
<div class="mock-grid">
{chr(10).join(frames_html)}
</div>
</body>
</html>
"""
    path = OUT / "ZC-CRM-maket.html"
    path.write_text(html, encoding="utf-8")
    print("написан:", path, f"({len(html)/1024:.0f} КБ, экранов: {len(FRAMES)})")


if __name__ == "__main__":
    build()
