/**
 * ZarnicaCRM — Google Sheets → CRM (БСО), production.
 * Ядро нормализации — из проверенного testSendNormalizedCashOrder.
 * Добавлено: все готовые строки, auth X-Gsheets-Secret, конфиг в Script Properties.
 *
 * Настройка (Script Properties):
 *   GSHEETS_ENDPOINT = https://<хост orders-webhook>/webhook/gsheets
 *   GSHEETS_SECRET   = та же строка, что в env GSHEETS_SECRET у orders-webhook
 *
 * Запуск: функция processSheet (вручную) + триггер «по времени → каждые 5 минут».
 */

var CONFIG = {
  SPREADSHEET_ID: '',          // пусто = активная таблица (bound script)
  SHEET_NAME: 'БАЛАНС',
  DATE_FROM: '2026-08-13',     // 13.08.2026
  ARTICLE_VALUE: 'Касса',
  COL: {
    article:     'Статья',
    date:        'Дата',
    income:      'Приход',
    docNumber:   '№ документа',
    playersFact: 'игроков (факт)',
    customer:    'Заказчик',
    restZone:    'Зона отдыха',
    orderId:     'order_id',
  },
};

function getSheet_() {
  var ss = CONFIG.SPREADSHEET_ID
    ? SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID)
    : SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(CONFIG.SHEET_NAME);
  if (!sheet) throw new Error('Лист "' + CONFIG.SHEET_NAME + '" не найден');
  return sheet;
}

function getColumns_(sheet) {
  var headers = sheet.getDataRange().getDisplayValues()[0];
  var column = {};
  headers.forEach(function (header, index) {
    var name = String(header).replace(/\n/g, ' ').trim();
    if (name) column[name] = index;
  });
  var idx = {}, missing = [];
  Object.keys(CONFIG.COL).forEach(function (key) {
    var name = CONFIG.COL[key];
    if (column[name] === undefined) missing.push(name);
    else idx[key] = column[name];
  });
  if (missing.length) throw new Error('Не найдены колонки: "' + missing.join('", "') + '"');
  return idx;
}

function sendToBackend_(payload) {
  var props = PropertiesService.getScriptProperties();
  var endpoint = props.getProperty('GSHEETS_ENDPOINT');
  var secret = props.getProperty('GSHEETS_SECRET') || '';
  if (!endpoint) throw new Error('Script Property GSHEETS_ENDPOINT не задан');
  var options = {
    method: 'post',
    contentType: 'application/json',
    headers: { 'X-Gsheets-Secret': secret },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  };
  var resp = UrlFetchApp.fetch(endpoint, options);
  return { code: resp.getResponseCode(), body: resp.getContentText() };
}

function processSheet() {
  var sheet = getSheet_();
  var idx = getColumns_(sheet);
  var data = sheet.getDataRange().getDisplayValues();

  var sent = 0, skipped = 0, errors = 0;

  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    var srcRow = i + 1;
    try {
      if (String(row[idx.article] || '').trim() !== CONFIG.ARTICLE_VALUE) continue;

      var dateText = String(row[idx.date] || '').trim();
      if (!dateText) continue;
      var isoDate = convertDateToISO(dateText);
      if (isoDate < CONFIG.DATE_FROM) continue;

      var orderIdText = String(row[idx.orderId] || '').trim();
      if (!orderIdText) continue;

      var payload = {
        order_id: parseInteger(orderIdText, 'order_id'),
        game_date: isoDate,
        order_amount: parseMoney(row[idx.income], 'Приход'),
        bso_number: String(row[idx.docNumber] || '').trim(),
        players_fact: parseInteger(row[idx.playersFact], 'игроков (факт)'),
        customer_name: String(row[idx.customer] || '').trim(),
        rest_zone_amount: parseNullableMoney(row[idx.restZone], 'Зона отдыха'),
      };

      var res = sendToBackend_(payload);
      if (res.code >= 200 && res.code < 300) {
        var status = null;
        try { status = JSON.parse(res.body).status; } catch (e) {}
        if (status === 'skipped') { skipped++; Logger.log('SKIP (нет заказа) order_id=' + payload.order_id); }
        else { sent++; Logger.log('OK order_id=' + payload.order_id); }
      } else {
        errors++;
        Logger.log('HTTP ' + res.code + ' (строка ' + srcRow + ', order_id=' + payload.order_id + '): ' + res.body);
      }
    } catch (e) {
      errors++;
      Logger.log('Строка ' + srcRow + ': ' + e.message);
    }
  }

  Logger.log('Итог: отправлено=' + sent + ' пропущено=' + skipped + ' ошибки=' + errors);
}

// ============ проверенные хелперы (из testSendNormalizedCashOrder) ============

function parseMoney(value, fieldName) {
  if (value === null || value === undefined) throw new Error(fieldName + ': значение отсутствует');
  var text = String(value).trim().replace(/\s/g, '').replace(/\u00A0/g, '');
  if (!text) throw new Error(fieldName + ': значение пустое');
  text = text.replace(',', '.');
  var number = Number(text);
  if (!isFinite(number)) throw new Error(fieldName + ': невозможно преобразовать "' + value + '" в число');
  return number;
}

function parseNullableMoney(value, fieldName) {
  if (value === null || value === undefined || String(value).trim() === '') return null;
  return parseMoney(value, fieldName);
}

function parseInteger(value, fieldName) {
  if (value === null || value === undefined) throw new Error(fieldName + ': значение отсутствует');
  var text = String(value).trim().replace(/\s/g, '').replace(/\u00A0/g, '');
  if (!text) throw new Error(fieldName + ': значение пустое');
  var number = Number(text);
  if (!Number.isInteger(number)) throw new Error(fieldName + ': значение "' + value + '" не является целым числом');
  return number;
}

function convertDateToISO(dateText) {
  var parts = dateText.split('.');
  if (parts.length !== 3) throw new Error('Неверный формат даты: "' + dateText + '"');
  var day = Number(parts[0]);
  var month = Number(parts[1]);
  var year = Number(parts[2]);
  if (!Number.isInteger(day) || !Number.isInteger(month) || !Number.isInteger(year)) {
    throw new Error('Неверная дата: "' + dateText + '"');
  }
  return year.toString().padStart(4, '0') + '-' + month.toString().padStart(2, '0') + '-' + day.toString().padStart(2, '0');
}
