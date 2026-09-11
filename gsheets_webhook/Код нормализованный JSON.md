function testSendNormalizedCashOrder() {

  const WEBHOOK_URL =
    "https://webhook.site/ff257bfb-9ac4-49f4-8c75-b368e9d9d466";

  const START_DATE = new Date(2026, 7, 13);

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName("БАЛАНС");

  if (!sheet) {
    throw new Error('Лист "БАЛАНС" не найден');
  }

  const data = sheet.getDataRange().getDisplayValues();

  if (data.length < 2) {
    throw new Error("На листе нет данных");
  }

  // ---------------------------------------------
  // Определяем колонки
  // ---------------------------------------------

  const headers = data[0];
  const column = {};

  headers.forEach((header, index) => {
    const name = header
      .replace(/\n/g, " ")
      .trim();

    column[name] = index;
  });

  const requiredColumns = [
    "Статья",
    "Дата",
    "Приход",
    "№ документа",
    "игроков (факт)",
    "Заказчик",
    "Зона отдыха",
    "order_id"
  ];

  requiredColumns.forEach(name => {
    if (column[name] === undefined) {
      throw new Error(
        'Не найдена колонка: "' + name + '"'
      );
    }
  });

  // ---------------------------------------------
  // Ищем первую подходящую строку
  // ---------------------------------------------

  let selectedRow = null;

  for (let i = 1; i < data.length; i++) {

    const row = data[i];

    if (row[column["Статья"]].trim() !== "Касса") {
      continue;
    }

    const dateText = row[column["Дата"]].trim();

    if (!dateText) {
      continue;
    }

    const parts = dateText.split(".");

    if (parts.length !== 3) {
      continue;
    }

    const day = Number(parts[0]);
    const month = Number(parts[1]);
    const year = Number(parts[2]);

    const gameDate = new Date(
      year,
      month - 1,
      day
    );

    if (isNaN(gameDate.getTime())) {
      continue;
    }

    if (gameDate < START_DATE) {
      continue;
    }

    const orderId = row[column["order_id"]].trim();

    if (!orderId) {
      continue;
    }

    selectedRow = {
      source_row: i + 1,
      order_id: orderId,
      game_date: dateText,
      order_amount: row[column["Приход"]].trim(),
      bso_number: row[column["№ документа"]].trim(),
      players_fact: row[column["игроков (факт)"]].trim(),
      customer_name: row[column["Заказчик"]].trim(),
      rest_zone_amount: row[column["Зона отдыха"]].trim()
    };

    break;
  }

  if (!selectedRow) {
    throw new Error(
      "Не найдена подходящая строка Касса"
    );
  }

  // ---------------------------------------------
  // Нормализация
  // ---------------------------------------------

  const orderId = parseInteger(
    selectedRow.order_id,
    "order_id"
  );

  const orderAmount = parseMoney(
    selectedRow.order_amount,
    "Приход"
  );

  const playersFact = parseInteger(
    selectedRow.players_fact,
    "игроков (факт)"
  );

  const restZoneAmount =
    parseNullableMoney(
      selectedRow.rest_zone_amount,
      "Зона отдыха"
    );

  const isoDate = convertDateToISO(
    selectedRow.game_date
  );

  // ---------------------------------------------
  // Финальный JSON
  // ---------------------------------------------

  const payload = {
    order_id: orderId,
    game_date: isoDate,
    order_amount: orderAmount,
    bso_number: selectedRow.bso_number,
    players_fact: playersFact,
    customer_name: selectedRow.customer_name,
    rest_zone_amount: restZoneAmount
  };

  // ---------------------------------------------
  // POST
  // ---------------------------------------------

  const options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  const response = UrlFetchApp.fetch(
    WEBHOOK_URL,
    options
  );

  // ---------------------------------------------
  // Журнал
  // ---------------------------------------------

  Logger.log("========================================");
  Logger.log("NORMALIZED CASH ORDER TEST");
  Logger.log("========================================");

  Logger.log(
    "Исходная строка: " +
    selectedRow.source_row
  );

  Logger.log("");

  Logger.log("JSON:");

  Logger.log(
    JSON.stringify(payload, null, 2)
  );

  Logger.log("");

  Logger.log(
    "HTTP код: " +
    response.getResponseCode()
  );

  Logger.log("");

  Logger.log(
    "Ответ сервера:"
  );

  Logger.log(
    response.getContentText()
  );

  Logger.log("========================================");
}


// =================================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// =================================================

function parseMoney(value, fieldName) {

  if (value === null || value === undefined) {
    throw new Error(
      fieldName + ": значение отсутствует"
    );
  }

  let text = String(value).trim();

  if (!text) {
    throw new Error(
      fieldName + ": значение пустое"
    );
  }

  // Убираем пробелы и неразрывные пробелы
  text = text
    .replace(/\s/g, "")
    .replace(/\u00A0/g, "");

  // Российский формат:
  // 19 000,00 → 19000.00
  text = text.replace(",", ".");

  const number = Number(text);

  if (!isFinite(number)) {
    throw new Error(
      fieldName +
      ': невозможно преобразовать "' +
      value +
      '" в число'
    );
  }

  return number;
}


function parseNullableMoney(value, fieldName) {

  if (
    value === null ||
    value === undefined ||
    String(value).trim() === ""
  ) {
    return null;
  }

  return parseMoney(value, fieldName);
}


function parseInteger(value, fieldName) {

  if (value === null || value === undefined) {
    throw new Error(
      fieldName + ": значение отсутствует"
    );
  }

  const text = String(value)
    .trim()
    .replace(/\s/g, "")
    .replace(/\u00A0/g, "");

  if (!text) {
    throw new Error(
      fieldName + ": значение пустое"
    );
  }

  const number = Number(text);

  if (!Number.isInteger(number)) {
    throw new Error(
      fieldName +
      ': значение "' +
      value +
      '" не является целым числом'
    );
  }

  return number;
}


function convertDateToISO(dateText) {

  const parts = dateText.split(".");

  if (parts.length !== 3) {
    throw new Error(
      'Неверный формат даты: "' +
      dateText +
      '"'
    );
  }

  const day = Number(parts[0]);
  const month = Number(parts[1]);
  const year = Number(parts[2]);

  if (
    !Number.isInteger(day) ||
    !Number.isInteger(month) ||
    !Number.isInteger(year)
  ) {
    throw new Error(
      'Неверная дата: "' +
      dateText +
      '"'
    );
  }

  return (
    year.toString().padStart(4, "0") +
    "-" +
    month.toString().padStart(2, "0") +
    "-" +
    day.toString().padStart(2, "0")
  );
}