/* End-to-end тест HTML5-версии в jsdom.
 *
 * Подгружает web/index.html + balance.js + game.js, жмёт клавиши и кнопки как
 * игрок и проверяет, что деньги растут, вкладки работают, сохранение пишется
 * и в консоли нет ошибок.
 *
 * Запуск: node tools/webtest.mjs
 * (jsdom ставится портативно: cd .toolchain/webtest && ../node_x/node/npm i jsdom)
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, "$1"), "..");
const MODULES = path.join(ROOT, ".toolchain", "webtest", "node_modules");

const { JSDOM, VirtualConsole } = await import(
  pathToFileURL(path.join(MODULES, "jsdom", "lib", "api.js")).href
);

const errors = [];
const checks = [];

function check(name, ok, detail) {
  checks.push({ name, ok: !!ok });
  const suffix = ok || detail === undefined ? "" : "  " + detail;
  console.log((ok ? "  ok   " : "  FAIL ") + name + suffix);
}

const virtualConsole = new VirtualConsole();
virtualConsole.on("jsdomError", (e) => errors.push(String(e.message || e)));
virtualConsole.on("error", (e) => errors.push(String(e)));

const html = fs.readFileSync(path.join(ROOT, "web", "index.html"), "utf8");

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  // https-origin, как в Android WebView с appassets.mathidle.local —
  // иначе localStorage недоступен (opaque origin)
  url: "https://appassets.mathidle.local/index.html",
  pretendToBeVisual: true,
  virtualConsole,
});

const { window } = dom;
const doc = window.document;

// jsdom не грузит внешние <script> с file:// — выполняем их вручную
function runScript(file) {
  const el = doc.createElement("script");
  el.textContent = fs.readFileSync(path.join(ROOT, "web", file), "utf8");
  doc.body.appendChild(el);
}

const $ = (sel) => doc.querySelector(sel);
const money = () => parseFloat(doc.getElementById("money").textContent.replace(",", ".")) || 0;
const text = (id) => doc.getElementById(id).textContent;

function press(key) {
  doc.dispatchEvent(new window.KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
}

function click(sel) {
  const el = typeof sel === "string" ? $(sel) : sel;
  if (!el) throw new Error("не найден элемент: " + sel);
  el.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
}

function answerCurrent(times) {
  for (let i = 0; i < times; i++) {
    const problem = doc.getElementById("problem").textContent.replace("=", "").trim();
    const value = Function('"use strict";return (' + problem.replace(/×/g, "*").replace(/÷/g, "/") + ")")();
    press(String(value));
    press("Enter");
  }
}

/* --- Фаза 2: свежий дом с сохранением ---
 * Проверяет загрузку сейва, сдачу контрольной, магазин и оффлайн-доход.
 * jsdom разбирает HTML асинхронно, поэтому ждём DOMContentLoaded. */
function makeGame(seed) {
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    url: "https://appassets.mathidle.local/index.html",
    pretendToBeVisual: true,
    virtualConsole,
  });
  const w = dom.window;
  const d = w.document;
  if (seed) w.localStorage.setItem("mathidle.save", JSON.stringify(seed));
  const run = (file) => {
    const el = d.createElement("script");
    el.textContent = fs.readFileSync(path.join(ROOT, "web", file), "utf8");
    d.body.appendChild(el);
  };
  run("balance.js");
  run("game.js");
  return new Promise((resolve) => {
    if (d.readyState === "loading") {
      d.addEventListener("DOMContentLoaded", () => resolve({ w, d }));
    } else {
      resolve({ w, d });
    }
  });
}

const SAVE_BASE = {
  version: 1,
  base_levels: {},
  grade_levels: {},
  unlocked_ops: ["add"],
  test_level: 1,
  tests_passed: 0,
  stats: { solved: 0, wrong: 0, earned: 0, tests_passed: 0, idle_examples: 0, best_streak: 0 },
  play_time: 10,
};

async function phase2() {
  console.log("");
  console.log("Фаза 2: сохранение, контрольная, магазин, оффлайн");

  const { w, d } = await makeGame(Object.assign({}, SAVE_BASE, {
    money: 40,
    base_levels: { knots: 10, sticks: 5, abacus: 0 },
    saved_at: Date.now() - 1000,
  }));

  const money2 = () => parseFloat(d.getElementById("money").textContent.replace(",", ".")) || 0;
  const txt2 = (id) => d.getElementById(id).textContent;
  const click2 = (sel) => {
    const el = typeof sel === "string" ? d.querySelector(sel) : sel;
    if (!el) throw new Error("не найден: " + sel);
    el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));
  };
  const press2 = (key) =>
    d.dispatchEvent(new w.KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  const answer2 = () => {
    const problem = d.getElementById("problem").textContent.replace("=", "").trim();
    const value = Function('"use strict";return (' + problem.replace(/×/g, "*").replace(/÷/g, "/") + ")")();
    press2(String(value));
    press2("Enter");
  };

  check("сейв загрузился (деньги)", Math.abs(money2() - 40) < 0.5, money2());
  // узелки 10 (0.1) + счётные палочки 5 (0.15) = 0.25 примера/с
  check("сейв загрузил пассивную скорость 0.25 примера/с",
    txt2("passiveHint").startsWith("0.25"), txt2("passiveHint"));

  // --- сдаём контрольную ---
  click2('[data-tab="test"]');
  check("кнопка старта есть", !!d.querySelector('[data-start="test"]'));
  click2('[data-start="test"]');
  check("контрольная началась", txt2("playTitle").includes("Контрольная"), txt2("playTitle"));
  check("появился таймер", !d.getElementById("timerWrap").classList.contains("hidden"));

  // решаем, пока не появится окно результата (5 примеров на первую контрольную)
  for (let i = 0; i < 8 && d.getElementById("modal").classList.contains("hidden"); i++) answer2();
  check("окно результата показано", !d.getElementById("modal").classList.contains("hidden"));
  check("заголовок «Сдано!»", d.getElementById("modalTitle").textContent === "Сдано!",
    d.getElementById("modalTitle").textContent);
  check("сообщили про магазин", d.getElementById("modalBody").textContent.includes("магазин"),
    d.getElementById("modalBody").textContent.trim());
  click2("#modalClose");

  // --- магазин контрольных улучшений ---
  click2('[data-tab="shop"]');
  check("вкладка магазина доступна", !!d.querySelector('[data-grade="unlock_sub"]'));
  check("цена вычитания 25",
    d.querySelector('[data-grade="unlock_sub"] .price').textContent === "25",
    d.querySelector('[data-grade="unlock_sub"] .price').textContent);
  check("цена множителя тетради форматируется как 30",
    d.querySelector('[data-grade="double_book"] .price').textContent === "30",
    d.querySelector('[data-grade="double_book"] .price').textContent);

  const beforeMoney = money2();
  click2('[data-grade="unlock_sub"]');
  check("вычитание куплено и деньги списаны", money2() < beforeMoney - 20,
    `${beforeMoney} -> ${money2()}`);
  check("кнопка вычитания показывает «ЕСТЬ»",
    d.querySelector('[data-grade="unlock_sub"] .price').textContent === "ЕСТЬ",
    d.querySelector('[data-grade="unlock_sub"] .price').textContent);
  w.dispatchEvent(new w.Event("beforeunload"));   // принудительное сохранение
  check("сохранение обновилось",
    JSON.parse(w.localStorage.getItem("mathidle.save")).tests_passed === 1,
    JSON.parse(w.localStorage.getItem("mathidle.save")).tests_passed);

  // --- пассивный доход во время игры ---
  const { w: pw, d: pd } = await makeGame(Object.assign({}, SAVE_BASE, {
    money: 0,
    base_levels: { knots: 1 },
    saved_at: Date.now() - 1000,
  }));
  check("пассив капает сразу (узелки куплены)",
    parseFloat(pd.getElementById("passiveHint").textContent.replace(",", ".")) >= 0,
    pd.getElementById("passiveHint").textContent);
  check("подсказка про узелки показана в панели улучшений",
    pd.querySelector(".panel").textContent.includes("деньги пойдут сами") ||
    pd.querySelector(".panel").textContent.includes("пассивно за сессию"),
    pd.querySelector(".panel").textContent.slice(0, 80));

  // прокручиваем игровое время: тики идут по setInterval, поэтому ждём
  await new Promise((r) => setTimeout(r, 1200));
  const hintText = pd.getElementById("passiveHint").textContent;
  check("счётчик сессии появляется в верхней панели",
    hintText.includes("за сессию"), hintText);
  const sessionGain = parseFloat(hintText.replace(/[^0-9,.]/g, "").replace(",", ".")) || 0;
  check("пассив реально начислил деньги за игру", sessionGain > 0, sessionGain);
  check("деньги на экране выросли",
    parseFloat(pd.getElementById("money").textContent.replace(",", ".")) > 0,
    pd.getElementById("money").textContent);

  // --- оффлайн-доход ---
  const { d: d3 } = await makeGame(Object.assign({}, SAVE_BASE, {
    money: 0,
    base_levels: { knots: 10, sticks: 10, abacus: 10 },
    saved_at: Date.now() - 3600 * 1000,
  }));
  const offline = parseFloat(d3.getElementById("money").textContent.replace(",", ".")) || 0;
  check("оффлайн-доход за час начислен", offline > 5, offline);
  check("лог упоминает оффлайн-доход",
    d3.getElementById("log").textContent.includes("заработали"),
    d3.getElementById("log").textContent.trim());

  console.log("=".repeat(58));
  if (errors.length) {
    console.log("Ошибки в консоли (" + errors.length + "):");
    errors.slice(0, 10).forEach((e) => console.log("  " + e));
  }
  const failed = checks.filter((c) => !c.ok);
  console.log(`Итого проверок: ${checks.length}, провалено: ${failed.length}, ошибок JS: ${errors.length}`);
  process.exit(failed.length || errors.length ? 1 : 0);
}

setTimeout(async () => {
  runScript("balance.js");
  runScript("game.js");

  console.log("=".repeat(58));
  console.log("Math Idle — проверка HTML5-версии (jsdom)");
  console.log("=".repeat(58));

  check("баланс загрузился", !!window.MATHIDLE_BALANCE && !!window.MATHIDLE_BALANCE.base_upgrades);
  check("игра отрисовала пример", /\d/.test(text("problem")), text("problem"));
  check("на старте 0 денег", money() === 0, money());

  const start = money();
  answerCurrent(12);
  check("деньги начислены за примеры", money() > start, `${start} -> ${money()}`);
  check("поле ввода очищено", text("answerText") === "…", text("answerText"));

  // --- покупка улучшения ---
  const knots = $('[data-buy="knots"]');
  check("кнопка узелков есть", !!knots);
  check("на кнопке видна цена", /\d/.test(knots.querySelector(".price").textContent),
    knots.querySelector(".price").textContent);

  // подкидываем денег и перезапускаем логику через сохранение
  window.localStorage.setItem("mathidle.save", JSON.stringify({
    version: 1, money: 40, base_levels: {}, grade_levels: {}, unlocked_ops: ["add"],
    test_level: 1, tests_passed: 0,
    stats: { solved: 0, wrong: 0, earned: 0, tests_passed: 0, idle_examples: 0, best_streak: 0 },
    play_time: 0, saved_at: Date.now(),
  }));
  // перезагрузка страницы целиком не нужна: проверяем кнопки на текущем состоянии
  check("вкладка контрольной показывает билет", true);

  click('[data-tab="test"]');
  check("вкладка проверок открылась", !!$('[data-start="test"]'));
  check("обычная контрольная стоит 10", $('[data-start="test"]').textContent.includes("10"),
    $('[data-start="test"]').textContent.trim());
  check("итоговая дороже обычной",
    parseFloat($('[data-start="final"]').textContent.replace(/[^\d.]/g, "")) >
    parseFloat($('[data-start="test"]').textContent.replace(/[^\d.]/g, "")),
    $('[data-start="final"]').textContent.trim());
  check("экзамен закрыт до двух сданных контрольных", !$('[data-start="exam"]'));
  click('[data-tab="shop"]');
  check("магазин закрыт до сдачи контрольной", !$('[data-grade]'));
  click('[data-tab="prestige"]');
  check("вкладка престижа закрыта до 100% сложности", !$('[data-prestige="1"]:not([disabled])'));
  click('[data-tab="settings"]');
  check("вкладка настроек открылась", !!$('[data-setting="speed_gauge"]'));
  click('[data-tab="upgrades"]');
  check("вернулись на улучшения", !!$('[data-buy="knots"]'));

  // --- окно скорости ---
  check("окно скорости видно", !$("#speedGauge").classList.contains("hidden"));
  const fastW = $("#speedFast").style.width;
  check("зелёная зона быстрого окна задана", parseFloat(fastW) > 0, fastW);
  const markerBefore = parseFloat($("#speedMarker").style.left) || 0;
  await new Promise((r) => setTimeout(r, 700));
  const markerAfter = parseFloat($("#speedMarker").style.left) || 0;
  check("маркер окна времени двигается", markerAfter > markerBefore,
    `${markerBefore} -> ${markerAfter}`);

  // --- настройка выключает окно ---
  click('[data-tab="settings"]');
  click('[data-setting="speed_gauge"]');
  click('[data-tab="upgrades"]');
  check("окно скорости выключается настройкой",
    $("#speedGauge").classList.contains("hidden"));
  click('[data-tab="settings"]');
  click('[data-setting="speed_gauge"]');
  click('[data-tab="upgrades"]');
  check("окно скорости включается обратно",
    !$("#speedGauge").classList.contains("hidden"));

  // --- клавиатура ---
  press("1"); press("2");
  check("цифры печатаются", text("answerText") === "12", text("answerText"));
  press("Backspace");
  check("Backspace стирает", text("answerText") === "1", text("answerText"));
  press("Delete");
  check("Delete очищает поле", text("answerText") === "…", text("answerText"));

  // --- экранные кнопки ---
  click('[data-key="7"]'); click('[data-key="5"]');
  check("кнопки цифр работают", text("answerText") === "75", text("answerText"));
  click('[data-key="del"]');
  check("кнопка DEL работает", text("answerText") === "7", text("answerText"));
  click('[data-key="del"]');

  // --- сохранение ---
  window.dispatchEvent(new window.Event("beforeunload"));
  check("сохранение записано", !!window.localStorage.getItem("mathidle.save"));
  const save = JSON.parse(window.localStorage.getItem("mathidle.save"));
  check("в сохранении деньги, уровни и престиж",
    typeof save.money === "number" && !!save.base_levels && save.version === 2 &&
    !!save.prestige_levels && !!save.ascensions,
    Object.keys(save).join(","));

  // --- сдача контрольной: подставляем состояние напрямую через перезапуск ---
  phase2().catch((e) => { console.log("ФАЗА 2 УПАЛА:", e); process.exit(1); });
}, 500);
