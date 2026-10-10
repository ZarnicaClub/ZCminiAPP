"""Разметка расшифровки звонка по словам — без моделей и без обращений в сеть.

Задача: по тексту разговора понять
- **тип запроса** (детский, корпоратив, школьная группа, праздник взрослых, просто игра,
  нецелевой, непонятно),
- **дату игры**, если её назвали (в том числе «завтра», «в субботу»),
- **число игроков**, если его назвали.

Почему только правила: расшифровка приходит с ошибками («пиньболг» вместо «пейнтбол»),
однако по смыслу читается; правила ищут **корни** слов, объяснимы (видно, какая фраза
сработала) и бесплатны. Матчинг, который не понял, честно уходит в «непонятно».

Всё здесь — чистые функции: их можно и нужно проверять тестами без базы и без модели.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

TYPES = (
    "нецелевой",
    "школьная_группа",
    "детский",
    "корпоратив",
    "праздник_взрослые",
    "просто_игра",
    "непонятно",
)

# --- признаки по корням слов (сравнение идёт по нормализованному тексту) ---

NON_TARGET = (
    "задолженност", "ошиблись номером", "не туда попал", "вы не туда",
    "автоинформатор", "робот", "спам", "рекламн", "ваканси", "резюме",
    "поставщик", "оптов", "сотрудничеств предлагаем",
)

SCHOOL = (
    re.compile(r"\bшкол\w*"), re.compile(r"\bучител\w*"), re.compile(r"\bвыпускн\w*"),
    re.compile(r"\bкласс(а|у|е|ом|ы|ов)?\b"),          # «классные перчатки» — не школа
    re.compile(r"\bпервое сентября\b"), re.compile(r"\bродительск\w*"),
)

# Осторожно с короткими корнями: «дет» сидит в слове «будет», «класс» — в «классные».
CHILD = (
    re.compile(r"\bдет(ск|сад|и|ей|ям|ями|ьми|ьм)\w*"),
    re.compile(r"\bребен\w*"), re.compile(r"\bмалыш\w*"), re.compile(r"\bсадик\w*"),
    re.compile(r"\bподрост\w*"), re.compile(r"\bдочк\w*"), re.compile(r"\bдочер\w*"),
    re.compile(r"\bсын\w*"), re.compile(r"\bвнук\w*"), re.compile(r"\bвнучк\w*"),
)

CORPORATE = (
    "корпоратив", "сотрудник", "коллег", "от работы", "от компании", "фирм",
    "тимбилд", "начальств", "рабочий коллектив", "день компании", "организатор мероприятий",
    "организацией мероприятий", "организация мероприятий",
)

ADULT_PARTY = (
    "день рожден", "днюх", "юбиле", "друз", "взросл", "муж", "жен",
)

PLAY = (
    "поиграт", "играт", "забронир", "бронир", "бронь", "покатат", "приеха", "аренд",
    "пейнтбол", "пиньбол", "пинбол", "пейбол", "лазертаг", "лазер", "кидбол", "стрельб",
)

MONTHS = (
    ("январ", 1), ("янв", 1), ("феврал", 2), ("февр", 2), ("март", 3), ("апр", 4),
    ("май", 5), ("мая", 5), ("июн", 6), ("июл", 7), ("август", 8), ("авг", 8),
    ("сентябр", 9), ("сент", 9), ("октябр", 10), ("окт", 10), ("ноябр", 11), ("нояб", 11),
    ("декабр", 12), ("дек", 12),
)

WEEKDAYS = (
    (r"\bв понедельник\w*\b", 0), (r"\bв вторник\w*\b", 1), (r"\bв сред(у|е|ы)\b", 2),
    (r"\bв четверг\w*\b", 3), (r"\bв пятниц\w*\b", 4), (r"\bв суббот\w*\b", 5),
    (r"\bв воскресен\w*\b", 6),
)

UNITS = (
    ("перв", 1), ("втор", 2), ("трет", 3), ("четверт", 4), ("пят", 5), ("шест", 6),
    ("седьм", 7), ("восьм", 8), ("девят", 9), ("десят", 10), ("одиннадцат", 11),
    ("двенадцат", 12), ("тринадцат", 13), ("четырнадцат", 14), ("пятнадцат", 15),
    ("шестнадцат", 16), ("семнадцат", 17), ("восемнадцат", 18), ("девятнадцат", 19),
)
TENS = (("двадцат", 20), ("тридцат", 30), ("сорок", 40), ("пятьдесят", 50))

# Количественные числительные («два человека», «придут пять ребят») — от длинных к коротким.
CARDINALS = (
    ("одиннадцать", 11), ("двенадцать", 12), ("тринадцать", 13), ("четырнадцать", 14),
    ("пятнадцать", 15), ("шестнадцать", 16), ("семнадцать", 17), ("восемнадцать", 18),
    ("девятнадцать", 19), ("двадцать", 20), ("тридцать", 30), ("сорок", 40),
    ("пятьдесят", 50), ("десять", 10), ("девять", 9), ("восемь", 8), ("семь", 7),
    ("шесть", 6), ("пять", 5), ("четыре", 4), ("три", 3), ("два", 2), ("две", 2),
    ("пара", 2),
)

# Слова-«звоню вам завтра»: это не дата игры.
CALLBACK = ("наберу", "перезвон", "позвоню", "позвонит", "набрать", "жду звонка", "созвоним")

PEOPLE_UNITS = ("человек", "чел ", "участник", "гост", "детей", "ребят", "персон")
BAD_UNITS = ("рубл", "тысяч", "шарик", "минут", "час", "секунд", "процент", "₽", "штук")

MONTH_GEN = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
             "августа", "сентября", "октября", "ноября", "декабря")


def norm_text(text: str) -> str:
    """Нижний регистр, ё→е, только буквы/цифры/пробелы, одиночные пробелы."""
    s = (text or "").lower().replace("ё", "е")
    s = re.sub(r"[^а-я0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _hit(text: str, stems) -> str | None:
    """Первое совпадение: строка ищется как подстрока, скомпилированный шаблон — как регэксп."""
    for stem in stems:
        if hasattr(stem, "search"):
            m = stem.search(text)
            if m:
                return m.group(0)
        elif stem in text:
            return stem
    return None


def detect_type(text: str) -> dict:
    """Тип запроса + фраза-признак, по которой решили."""
    t = norm_text(text)
    hit = _hit(t, NON_TARGET)
    if hit:
        return {"type": "нецелевой", "why": hit}
    hit = _hit(t, SCHOOL)
    if hit:
        return {"type": "школьная_группа", "why": hit}
    hit = _hit(t, CHILD)
    if hit:
        return {"type": "детский", "why": hit}
    hit = _hit(t, CORPORATE)
    if hit:
        return {"type": "корпоратив", "why": hit}
    hit = _hit(t, ADULT_PARTY)
    if hit:
        return {"type": "праздник_взрослые", "why": hit}
    hit = _hit(t, PLAY)
    if hit:
        return {"type": "просто_игра", "why": hit}
    return {"type": "непонятно", "why": None}


def _word_number(chunk: str) -> int | None:
    """«тридцать первое» → 31, «двадцать» → 20, «восьмое» → 8."""
    tens = units = 0
    for stem, val in TENS:
        if stem in chunk:
            tens = val
            break
    for stem, val in UNITS:
        if stem in chunk:
            units = val
            break
    if tens and units:
        return tens + units
    return tens or units or None


def _near(text: str, pos: int, words, window: int = 35) -> bool:
    """Есть ли рядом слово из списка (например, «наберу» рядом с «в понедельник»)."""
    chunk = text[max(0, pos - window):pos + window]
    return any(w in chunk for w in words)


def find_date(text: str, call_day: date) -> dict | None:
    """Дата игры: явная («31 октября»), относительная («завтра», «в субботу») или «17-го числа».

    Даты-обещания перезвонить («в понедельник наберу») отбрасываются: это не день игры.
    """
    t = norm_text(text)

    for stem, month in MONTHS:
        m = re.search(stem, t)
        if not m:
            continue
        before = t[max(0, m.start() - 22):m.start()]
        day = None
        digits = re.findall(r"\b(\d{1,2})\b", before)
        if digits:
            day = int(digits[-1])
        if day is None:
            day = _word_number(before)
        if not day or not 1 <= day <= 31:
            continue
        year = call_day.year
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if d < call_day:  # «31 октября» сказали в ноябре — значит следующий год
            d = date(year + 1, month, day)
        return {"date": d.isoformat(), "kind": "explicit", "text": f"{day} {MONTH_GEN[month - 1]}"}

    # «завтра», «послезавтра» — но не «завтра вам перезвоню»
    for word, delta in (("послезавтра", 2), ("завтра", 1)):
        for m in re.finditer(rf"\b{word}\b", t):
            if _near(t, m.start(), CALLBACK):
                continue
            d = call_day + timedelta(days=delta)
            return {"date": d.isoformat(), "kind": "relative", "text": word}

    # «в субботу», «в пятницу» — тоже мимо обещаний позвонить
    for pattern, num in WEEKDAYS:
        m = re.search(pattern, t)
        if m and not _near(t, m.start(), CALLBACK):
            ahead = (num - call_day.weekday()) % 7 or 7
            d = call_day + timedelta(days=ahead)
            return {"date": d.isoformat(), "kind": "relative", "text": m.group(0)}

    # «17-го числа» — день без месяца: этот месяц, а если уже прошёл — следующий
    m = re.search(r"\b(\d{1,2})\s+(?:го|числа)\b", t)
    if m and not _near(t, m.start(), ("лет", "рубл", "тысяч", "шарик", "минут")):
        day = int(m.group(1))
        if 1 <= day <= 31:
            year, month = call_day.year, call_day.month
            if day < call_day.day:
                month += 1
                if month > 12:
                    year, month = year + 1, 1
            d = date(year, month, day)
            return {"date": d.isoformat(), "kind": "explicit", "text": m.group(0)}
    return None


def find_players(text: str) -> dict | None:
    """Число игроков: «30 человек», «человек 30», «нас будет тридцать», «на 10 человек»."""
    t = norm_text(text)
    unit = "|".join(PEOPLE_UNITS)
    bad = "|".join(BAD_UNITS)

    # «30 человек» / «30 участников»
    for m in re.finditer(rf"\b(\d{{1,3}})\s*(?:{unit})", t):
        n = int(m.group(1))
        if 2 <= n <= 500 and not re.search(rf"\d{{1,3}}\s*(?:{bad})", t[max(0, m.start() - 4):m.end() + 6]):
            return {"players": n, "text": m.group(0).strip()}

    # «человек 30» / «человек тридцать»
    for m in re.finditer(rf"(?:{unit})\s+(?:где то\s+)?(?:примерно\s+)?(\d{{1,3}})", t):
        n = int(m.group(1))
        if 2 <= n <= 500:
            return {"players": n, "text": m.group(0).strip()}

    # «два человека», «пять ребят» — число словом перед единицей
    card = "|".join(w for w, _ in CARDINALS)
    m = re.search(rf"\b({card})\s+(?:{unit})", t)
    if m:
        for word, val in CARDINALS:
            if m.group(1) == word and 2 <= val <= 500:
                return {"players": val, "text": m.group(0).strip()}

    # словом: «человек тридцать», «нас будет тридцать»
    for m in re.finditer(rf"(?:{unit})\s+(?:где то\s+)?((?:двадцат|тридцат|сорок|пятьдесят)\w*)", t):
        n = _word_number(m.group(1))
        if n and 2 <= n <= 500:
            return {"players": n, "text": m.group(0).strip()}

    # «нас будет 30», «будет человек 30», «планируется 30»
    m = re.search(r"(?:нас|будет|планиру\w*|приед\w*|примерно|около|порядка)\s+(?:где то\s+)?(\d{1,3})\b", t)
    if m:
        n = int(m.group(1))
        if 2 <= n <= 500:
            return {"players": n, "text": m.group(0).strip()}
    return None


def classify(text: str, call_day: date) -> dict:
    """Полная разметка одного разговора.

    Дату и число игроков берём только у звонков «по нашей тематике»: если по тексту
    не видно даже игры (тип `непонятно` или `нецелевой`), любое число и дата — случайные.
    """
    res = detect_type(text)
    game = res["type"] not in ("непонятно", "нецелевой")
    res["date"] = find_date(text, call_day) if game else None
    res["players"] = find_players(text) if game else None
    res["source"] = "rules-v1"
    return res
