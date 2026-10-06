/* Math Idle — HTML5/JS-порт pygame-версии.
 *
 * Баланс приходит из balance.js (выгружается из mathidle/config.py скриптом
 * tools/export_balance.py), поэтому обе версии считают деньги одинаково.
 * Правки баланса делаются только в Python-конфиге.
 */
(function () {
  "use strict";

  var B = window.MATHIDLE_BALANCE;
  var R = B.rewards, T = B.test;

  // ---------------------------------------------------------------- utils
  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function nowSec() { return Date.now() / 1000; }
  function rndInt(rng, a, b) { return a + Math.floor(rng() * (b - a + 1)); }

  // детерминированный генератор, чтобы примеры не «прыгали» при каждом кадре
  function mulberry32(seed) {
    return function () {
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  var rng = mulberry32(0x9E3779B9);

  function operation(id) {
    for (var i = 0; i < B.operations.length; i++) if (B.operations[i].id === id) return B.operations[i];
    throw new Error("operation " + id);
  }
  function baseUpgrade(id) {
    for (var i = 0; i < B.base_upgrades.length; i++) if (B.base_upgrades[i].id === id) return B.base_upgrades[i];
    throw new Error("upgrade " + id);
  }
  function gradeItem(id) {
    for (var i = 0; i < B.grade_items.length; i++) if (B.grade_items[i].id === id) return B.grade_items[i];
    throw new Error("item " + id);
  }

  // ------------------------------------------------------- форматирование
  var SUFFIX = ["", "K", "M", "B", "T", "aa", "ab", "ac"];

  function fmtMoney(value) {
    var v = Number(value) || 0;
    if (v === 0) return "0";
    if (Math.abs(v) >= 1000) {
      var n = v, i = 0;
      while (Math.abs(n) >= 1000 && i < SUFFIX.length - 1) { n /= 1000; i++; }
      return n.toFixed(2) + SUFFIX[i];
    }
    if (Math.abs(v) < 1e-5) return v.toExponential(2).replace("e-", "e-");
    if (Math.abs(v) < 1) return v.toFixed(4);
    if (Math.abs(v - Math.round(v)) < 1e-9 && Math.abs(v) < 1000) return String(Math.round(v));
    return v.toFixed(3);
  }

  function fmtRate(v) {
    v = Number(v) || 0;
    if (v === 0) return "0";
    if (Math.abs(v) < 0.01) return v.toFixed(3);
    if (Math.abs(v) < 10) return v.toFixed(2);
    return v.toFixed(1);
  }

  function fmtTime(sec) {
    var s = Math.max(0, Math.round(sec));
    if (s < 60) return s + "с";
    return Math.floor(s / 60) + "м " + String(s % 60).padStart(2, "0") + "с";
  }

  // ------------------------------------------------------ генерация примеров
  function genAdd(diff, cfg) {
    var terms = 2;
    if (diff > 0.30) terms++;
    if (diff > 0.65 && (cfg.max_terms || 4) >= 3) terms++;
    if (diff > 0.90 && (cfg.max_terms || 4) >= 4) terms++;
    terms = Math.min(terms, cfg.max_terms || 4);
    var hi = Math.max(4, Math.round(5 + 45 * diff));
    var nums = [], sum = 0, text = [];
    for (var i = 0; i < terms; i++) {
      var n = rndInt(rng, 1, hi);
      nums.push(n); sum += n; text.push(String(n));
    }
    return { text: text.join(" + "), answer: sum };
  }

  function genSub(diff) {
    var hi = Math.max(8, Math.round(9 + 90 * diff));
    var a = rndInt(rng, Math.max(4, Math.floor(hi / 2)), hi);
    var b = rndInt(rng, 1, Math.max(1, a - 1));
    return { text: a + " - " + b, answer: a - b };
  }

  function genMul(diff) {
    var hi = Math.max(5, Math.round(6 + 19 * diff));
    var a = rndInt(rng, 2, hi), b = rndInt(rng, 2, hi);
    return { text: a + " × " + b, answer: a * b };
  }

  function genDiv(diff) {
    var hiB = Math.max(3, Math.round(3 + 9 * diff));
    var hiQ = Math.max(4, Math.round(5 + 20 * diff));
    var b = rndInt(rng, 2, hiB), q = rndInt(rng, 2, hiQ);
    return { text: (b * q) + " ÷ " + b, answer: q };
  }

  function atomic(diff, hi) {
    var roll = rng();
    if (roll < 0.30) {
      var a = rndInt(rng, 2, hi), b = rndInt(rng, 2, hi);
      return { text: a + " × " + b, value: a * b };
    }
    if (roll < 0.48) {
      var d = rndInt(rng, 2, Math.max(3, Math.floor(hi / 2)));
      var q = rndInt(rng, 2, Math.max(3, Math.floor(hi / 2)));
      return { text: (d * q) + " ÷ " + d, value: q };
    }
    var n = rndInt(rng, 1, hi + 4);
    return { text: String(n), value: n };
  }

  function genExpr(diff) {
    var hi = Math.max(5, Math.round(5 + 15 * diff));
    var pieces = diff < 0.45 ? 4 : 5;
    if (diff > 0.85) pieces = 6;
    var total = 0, chunks = [];
    for (var i = 0; i < pieces; i++) {
      var at = atomic(diff, hi), sign;
      if (i === 0) {
        sign = "+";
      } else {
        var minus = rng() < 0.4;
        if (minus && total - at.value < 0) minus = false;
        sign = minus ? "-" : "+";
      }
      chunks.push({ sign: sign, text: at.text });
      total += sign === "+" ? at.value : -at.value;
    }
    var body = chunks[0].text;
    for (var k = 1; k < chunks.length; k++) body += " " + chunks[k].sign + " " + chunks[k].text;
    return { text: body, answer: total };
  }

  var GENERATORS = { add: genAdd, sub: genSub, mul: genMul, div: genDiv, expr: genExpr };

  function generate(opId, difficulty) {
    var diff = clamp(difficulty, 0, 1);
    var res = GENERATORS[opId](diff, operation(opId));
    return { text: res.text, answer: Math.round(res.answer), op: opId, difficulty: diff };
  }

  function randomProblem(opIds, difficulty) {
    if (!opIds || !opIds.length) opIds = ["add"];
    return generate(opIds[Math.floor(rng() * opIds.length)], difficulty);
  }

  // ------------------------------------------------------------- экономика
  function upgradeCost(up, level) {
    var n = level + 1;
    if (up.cost_kind === "linear") return up.cost_start * n;
    return up.cost_start + up.cost_step * n * (n - 1);
  }

  function gradeCost(item, level) {
    return item.price * Math.pow(item.growth == null ? 1 : item.growth, level);
  }

  function effectTotal(effect) {
    var total = 0;
    for (var i = 0; i < B.grade_items.length; i++) {
      var it = B.grade_items[i];
      if (it.effect === effect) total += it.per_level * (state.grade[it.id] || 0);
    }
    return total;
  }

  function moneyMult() { return 1 + effectTotal("money_mult"); }
  function speedMult() { return 1 + effectTotal("speed_window"); }
  function addMult() { return 1 + effectTotal("add_bonus"); }
  function passiveMult() { return 1 + effectTotal("passive_share"); }

  function hintEvery() {
    var levels = effectTotal("hint_every");
    return levels <= 0 ? 0 : Math.max(4, Math.floor(10 / levels));
  }

  function difficultyFactor(d) { return 1 - (1 - R.diff_floor) * clamp(d, 0, 1); }

  function speedFactor(elapsed) {
    var fast = R.fast_window * speedMult(), slow = R.slow_window * speedMult();
    if (elapsed <= fast) return 1;
    if (elapsed >= slow) return R.speed_floor;
    return 1 - (1 - R.speed_floor) * ((elapsed - fast) / (slow - fast));
  }

  function comboBonus(combo) { return Math.min(R.combo_max, combo * R.combo_step); }

  function reward(opId, difficulty, elapsed, combo) {
    var amount = operation(opId).cap * difficultyFactor(difficulty) * speedFactor(elapsed) *
      moneyMult() * (1 + comboBonus(combo));
    if (opId === "add") amount *= addMult();
    return amount;
  }

  function passiveReward(opId) {
    return operation(opId).cap * difficultyFactor(R.idle_difficulty) * moneyMult() *
      R.passive_share * passiveMult();
  }

  function testReward(level) { return T.pass_bonus + T.pass_bonus_per_level * (level - 1); }
  function testProblemCount(level) { return Math.min(T.max_problems, T.base_problems + T.problems_per_level * (level - 1)); }
  function testDifficulty(level) { return Math.min(T.diff_max, T.diff_base + T.diff_per_level * (level - 1)); }
  function testTimeLimit(level) { return T.base_time + T.time_per_problem * testProblemCount(level) + effectTotal("test_time"); }

  // ----------------------------------------------------------------- state
  var SAVE_KEY = "mathidle.save";
  var state = {
    money: 0,
    base: {}, grade: {}, ops: ["add"],
    testLevel: 1, testsPassed: 0,
    combo: 0, lastCorrectAt: 0,
    playTime: 0,
    stats: { solved: 0, wrong: 0, earned: 0, tests_passed: 0, idle_examples: 0, best_streak: 0 },
    current: null, shownAt: 0,
    test: null,
    clock: 0, lastTick: nowSec()
  };

  (function initState() {
    for (var i = 0; i < B.base_upgrades.length; i++) state.base[B.base_upgrades[i].id] = 0;
    for (var j = 0; j < B.grade_items.length; j++) state.grade[B.grade_items[j].id] = 0;
  })();

  function load() {
    var raw = null;
    try { raw = localStorage.getItem(SAVE_KEY); } catch (e) { raw = null; }
    if (!raw) return null;
    var data;
    try { data = JSON.parse(raw); } catch (e) { return null; }
    if (!data || data.version !== 1) return null;

    state.money = Number(data.money) || 0;
    for (var i = 0; i < B.base_upgrades.length; i++) {
      var bid = B.base_upgrades[i].id;
      state.base[bid] = Number((data.base_levels || {})[bid]) || 0;
    }
    for (var j = 0; j < B.grade_items.length; j++) {
      var gid = B.grade_items[j].id;
      state.grade[gid] = Number((data.grade_levels || {})[gid]) || 0;
    }
    var valid = {};
    for (var k = 0; k < B.operations.length; k++) valid[B.operations[k].id] = true;
    state.ops = (data.unlocked_ops && data.unlocked_ops.length ? data.unlocked_ops : ["add"])
      .filter(function (o) { return valid[o]; });
    if (state.ops.indexOf("add") < 0) state.ops.push("add");
    state.testLevel = Math.max(1, Number(data.test_level) || 1);
    state.testsPassed = Number(data.tests_passed) || 0;
    state.playTime = Number(data.play_time) || 0;
    if (data.stats) for (var s in state.stats) {
      if (Object.prototype.hasOwnProperty.call(data.stats, s)) state.stats[s] = data.stats[s];
    }
    return data;
  }

  var earnedOffline = 0, awayTime = 0;

  function applyOffline(savedAt) {
    awayTime = Math.max(0, nowSec() - (Number(savedAt) / 1000 || nowSec()));
    if (!B.offline.enabled || awayTime < 60) return;
    var capped = Math.min(awayTime, B.offline.cap_hours * 3600);
    var rate = passiveRate();
    if (rate > 0) {
      earnedOffline = rate * capped * passiveReward(topOperation()) * B.offline.efficiency;
      state.money += earnedOffline;
    }
  }

  var saveTimer = 0;
  function save() {
    try {
      localStorage.setItem(SAVE_KEY, JSON.stringify({
        version: 1,
        money: state.money,
        base_levels: state.base,
        grade_levels: state.grade,
        unlocked_ops: state.ops,
        test_level: state.testLevel,
        tests_passed: state.testsPassed,
        stats: state.stats,
        play_time: state.playTime,
        saved_at: Date.now()
      }));
    } catch (e) { /* приватный режим — молча играем без сохранения */ }
  }

  // ---------------------------------------------------------------- helpers
  function passiveRate() {
    var total = 0;
    for (var i = 0; i < B.base_upgrades.length; i++) {
      var up = B.base_upgrades[i];
      total += (state.base[up.id] || 0) * up.rate_per_level;
    }
    return total;
  }

  function topOperation() {
    var last = "add";
    for (var i = 0; i < B.operations.length; i++) {
      if (state.ops.indexOf(B.operations[i].id) >= 0) last = B.operations[i].id;
    }
    return last;
  }

  function maxLevelOf(up) { return Math.round(up.max_rate / up.rate_per_level); }
  function shopUnlocked() { return state.testsPassed >= 1; }

  function manualDifficulty() { return Math.min(0.75, 0.2 + 0.07 * (state.testLevel - 1)); }

  function nextProblem() {
    if (state.test && !state.test.finished) {
      state.current = state.test.problems[state.test.index];
    } else {
      state.current = randomProblem(state.ops, manualDifficulty());
    }
    state.shownAt = state.clock;
    return state.current;
  }

  function log(text, kind, ttl) {
    ui.log(text, kind, ttl || 4.5);
  }

  // ------------------------------------------------------------- покупки
  function upgradeCostOf(id) { return upgradeCost(baseUpgrade(id), state.base[id] || 0); }
  function upgradeFull(id) { return (state.base[id] || 0) >= maxLevelOf(baseUpgrade(id)); }

  function buyUpgrade(id) {
    if (upgradeFull(id)) return false;
    var cost = upgradeCostOf(id);
    if (state.money < cost) return false;
    state.money -= cost;
    state.base[id] += 1;
    var up = baseUpgrade(id);
    log(up.name + ": уровень " + state.base[id] + " (+" + up.rate_per_level + " примера/с)", "buy");
    return true;
  }

  function buyAllUpgrades() {
    var bought = 0, spent = 0, guard = 0;
    while (guard++ < 200) {
      var best = null, bestCost = Infinity;
      for (var i = 0; i < B.base_upgrades.length; i++) {
        var id = B.base_upgrades[i].id;
        if (upgradeFull(id)) continue;
        var c = upgradeCostOf(id);
        if (c < bestCost) { bestCost = c; best = id; }
      }
      if (!best || state.money < bestCost) break;
      state.money -= bestCost; spent += bestCost; state.base[best] += 1; bought++;
    }
    if (bought) log("Куплено улучшений: " + bought + " на " + fmtMoney(spent), "buy");
    return bought;
  }

  function buyGrade(id) {
    if (!shopUnlocked()) return false;
    var item = gradeItem(id);
    if ((state.grade[id] || 0) >= item.max_level) return false;
    var cost = gradeCost(item, state.grade[id] || 0);
    if (state.money < cost) return false;
    state.money -= cost;
    state.grade[id] = (state.grade[id] || 0) + 1;
    if (item.effect === "unlock") {
      if (state.ops.indexOf(item.operation) < 0) state.ops.push(item.operation);
      log("Открыто действие «" + operation(item.operation).name + "»!", "unlock");
    } else {
      log(item.name + ": уровень " + state.grade[id], "buy");
    }
    return true;
  }

  // ------------------------------------------------------------- контрольная
  function startTest() {
    if (state.test) return false;
    if (state.money < T.entry_price) return false;
    state.money -= T.entry_price;
    var level = state.testLevel;
    var count = testProblemCount(level), diff = testDifficulty(level);
    var problems = [];
    for (var i = 0; i < count; i++) problems.push(randomProblem(state.ops, diff));
    state.test = {
      level: level, problems: problems, index: 0,
      limit: testTimeLimit(level), startedAt: state.clock,
      elapsed: 0, finished: false, passed: false
    };
    nextProblem();
    log("Контрольная №" + level + ": " + count + " примеров на " + fmtTime(state.test.limit), "test");
    return true;
  }

  function passTest() {
    var bonus = testReward(state.test.level);
    state.money += bonus;
    state.stats.earned += bonus;
    state.stats.tests_passed += 1;
    state.testsPassed += 1;
    var level = state.test.level;
    var spare = state.test.limit - state.test.elapsed;
    var first = state.stats.tests_passed === 1;
    state.test = null;
    state.testLevel = level + 1;
    log("Контрольная №" + level + " сдана! +" + fmtMoney(bonus) +
      (first ? " Открыт магазин контрольных улучшений!" : ""), first ? "unlock" : "pass");
    return { passed: true, level: level, bonus: bonus, spare: spare, shopUnlocked: first };
  }

  function failTest(reason) {
    var refund = T.entry_price * T.fail_refund;
    var level = state.test ? state.test.level : state.testLevel;
    state.money += refund;
    state.test = null;
    state.combo = 0;
    var text = reason === "time" ? "Время вышло!" : "Ошибка в контрольной";
    log(text + " Контрольная №" + level + " провалена, билет возвращён", "fail");
    return { passed: false, level: level, refund: refund, reason: reason || "wrong" };
  }

  function abortTest() {
    if (!state.test || state.test.finished) return null;
    return failTest("abort");
  }

  // ------------------------------------------------------------- ответы
  function submit(text) {
    var raw = (text || "").trim().replace(",", ".");
    if (!state.current) nextProblem();
    var value = Number(raw);
    if (raw === "" || isNaN(value)) {
      state.stats.wrong += 1; state.combo = 0;
      return { ok: false, reason: raw === "" ? "empty" : "parse" };
    }
    var expected = state.current.answer;
    var elapsed = state.clock - state.shownAt;
    if (value !== expected) {
      state.stats.wrong += 1; state.combo = 0;
      var res = { ok: false, reason: "wrong", expected: expected };
      if (state.test) res.test = failTest("wrong");
      return res;
    }
    state.stats.solved += 1;
    state.combo += 1;
    state.stats.best_streak = Math.max(state.stats.best_streak, state.combo);
    state.lastCorrectAt = state.clock;
    var amount = reward(state.current.op, state.current.difficulty, elapsed, state.combo - 1);
    state.money += amount;
    state.stats.earned += amount;

    var out = { ok: true, amount: amount, elapsed: elapsed, combo: state.combo, speed: speedFactor(elapsed) };
    if (state.test && !state.test.finished) {
      state.test.index += 1;
      if (state.test.index >= state.test.problems.length) out.test = passTest();
      else nextProblem();
    } else {
      nextProblem();
    }
    return out;
  }

  function wantsHint() {
    var every = hintEvery();
    return every > 0 && state.current && state.stats.solved > 0 && state.stats.solved % every === 0;
  }

  // ------------------------------------------------------------------- тик
  function tick() {
    var t = nowSec();
    var dt = Math.min(0.5, Math.max(0, t - state.lastTick));
    state.lastTick = t;
    state.clock += dt;
    state.playTime += dt;

    var rate = passiveRate();
    if (rate > 0) {
      var gain = rate * dt * passiveReward(topOperation());
      state.money += gain;
      state.stats.idle_examples += rate * dt;
    }
    if (state.combo && state.clock - state.lastCorrectAt > R.combo_decay) state.combo = 0;
    if (state.test) {
      state.test.elapsed = state.clock - state.test.startedAt;
      if (state.test.elapsed >= state.test.limit) {
        var failed = failTest("time");
        ui.showModal(failed);
        ui.renderAll();
      }
    }

    saveTimer += dt;
    if (saveTimer >= B.game.autosave_seconds) { saveTimer = 0; save(); }
  }

  // --------------------------------------------------------------------- UI
  var ui = (function () {
    var el = {};
    function byId(id) { return document.getElementById(id); }

    var input = "";
    var tab = "upgrades";
    var floaters = [];

    var KIND_COLORS = {
      buy: "var(--accent)", unlock: "var(--gold)", pass: "var(--green)",
      fail: "var(--red)", test: "var(--blue)", info: "var(--muted)"
    };

    var events = [];

    function cache() {
      ["money", "passive", "passiveHint", "mult", "combo", "playTitle", "playHint", "timerWrap",
        "timerBar", "timerText", "testProgress", "problem", "diffBar", "diffText", "answer",
        "answerText", "floaters", "log", "panel", "modal", "modalTitle", "modalBody", "modalClose",
        "tabGrades", "app"].forEach(function (id) { el[id] = byId(id); });
    }

    function flash(kind) {
      el.app.classList.remove("flash-ok", "flash-bad");
      void el.app.offsetWidth;
      el.app.classList.add(kind === "ok" ? "flash-ok" : "flash-bad");
    }

    function log(text, kind, ttl) {
      events.push({ text: text, kind: kind, born: state.clock, ttl: ttl || 4.5 });
      if (events.length > 4) events.shift();
      renderLog();
    }

    function renderLog() {
      var now = state.clock;
      events = events.filter(function (e) { return now - e.born < e.ttl; });
      el.log.innerHTML = events.map(function (e) {
        var left = e.ttl - (now - e.born);
        return '<div style="color:' + (KIND_COLORS[e.kind] || "var(--text)") +
          ';opacity:' + Math.min(1, left).toFixed(2) + '">' + e.text + "</div>";
      }).join("");
    }

    function floater(text, color) {
      var d = document.createElement("div");
      d.className = "floater";
      d.textContent = text;
      d.style.color = color;
      d.style.top = (-30 - floaters.length * 26) + "px";
      el.floaters.appendChild(d);
      floaters.push(d);
      setTimeout(function () {
        if (d.parentNode) d.parentNode.removeChild(d);
        floaters = floaters.filter(function (x) { return x !== d; });
      }, 1100);
    }

    function renderTop() {
      var rate = passiveRate();
      el.money.textContent = fmtMoney(state.money);
      el.passive.textContent = "+" + fmtMoney(rate * passiveReward(topOperation())) + "/с";
      el.passiveHint.textContent = fmtRate(rate) + " примера/с";
      el.mult.textContent = "×" + moneyMult().toFixed(1);
      el.combo.textContent = state.combo > 1 ? "серия " + state.combo : "";
    }

    function renderPlay() {
      var testing = !!state.test;
      el.playTitle.textContent = testing
        ? "Контрольная №" + state.test.level + " · пример " + (state.test.index + 1) +
          " из " + state.test.problems.length
        : "Реши пример";
      el.playTitle.style.color = testing ? "var(--blue)" : "var(--muted)";

      if (testing) {
        var left = Math.max(0, state.test.limit - state.test.elapsed);
        var k = left / Math.max(1e-6, state.test.limit);
        el.timerWrap.classList.remove("hidden");
        el.timerBar.style.width = (k * 100).toFixed(1) + "%";
        el.timerBar.style.background = k < 0.25 ? "var(--red)" : (k < 0.5 ? "var(--gold)" : "var(--green)");
        el.timerText.textContent = "осталось " + fmtTime(left);
        el.testProgress.textContent = state.test.index + "/" + state.test.problems.length;
      } else {
        el.timerWrap.classList.add("hidden");
      }

      el.playHint.textContent = wantsHint() ? "шпаргалка" : "";
      el.playHint.classList.toggle("hidden", !wantsHint());

      if (state.current) {
        el.problem.textContent = state.current.text + " =";
        var d = state.current.difficulty;
        el.diffBar.style.width = (d * 100).toFixed(0) + "%";
        el.diffBar.style.background = d < 0.35 ? "var(--green)" : (d < 0.6 ? "var(--gold)" : "var(--red)");
        el.diffText.textContent = "сложность " + Math.round(d * 100) + "%";
      }

      el.answerText.textContent = input ? input : "…";
      el.answerText.style.color = input ? "var(--text)" : "var(--muted)";
      el.answer.classList.toggle("active", !!input);
    }

    function renderPanel() {
      var html = "";
      if (tab === "upgrades") html = panelUpgrades();
      else if (tab === "test") html = panelTest();
      else html = panelGrades();
      el.panel.innerHTML = html;
      bindPanel();
      el.tabGrades.disabled = !shopUnlocked();
    }

    function panelUpgrades() {
      var rate = passiveRate();
      var out = '<div class="small" style="margin-bottom:8px">Сейчас: ' + fmtRate(rate) +
        " примера/с · " + fmtMoney(rate * passiveReward(topOperation())) + "/с</div>";
      for (var i = 0; i < B.base_upgrades.length; i++) {
        var up = B.base_upgrades[i];
        var level = state.base[up.id] || 0;
        var maxl = maxLevelOf(up);
        var full = level >= maxl;
        var cost = upgradeCostOf(up.id);
        var afford = !full && state.money >= cost;
        var sub = full
          ? "максимум " + up.max_rate + " примера/с"
          : "+" + up.rate_per_level + " примера/с · ур. " + level + "/" + maxl +
            " · цена: " + fmtMoney(cost);
        out += '<button class="item' + (afford ? " affordable" : "") + '" data-buy="' + up.id + '"' +
          (full ? " disabled" : "") + '>' +
          '<div class="name">' + up.name + "</div>" +
          '<div class="sub">' + sub + "</div>" +
          '<div class="price">' + (full ? "МАКС" : fmtMoney(cost)) + "</div>" +
          '<div class="prog"><i style="width:' + ((level * up.rate_per_level / up.max_rate) * 100).toFixed(0) + '%"></i></div>' +
          "</button>";
      }
      out += '<button class="item affordable" data-buyall="1" style="border-color:var(--blue)">' +
        '<div class="name" style="color:var(--blue)">Купить максимум</div>' +
        '<div class="sub">всё, что позволяет баланс</div></button>';
      return out;
    }

    function panelTest() {
      if (state.test) {
        return '<div class="info-card">' +
          '<h3>Контрольная №' + state.test.level + " идёт</h3>" +
          '<div class="line"><span>Пример</span><span>' + (state.test.index + 1) + " из " +
          state.test.problems.length + "</span></div>" +
          '<div class="line"><span>Осталось</span><span>' +
          fmtTime(state.test.limit - state.test.elapsed) + "</span></div>" +
          '<div class="line"><span>Награда</span><span>' + fmtMoney(testReward(state.test.level)) + "</span></div>" +
          '<button class="big-btn danger" data-abort="1">Прервать (вернуть билет)</button>' +
          "</div>" + rulesHtml();
      }
      var level = state.testLevel;
      var can = state.money >= T.entry_price;
      return '<div class="info-card">' +
        "<h3>Контрольная</h3>" +
        '<div class="line"><span>Билет</span><span>' + fmtMoney(T.entry_price) + "</span></div>" +
        '<div class="line"><span>Примеров</span><span>' + testProblemCount(level) + "</span></div>" +
        '<div class="line"><span>Сложность</span><span>' +
        Math.round(testDifficulty(level) * 100) + "%</span></div>" +
        '<div class="line"><span>Время</span><span>' + fmtTime(testTimeLimit(level)) + "</span></div>" +
        '<div class="line"><span>Награда</span><span>' + fmtMoney(testReward(level)) + "</span></div>" +
        '<div class="line"><span>Пройдено</span><span>' + state.testsPassed + "</span></div>" +
        '<button class="big-btn" data-start="1"' + (can ? "" : " disabled") + ">" +
        (can ? "Начать контрольную" : "Нужно " + fmtMoney(T.entry_price)) + "</button>" +
        "</div>" + rulesHtml();
    }

    function rulesHtml() {
      return '<div class="rules"><b>Правила контрольной:</b><br>' +
        "• ни одной ошибки, иначе провал (билет возвращается)<br>" +
        "• не уложишься во время — тоже провал<br>" +
        "• сдаёшь — награда и следующий уровень<br><br>" +
        "После первой сданной контрольной открывается магазин контрольных улучшений: " +
        "множители денег, более широкое окно скорости и новые математические действия.</div>";
    }

    function panelGrades() {
      if (!shopUnlocked()) return '<div class="info-card"><h3>Магазин закрыт</h3>' +
        '<div class="rules">Сдай первую контрольную — и здесь появятся контрольные улучшения: ' +
        "множители денег, ускорение и новые математические действия.</div></div>";
      var out = '<div class="small" style="margin-bottom:4px">Улучшения за деньги, полученные на контрольных.</div>';
      for (var i = 0; i < B.grade_items.length; i++) {
        var item = B.grade_items[i];
        var level = state.grade[item.id] || 0;
        var full = level >= item.max_level;
        var cost = gradeCost(item, level);
        var isUnlock = item.effect === "unlock";
        var already = isUnlock && state.ops.indexOf(item.operation) >= 0;
        var afford = !full && !already && state.money >= cost;
        var cls = isUnlock ? "gold" : "violet";
        var badge = isUnlock ? (already ? "ЕСТЬ" : fmtMoney(cost)) : (full ? "МАКС" : fmtMoney(cost));
        var sub;
        if (isUnlock) sub = already ? "уже открыто" : item.desc;
        else sub = (full ? "максимум" : "ур. " + level + "/" + item.max_level) + " · " + item.desc;
        out += '<button class="item ' + cls + (afford ? " affordable" : "") + '" data-grade="' + item.id + '"' +
          (full || already ? " disabled" : "") + ">" +
          '<div class="name">' + item.name + "</div>" +
          '<div class="sub">' + sub + "</div>" +
          '<div class="price">' + badge + "</div></button>";
      }
      return out;
    }

    function bindPanel() {
      var nodes = el.panel.querySelectorAll("[data-buy]");
      for (var i = 0; i < nodes.length; i++) {
        nodes[i].onclick = function () {
          if (buyUpgrade(this.getAttribute("data-buy"))) { flash("ok"); renderAll(); }
        };
      }
      var all = el.panel.querySelector("[data-buyall]");
      if (all) all.onclick = function () {
        var n = buyAllUpgrades();
        flash(n ? "ok" : "bad");
        renderAll();
      };
      var grades = el.panel.querySelectorAll("[data-grade]");
      for (var j = 0; j < grades.length; j++) {
        grades[j].onclick = function () {
          if (buyGrade(this.getAttribute("data-grade"))) { flash("ok"); renderAll(); }
        };
      }
      var start = el.panel.querySelector("[data-start]");
      if (start) start.onclick = function () {
        if (startTest()) { input = ""; tab = "upgrades"; syncTabs(); renderAll(); }
      };
      var abort = el.panel.querySelector("[data-abort]");
      if (abort) abort.onclick = function () {
        var res = abortTest();
        if (res) { showModal(res); renderAll(); }
      };
    }

    function syncTabs() {
      var tabs = document.querySelectorAll(".tabs button");
      for (var i = 0; i < tabs.length; i++) {
        tabs[i].classList.toggle("active", tabs[i].getAttribute("data-tab") === tab);
      }
    }

    function showModal(res) {
      var title, lines, fail;
      if (res.passed) {
        title = "Сдано!";
        lines = ["Контрольная №" + res.level + " сдана",
          "Награда: +" + fmtMoney(res.bonus),
          "Осталось времени: " + fmtTime(res.spare)];
        if (res.shopUnlocked) lines.push("Открыт магазин контрольных улучшений!");
        fail = false;
      } else {
        var reasons = { time: "Время вышло", abort: "Контрольная прервана", wrong: "Ошибка в примере" };
        title = reasons[res.reason] || "Провал";
        lines = ["Контрольная №" + res.level + " не засчитана", "Билет возвращён"];
        fail = true;
      }
      el.modalTitle.textContent = title;
      el.modalBody.innerHTML = lines.map(function (l) { return '<div class="mline">' + l + "</div>"; }).join("");
      el.modal.querySelector(".modal-card").classList.toggle("fail", fail);
      el.modal.classList.remove("hidden");
    }

    function pressKey(key) {
      if (key === "ok") { pressEnter(); return; }
      if (key === "del") input = input.slice(0, -1);
      else if (input.length < 8) input += key;
      renderPlay();
    }

    function pressEnter() {
      if (!input) return;
      var res = submit(input);
      input = "";
      if (res.ok) {
        floater("+" + fmtMoney(res.amount), "var(--gold)");
        if (res.speed >= 0.999) floater("мгновенно!", "var(--accent)");
        else if (res.combo >= 3) floater("серия ×" + res.combo, "var(--blue)");
        flash("ok");
      } else {
        floater("ответ: " + res.expected, "var(--red)");
        flash("bad");
      }
      if (res.test) showModal(res.test);
      renderAll();
    }

    function onKey(e) {
      var k = e.key;
      if (!el.modal.classList.contains("hidden")) {
        if (k === "Enter" || k === "Escape" || k === " ") el.modal.classList.add("hidden");
        e.preventDefault();
        return;
      }
      if (k >= "0" && k <= "9") { pressKey(k); e.preventDefault(); }
      else if (k === "-" || k === "," || k === ".") { pressKey("-"); e.preventDefault(); }
      else if (k === "Backspace") { pressKey("del"); e.preventDefault(); }
      else if (k === "Delete") { input = ""; renderPlay(); e.preventDefault(); }
      else if (k === "Enter") { pressEnter(); e.preventDefault(); }
      else if (k === "Tab") {
        var order = ["upgrades", "test", "grades"], i = order.indexOf(tab);
        tab = order[(i + 1) % order.length];
        if (tab === "grades" && !shopUnlocked()) tab = "upgrades";
        syncTabs(); renderPanel();
        e.preventDefault();
      }
    }

    function init() {
      cache();

      var keys = document.querySelectorAll(".keypad button");
      for (var i = 0; i < keys.length; i++) {
        (function (btn) {
          btn.addEventListener("click", function () { pressKey(btn.getAttribute("data-key")); });
        })(keys[i]);
      }

      var tabs = document.querySelectorAll(".tabs button");
      for (var j = 0; j < tabs.length; j++) {
        (function (btn) {
          btn.addEventListener("click", function () {
            var t = btn.getAttribute("data-tab");
            if (t === "grades" && !shopUnlocked()) return;
            tab = t;
            syncTabs();
            renderPanel();
          });
        })(tabs[j]);
      }

      el.modalClose.addEventListener("click", function () { el.modal.classList.add("hidden"); });
      el.modal.addEventListener("click", function (e) {
        if (e.target === el.modal) el.modal.classList.add("hidden");
      });
      document.addEventListener("keydown", onKey);
      window.addEventListener("beforeunload", save);
      document.addEventListener("visibilitychange", function () {
        if (document.hidden) save();
      });
      syncTabs();
    }

    function renderAll() {
      renderTop();
      renderPlay();
      renderPanel();
      renderLog();
    }

    return {
      init: init, log: log, renderAll: renderAll, showModal: showModal, flash: flash,
      inputValue: function () { return input; }
    };
  })();

  // ------------------------------------------------------------------ старт
  function boot() {
    ui.init();
    var saved = load();
    if (saved) applyOffline(saved.saved_at);
    nextProblem();
    if (earnedOffline > 0) {
      ui.log("Пока тебя не было " + fmtTime(awayTime) + ", пассивные примеры заработали " +
        fmtMoney(earnedOffline), "info", 8);
    }
    ui.renderAll();
    setInterval(tick, 1000 / 30);
    setInterval(save, 15000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
