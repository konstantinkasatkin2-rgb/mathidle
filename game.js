/* Math Idle — HTML5/JS-порт pygame-версии.
 *
 * Баланс приходит из balance.js (выгружается из mathidle/config.py скриптом
 * tools/export_balance.py), поэтому обе версии считают деньги одинаково.
 * Правки баланса делаются только в Python-конфиге.
 */
(function () {
  "use strict";

  var B = window.MATHIDLE_BALANCE;
  var R = B.rewards, T = B.test, P = B.prestige, ASC = B.ascension;
  var SETTINGS_KEY = "mathidle.save";

  // ---------------------------------------------------------------- utils
  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function nowSec() { return Date.now() / 1000; }

  function mulberry32(seed) {
    return function () {
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  var rng = mulberry32(0x9E3779B9);

  function rndInt(a, b) { return a + Math.floor(rng() * (b - a + 1)); }
  function pick(list) { return list[Math.floor(rng() * list.length)]; }
  function shuffle(list) {
    for (var i = list.length - 1; i > 0; i--) {
      var j = Math.floor(rng() * (i + 1));
      var tmp = list[i]; list[i] = list[j]; list[j] = tmp;
    }
    return list;
  }
  function sample(list, count) { return shuffle(list.slice()).slice(0, count); }

  function operation(id) { return findBy(B.operations, "id", id); }
  function baseUpgrade(id) { return findBy(B.base_upgrades, "id", id); }
  function gradeItem(id) { return findBy(B.grade_items, "id", id); }
  function prestigeItem(id) { return findBy(B.prestige_items, "id", id); }
  function testType(id) { return findBy(B.test_types, "id", id); }
  function settingDef(id) { return findBy(B.display_settings, "id", id); }

  function findBy(list, key, value) {
    for (var i = 0; i < list.length; i++) if (list[i][key] === value) return list[i];
    throw new Error("не найдено: " + key + "=" + value);
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
    if (Math.abs(v) < 1e-5) return v.toExponential(2).replace("e-", "e−");
    if (Math.abs(v) < 1) return v.toFixed(4);
    if (Math.abs(v - Math.round(v)) < 1e-9 && Math.abs(v) < 1000) return String(Math.round(v));
    return v.toFixed(state.settings.precise_money ? 4 : 3);
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
    var text = [], sum = 0;
    for (var i = 0; i < terms; i++) {
      var n = rndInt(1, hi);
      text.push(String(n));
      sum += n;
    }
    return { text: text.join(" + "), answer: sum };
  }

  function genSub(diff) {
    var hi = Math.max(8, Math.round(9 + 90 * diff));
    var a = rndInt(Math.max(4, Math.floor(hi / 2)), hi);
    var b = rndInt(1, Math.max(1, a - 1));
    return { text: a + " - " + b, answer: a - b };
  }

  function genMul(diff) {
    var hi = Math.max(5, Math.round(6 + 19 * diff));
    var a = rndInt(2, hi), b = rndInt(2, hi);
    return { text: a + " × " + b, answer: a * b };
  }

  function genDiv(diff) {
    var hiB = Math.max(3, Math.round(3 + 9 * diff));
    var hiQ = Math.max(4, Math.round(5 + 20 * diff));
    var b = rndInt(2, hiB), q = rndInt(2, hiQ);
    return { text: (b * q) + " ÷ " + b, answer: q };
  }

  function atomic(diff, hi) {
    var roll = rng();
    if (roll < 0.30) {
      var a = rndInt(2, hi), b = rndInt(2, hi);
      return { text: a + " × " + b, value: a * b };
    }
    if (roll < 0.48) {
      var d = rndInt(2, Math.max(3, Math.floor(hi / 2)));
      var q = rndInt(2, Math.max(3, Math.floor(hi / 2)));
      return { text: (d * q) + " ÷ " + d, value: q };
    }
    var n = rndInt(1, hi + 4);
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

  /* Смешанный пример: куски, первый без знака. Каждый кусок — законченное
   * выражение, поэтому «6 × 5 + 7 × 2» = 30 + 14, а не случайная цепочка. */
  function genMix(diff) {
    var hiSmall = Math.max(5, Math.round(5 + 15 * diff));
    var hiBig = Math.max(4, Math.round(4 + 9 * diff));
    var chunks = [];

    function piecePlus() {
      var n = rndInt(1, hiSmall + 4);
      chunks.push({ sign: "+", text: String(n), value: n });
    }
    function pieceMinus() {
      var n = rndInt(1, hiSmall + 4);
      var running = 0;
      for (var i = 0; i < chunks.length; i++) {
        running += chunks[i].sign === "+" ? chunks[i].value : -chunks[i].value;
      }
      chunks.push({ sign: running - n >= 0 ? "-" : "+", text: String(n), value: n });
    }
    function pieceMul() {
      var a = rndInt(2, hiBig), b = rndInt(2, hiBig);
      chunks.push({ sign: "+", text: a + " × " + b, value: a * b });
    }
    function pieceDiv() {
      var b = rndInt(2, Math.max(3, hiBig)), q = rndInt(2, Math.max(3, hiBig + 2));
      chunks.push({ sign: "+", text: (b * q) + " ÷ " + b, value: q });
    }

    // умножение и деление видны в строке всегда — два разных действия гарантированы
    var order = rng() < 0.5 ? [pieceMul, pieceDiv] : [pieceDiv, pieceMul];
    var count = diff < 0.6 ? 2 : (diff < 0.85 ? 3 : 4);
    if (count > 2) order.push(piecePlus);
    if (count > 3) order.push(rng() < 0.5 ? pieceMinus : piecePlus);
    shuffle(order);
    for (var i = 0; i < order.length; i++) order[i]();

    var text = chunks[0].text, total = chunks[0].value;
    for (var k = 1; k < chunks.length; k++) {
      text += " " + chunks[k].sign + " " + chunks[k].text;
      total += chunks[k].sign === "+" ? chunks[k].value : -chunks[k].value;
    }
    return { text: text, answer: total };
  }

  var GENERATORS = {
    add: genAdd, sub: genSub, mul: genMul, div: genDiv, expr: genExpr, mix: genMix
  };

  function generate(opId, difficulty) {
    var diff = clamp(difficulty, 0, 1);
    var res = GENERATORS[opId](diff, operation(opId));
    return { text: res.text, answer: Math.round(res.answer), op: opId, difficulty: diff };
  }

  function randomProblem(opIds, difficulty) {
    if (!opIds || !opIds.length) opIds = ["add"];
    return generate(pick(opIds), difficulty);
  }

  /** Набор примеров для контрольной: обычная берёт две случайные операции. */
  function testProblemsFor(typeId, opIds, difficulty, count) {
    var tt = testType(typeId);
    var pool = (opIds && opIds.length) ? opIds : ["add"];
    var chosen = (tt.ops_mode === "two" && pool.length > 1) ? sample(pool, 2) : pool;
    var out = [];
    for (var i = 0; i < count; i++) out.push(generate(pick(chosen), difficulty));
    return { problems: out, ops: chosen };
  }

  // ------------------------------------------------------------- экономика
  function upgradeCost(up, level) {
    var n = level + 1;                       // арифметическая прогрессия a1 + (n−1)·d
    return up.cost_start + up.cost_step * (n - 1);
  }

  function ascensionRateMultiplier(n) { return Math.pow(ASC.rate_multiplier, Math.max(0, n)); }
  function ascensionCostMultiplier(n) { return Math.pow(ASC.cost_multiplier, Math.max(0, n)); }

  function gradeCost(item, level) {
    return item.price * Math.pow(item.growth == null ? 1 : item.growth, level);
  }

  function prestigeCost(item, level) {
    var discount = item.discount || 0;
    return round6(item.price * (1 - discount) + (item.step || 0) * level);
  }

  function prestigeEffectTotal(effect) {
    var total = 0;
    for (var i = 0; i < B.prestige_items.length; i++) {
      var it = B.prestige_items[i];
      if (it.effect === effect) total += it.per_level * (state.prestige[it.id] || 0);
    }
    return total;
  }

  function gradeEffectTotal(effect) {
    var total = 0;
    for (var i = 0; i < B.grade_items.length; i++) {
      var it = B.grade_items[i];
      if (it.effect === effect) total += it.per_level * (state.grade[it.id] || 0);
    }
    return total;
  }

  function round6(v) { return Math.round(v * 1e6) / 1e6; }

  function moneyMult() {
    return 1 + gradeEffectTotal("money_mult") + prestigeEffectTotal("money_mult");
  }
  function speedMult() {
    return 1 + gradeEffectTotal("speed_window") + prestigeEffectTotal("speed_window");
  }
  function addMult() { return 1 + gradeEffectTotal("add_bonus"); }
  function passiveMult() {
    return 1 + gradeEffectTotal("passive_share") + prestigeEffectTotal("passive_share");
  }
  function keepMoneyShare() { return prestigeEffectTotal("keep_money"); }

  function hintEvery() {
    var levels = gradeEffectTotal("hint_every");
    return levels <= 0 ? 0 : Math.max(4, Math.floor(10 / levels));
  }

  function difficultyFactor(d) { return 1 - (1 - R.diff_floor) * clamp(d, 0, 1); }

  function speedFactor(elapsed) {
    var mult = speedMult();
    var fast = R.fast_window * mult, slow = R.slow_window * mult;
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

  function prestigePoints(earned) {
    return earned * P.points_per_money * (1 + prestigeEffectTotal("prestige_gain"));
  }

  function testReward(level, typeId) {
    var tt = testType(typeId || "test");
    return (T.pass_bonus + T.pass_bonus_per_level * (level - 1)) * tt.reward_mult;
  }

  function testProblemCount(level, typeId) {
    var tt = testType(typeId || "test");
    var base = Math.min(T.max_problems, T.base_problems + T.problems_per_level * (level - 1));
    return Math.max(1, Math.round(base * tt.problems_mult));
  }

  function testDifficulty(level, typeId) {
    var tt = testType(typeId || "test");
    var base = T.diff_base + T.diff_per_level * (level - 1);
    return Math.min(T.diff_max, base + tt.diff_bonus + prestigeEffectTotal("test_difficulty"));
  }

  function testPrice(typeId) { return testType(typeId || "test").price; }

  function testTimeLimit(level, typeId) {
    var tt = testType(typeId || "test");
    var count = testProblemCount(level, typeId);
    var base = (T.base_time + T.time_per_problem * count) * tt.time_mult +
      gradeEffectTotal("test_time");
    return base * (1 + prestigeEffectTotal("test_time"));
  }

  // ---------------------------------------------------------------- аккаунт
  var account = {
    url: null, username: null, token: null, lastError: null, customUrl: "",
    discovered: [],          // адреса, найденные приложением в локальной сети

    /** Адреса, которые пробуем по очереди: заданный игроком, потом дефолтные. */
    candidateUrls: function () {
      var list = [];
      var custom = (state.serverUrl || "").trim() || (window.MATHIDLE_SERVER || "");
      if (custom) list.push(custom);
      // то, что нашлось в сети, важнее 127.0.0.1: на телефоне 127.0.0.1 —
      // это сам телефон, а не компьютер с игрой
      for (var k = 0; k < this.discovered.length; k++) list.push(this.discovered[k]);
      var def = B.account.default_url || "";
      if (def) list.push(def);
      else {
        var ports = B.account.fallback_ports || [8766];
        for (var i = 0; i < ports.length; i++) list.push("http://127.0.0.1:" + ports[i]);
      }
      var seen = {}, out = [];
      for (var j = 0; j < list.length; j++) {
        var clean = String(list[j]).replace(/\/+$/, "");
        if (clean && !seen[clean]) { seen[clean] = 1; out.push(clean); }
      }
      return out;
    },

    /**
     * В приложении на Android сервер аккаунтов ищется сам: нативная часть
     * спрашивает по UDP, кто отвечает в сети, и передаёт адреса сюда.
     * В браузере этого нет — остаётся поле в настройках.
     */
    discover: function (attempt) {
      var self = this;
      attempt = attempt || 0;
      if (window.MathIdleNative && typeof window.MathIdleNative.findServers === "function") {
        window.MathIdleNativeServers = function (urls) {
          self.discovered = urls || [];
          if (self.discovered.length && !state.serverUrl) {
            // запоминаем находку, чтобы не искать каждый раз
            state.serverUrl = self.discovered[0];
            save();
          }
          if (activeTab() === "settings") renderAll();
        };
        try {
          window.MathIdleNative.findServers();
        } catch (err) {
          // мост не ответил — работаем на введённый вручную адрес
        }
        return true;
      }
      // Моста пока нет: в приложении он появляется сразу, но на всякий
      // случай пробуем ещё несколько раз.
      if (attempt < 6) {
        setTimeout(function () { self.discover(attempt + 1); }, 500);
      }
      return false;
    },

    signedIn: function () { return !!(this.token && this.username); },

    status: function () { return this.url || "(не подключено)"; },

    /** Страница по HTTPS не может ходить на HTTP — это ловится заранее. */
    isMixedContent: function (base) {
      if (!/^https:/i.test(window.location.protocol)) return false;
      return /^http:/i.test(String(base));
    },

    request: function (path, method, payload, token) {
      var base = this.url || this.candidateUrls()[0];
      if (this.isMixedContent(base)) {
        var blocked = new Error("HTTPS-страница не может обратиться к http-серверу. " +
          B.account.https_required_hint);
        blocked.mixed = true;
        return Promise.reject(blocked);
      }
      var opts = { method: method || "GET", headers: { Accept: "application/json" } };
      if (payload !== undefined && payload !== null) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(payload);
      }
      if (token) opts.headers["Authorization"] = "Bearer " + token;
      var self = this;
      return fetch(base + path, opts).then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          if (!response.ok) {
            var err = new Error(data.error || ("HTTP " + response.status));
            err.httpStatus = response.status;
            err.serverSaid = true;
            throw err;
          }
          return data;
        });
      }).catch(function (err) {
        // fetch падает целиком: сеть, CORS, mixed content, не тот адрес
        if (err && err.serverSaid) throw err;
        var message = err && err.message ? err.message : "сеть недоступна";
        if (/failed to fetch|networkerror|load failed/i.test(message)) {
          var hint = self.isMixedContent(base)
            ? B.account.https_required_hint
            : "Проверьте, что сервер аккаунтов запущен (bash tools/serve_accounts.sh) " +
              "и что адрес доступен с этого устройства.";
          var wrapped = new Error("Сервер не отвечает. " + hint);
          wrapped.unreachable = true;
          throw wrapped;
        }
        var net = new Error("Сервер не отвечает: " + message);
        net.unreachable = true;
        throw net;
      });
    },

    /** Перебирает адреса только пока сервер не отвечает.
     *  Логический ответ («неверный пароль») — повод не искать другой адрес. */
    tryUrls: function (path, method, payload, token) {
      var bases = this.candidateUrls();
      var self = this;
      var lastError = null;
      function attempt(index) {
        if (index >= bases.length) {
          return Promise.reject(lastError || new Error("Сервер недоступен"));
        }
        self.url = bases[index];
        return self.request(path, method, payload, token).catch(function (err) {
          lastError = err;
          if (err && (err.serverSaid || err.mixed)) throw err;
          return attempt(index + 1);
        });
      }
      return attempt(0).catch(function (err) {
        self.lastError = err && err.message ? err.message : "сервер недоступен";
        var wrapped = new Error(self.lastError);
        wrapped.unreachable = !!(err && err.unreachable);
        wrapped.serverSaid = !!(err && err.serverSaid);
        wrapped.mixed = !!(err && err.mixed);
        throw wrapped;
      });
    },

    register: function (username, password) {
      var self = this;
      return this.tryUrls("/api/register", "POST", { username: username, password: password })
        .then(function (data) { self.username = data.username || username; self.token = data.token; });
    },

    login: function (username, password) {
      var self = this;
      return this.tryUrls("/api/login", "POST", { username: username, password: password })
        .then(function (data) { self.username = data.username || username; self.token = data.token; });
    },

    logout: function () { this.username = null; this.token = null; },

    downloadSave: function () {
      return this.tryUrls("/api/save", "GET", null, this.token);
    },

    uploadSave: function (save) {
      return this.tryUrls("/api/save", "PUT", { save: save }, this.token);
    }
  };

  // ----------------------------------------------------------------- state
  var state = {
    money: 0,
    runEarned: 0,
    base: {},
    ascensions: {},
    grade: {},
    prestige: {},
    prestigePoints: 0,
    prestigeCount: 0,
    ops: ["add"],
    testLevel: 1,
    testsPassed: 0,
    combo: 0,
    lastCorrectAt: 0,
    playTime: 0,
    maxDifficulty: 0,
    stats: { solved: 0, wrong: 0, earned: 0, passive_earned: 0, prestige_points_total: 0,
             tests_passed: 0, idle_examples: 0, best_streak: 0, ascensions: 0, femboy: false },
    settings: {},
    serverUrl: "",          // адрес сервера аккаунтов (настраивается в «Настройках»)
    current: null,
    shownAt: 0,
    test: null,
    clock: 0,
    lastTick: nowSec(),
    sessionPassive: 0,
    passiveMilestone: 0,
    easterEgg: false
  };

  (function initState() {
    for (var i = 0; i < B.base_upgrades.length; i++) {
      state.base[B.base_upgrades[i].id] = 0;
      state.ascensions[B.base_upgrades[i].id] = 0;
    }
    for (var j = 0; j < B.grade_items.length; j++) state.grade[B.grade_items[j].id] = 0;
    for (var k = 0; k < B.prestige_items.length; k++) state.prestige[B.prestige_items[k].id] = 0;
    for (var m = 0; m < B.display_settings.length; m++) {
      state.settings[B.display_settings[m].id] = B.display_settings[m].default;
    }
  })();

  function setting(name) { return state.settings[name] !== false; }

  // ---------------------------------------------------------------- helpers
  function passiveRate() {
    var total = 0;
    for (var i = 0; i < B.base_upgrades.length; i++) {
      var up = B.base_upgrades[i];
      var asc = ascensionRateMultiplier(state.ascensions[up.id] || 0);
      total += (state.base[up.id] || 0) * up.rate_per_level * asc;
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
  function prestigeShopUnlocked() { return state.prestigeCount >= 1; }

  function upgradeCostOf(id) {
    var mult = ascensionCostMultiplier(state.ascensions[id] || 0);
    return upgradeCost(baseUpgrade(id), state.base[id] || 0) * mult;
  }

  function upgradeFull(id) { return (state.base[id] || 0) >= maxLevelOf(baseUpgrade(id)); }

  function upgradeRate(id) {
    var up = baseUpgrade(id);
    return (state.base[id] || 0) * up.rate_per_level *
      ascensionRateMultiplier(state.ascensions[id] || 0);
  }

  function canAscend(id) {
    return state.prestigeCount >= ASC.unlock_after_prestige && upgradeFull(id);
  }

  function operationIds() {
    var ops = B.operations.filter(function (op) { return state.ops.indexOf(op.id) >= 0; })
      .map(function (op) { return op.id; });
    return ops.length ? ops : ["add"];
  }

  function manualDifficulty() {
    var level = Math.max(0, state.testLevel - 1);
    var value = 0.2 + 0.07 * level;
    if (prestigeShopUnlocked()) value += 0.05;
    return Math.min(1, value);
  }

  function nextProblem() {
    if (state.test && !state.test.finished) {
      state.current = state.test.problems[state.test.index];
    } else {
      state.current = randomProblem(operationIds(), manualDifficulty());
    }
    state.shownAt = state.clock;
    return state.current;
  }

  function credit(amount, passive) {
    if (amount <= 0) return 0;
    state.money += amount;
    state.runEarned += amount;
    if (!passive) state.stats.earned += amount;
    return amount;
  }

  // ------------------------------------------------------------- покупки
  function buyUpgrade(id) {
    if (upgradeFull(id)) return false;
    var cost = upgradeCostOf(id);
    if (state.money < cost) return false;
    state.money -= cost;
    state.base[id] += 1;
    var up = baseUpgrade(id);
    var asc = state.ascensions[id] || 0;
    ui.log(up.name + ": уровень " + state.base[id] +
      (asc ? " (вознесено ×" + Math.pow(2, asc) + ")" : ""), "buy");
    return true;
  }

  function ascend(id) {
    if (state.prestigeCount < ASC.unlock_after_prestige) return false;
    if (!upgradeFull(id)) return false;
    state.ascensions[id] = (state.ascensions[id] || 0) + 1;
    state.base[id] = 0;
    state.stats.ascensions += 1;
    ui.log(baseUpgrade(id).name + " вознесено " + state.ascensions[id] + " раз", "unlock");
    return true;
  }

  function buyAllUpgrades() {
    var bought = 0, guard = 0;
    while (guard++ < 300) {
      var bestId = null, bestCost = Infinity;
      for (var i = 0; i < B.base_upgrades.length; i++) {
        var id = B.base_upgrades[i].id;
        if (upgradeFull(id)) continue;
        var c = upgradeCostOf(id);
        if (c < bestCost) { bestCost = c; bestId = id; }
      }
      if (!bestId || state.money < bestCost) break;
      state.money -= bestCost;
      state.base[bestId] += 1;
      bought++;
    }
    if (bought) ui.log("Куплено улучшений: " + bought, "buy");
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
      ui.log("Открыто действие «" + operation(item.operation).name + "»!", "unlock");
    } else {
      ui.log(item.name + ": уровень " + state.grade[id], "buy");
    }
    return true;
  }

  // ------------------------------------------------------------- престиж
  function prestigeUnlocked() {
    return state.maxDifficulty >= P.required_difficulty;
  }

  function prestigeBlockedReason() {
    if (prestigeUnlocked()) return "";
    return "Нужен пример сложности " + Math.round(P.required_difficulty * 100) +
      "%. Лучший решён: " + Math.round(state.maxDifficulty * 100) + "%";
  }

  function pendingPrestigePoints() { return prestigePoints(state.runEarned); }

  function doPrestige() {
    if (!prestigeUnlocked()) return false;
    if (state.prestigeCount === 0 && pendingPrestigePoints() <= 0) return false;

    var gained = pendingPrestigePoints();
    var keep = state.money * keepMoneyShare();

    state.prestigePoints += gained;
    state.stats.prestige_points_total += gained;
    state.prestigeCount += 1;

    B.base_upgrades.forEach(function (up) { state.base[up.id] = 0; });
    B.grade_items.forEach(function (item) {
      if (item.effect !== "unlock") state.grade[item.id] = 0;   // операции остаются
    });

    state.money = keep;
    state.runEarned = 0;
    state.combo = 0;
    state.test = null;
    state.current = null;

    if (state.prestigeCount === 1 && P.unlock_mixed_on_first &&
        state.ops.indexOf("mix") < 0) {
      state.ops.push("mix");
      ui.log("Открыты смешанные примеры (несколько действий в одном)", "unlock");
    }
    ui.log("Престиж! +" + fmtMoney(gained) + " очков престижа (престиж #" +
            state.prestigeCount + ")", "pass");
    nextProblem();
    return true;
  }

  function prestigeFull(id) { return (state.prestige[id] || 0) >= prestigeItem(id).max_level; }

  function buyPrestige(id) {
    if (!prestigeShopUnlocked()) return false;
    var item = prestigeItem(id);
    if (prestigeFull(id)) return false;
    var cost = prestigeCost(item, state.prestige[id] || 0);
    if (state.prestigePoints < cost) return false;
    state.prestigePoints -= cost;
    state.prestige[id] = (state.prestige[id] || 0) + 1;
    if (item.easter_egg) {
      state.easterEgg = true;
      state.stats.femboy = true;
      ui.log("Femboy Futa house куплен", "unlock");
    } else {
      ui.log(item.name + ": уровень " + state.prestige[id], "buy");
    }
    return true;
  }

  // ------------------------------------------------------------- контрольные
  function testTypesAvailable() {
    return B.test_types.filter(function (tt) { return state.testsPassed >= tt.unlock_after; });
  }

  function canStartTest(typeId) {
    return !state.test && state.money >= testPrice(typeId) &&
      testTypesAvailable().some(function (tt) { return tt.id === typeId; });
  }

  function startTest(typeId) {
    typeId = typeId || "test";
    if (state.test) return false;
    if (!testTypesAvailable().some(function (tt) { return tt.id === typeId; })) return false;
    var cost = testPrice(typeId);
    if (state.money < cost) return false;
    state.money -= cost;

    var level = state.testLevel;
    var count = testProblemCount(level, typeId);
    var diff = testDifficulty(level, typeId);
    var built = testProblemsFor(typeId, operationIds(), diff, count);

    state.test = {
      level: level, type: typeId, problems: built.problems, ops: built.ops,
      index: 0, limit: testTimeLimit(level, typeId), startedAt: state.clock,
      elapsed: 0, finished: false, passed: false, difficulty: diff
    };
    nextProblem();
    ui.log(testType(typeId).name + ": " + count + " примеров на " +
           fmtTime(state.test.limit), "test");
    return true;
  }

  function passTest() {
    var tt = testType(state.test.type);
    var bonus = testReward(state.test.level, state.test.type);
    credit(bonus, false);
    state.testsPassed += 1;
    state.stats.tests_passed += 1;
    var level = state.test.level;
    var spare = state.test.limit - state.test.elapsed;
    var first = state.stats.tests_passed === 1;
    state.test.finished = true;
    state.test.passed = true;
    state.test = null;
    state.testLevel = level + 1;
    if (state.testKindIsPlain === undefined) state.testKindIsPlain = true;
    ui.log(tt.name + " сдана! +" + fmtMoney(bonus) +
      (first && tt.id === "test" ? " Открыт магазин контрольных улучшений!" : ""),
      tt.id === "test" ? (first ? "unlock" : "pass") : "pass");
    return { passed: true, level: level, name: tt.name, kind: tt.id, bonus: bonus,
             spare: spare, shopUnlocked: first && tt.id === "test" };
  }

  function failTest(reason) {
    var kind = state.test ? state.test.type : "test";
    var refund = testPrice(kind) * T.fail_refund;
    var level = state.test ? state.test.level : state.testLevel;
    var name = testType(kind).name;
    credit(refund, false);
    if (state.test) { state.test.finished = true; state.test.passed = false; }
    state.test = null;
    state.combo = 0;
    ui.log((reason === "time" ? "Время вышло! " : "Ошибка в проверке. ") +
           name + " провалена, билет возвращён", "fail");
    return { passed: false, level: level, name: name, refund: refund, reason: reason };
  }

  function abortTest() {
    if (state.test && !state.test.finished) return failTest("abort");
    return null;
  }

  // ------------------------------------------------------------- ответы
  function submit(text) {
    var raw = (text || "").trim().replace(",", ".");
    if (!state.current) nextProblem();
    var value = Number(raw);
    if (raw === "" || isNaN(value)) {
      state.stats.wrong += 1;
      state.combo = 0;
      return { ok: false, reason: raw === "" ? "empty" : "parse" };
    }
    var expected = state.current.answer;
    var elapsed = state.clock - state.shownAt;
    if (value !== expected) {
      state.stats.wrong += 1;
      state.combo = 0;
      var res = { ok: false, reason: "wrong", expected: expected };
      if (state.test) res.test = failTest("wrong");
      return res;
    }

    state.stats.solved += 1;
    state.combo += 1;
    state.stats.best_streak = Math.max(state.stats.best_streak, state.combo);
    state.lastCorrectAt = state.clock;
    state.maxDifficulty = Math.max(state.maxDifficulty, state.current.difficulty);
    var amount = reward(state.current.op, state.current.difficulty, elapsed, state.combo - 1);
    credit(amount, false);

    var out = { ok: true, amount: amount, elapsed: elapsed, combo: state.combo,
                speed: speedFactor(elapsed) };
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

  function speedWindow() {
    var mult = speedMult();
    return [R.fast_window * mult, R.slow_window * mult];
  }

  /** Как только пассивный доход стал заметным — показываем всплывашку. */
  var PASSIVE_MILESTONES = [0.01, 0.1, 1, 10, 100, 1000];
  function checkPassiveMilestone() {
    var passed = 0;
    for (var i = 0; i < PASSIVE_MILESTONES.length; i++) {
      if (state.sessionPassive >= PASSIVE_MILESTONES[i]) passed++;
    }
    if (passed > state.passiveMilestone) {
      state.passiveMilestone = passed;
      ui.floater("пассив: +" + fmtMoney(PASSIVE_MILESTONES[passed - 1]), "var(--accent)");
    }
  }

  // ------------------------------------------------------------------- тик
  var saveTimer = 0;
  var repaintTimer = 0;

  function tick() {
    var t = nowSec();
    var dt = Math.min(0.5, Math.max(0, t - state.lastTick));
    state.lastTick = t;
    state.clock += dt;
    state.playTime += dt;

    // пассивный доход идёт и во время игры
    var rate = passiveRate();
    if (rate > 0) {
      var gain = rate * dt * passiveReward(topOperation());
      state.money += gain;
      state.runEarned += gain;
      state.stats.idle_examples += rate * dt;
      state.sessionPassive += gain;
      state.stats.passive_earned += gain;
      checkPassiveMilestone();
    }
    if (state.combo && state.clock - state.lastCorrectAt > R.combo_decay) state.combo = 0;
    if (state.test && !state.test.finished) {
      state.test.elapsed = state.clock - state.test.startedAt;
      if (state.test.elapsed >= state.test.limit) {
        var failed = failTest("time");
        ui.showModal(failed);
        ui.renderAll();
      }
    }

    saveTimer += dt;
    if (saveTimer >= B.game.autosave_seconds) { saveTimer = 0; save(); }

    // верхняя панель обновляется сама, без кликов игрока
    repaintTimer += dt;
    if (repaintTimer >= 0.25) { repaintTimer = 0; ui.renderLive(); }
  }

  // ----------------------------------------------------------- сохранение
  function toDict() {
    return {
      version: 2,
      money: state.money,
      run_earned: state.runEarned,
      base_levels: state.base,
      ascensions: state.ascensions,
      grade_levels: state.grade,
      prestige_levels: state.prestige,
      prestige_points: state.prestigePoints,
      prestige_count: state.prestigeCount,
      unlocked_ops: state.ops,
      test_level: state.testLevel,
      tests_passed: state.testsPassed,
      max_difficulty_solved: state.maxDifficulty,
      settings: state.settings,
      server_url: state.serverUrl,
      stats: state.stats,
      play_time: state.playTime,
      account_username: account.username,
      account_token: account.token,
      saved_at: Date.now()
    };
  }

  function applyDict(data) {
    if (!data) return;
    state.money = Number(data.money) || 0;
    state.runEarned = Number(data.run_earned) || 0;
    B.base_upgrades.forEach(function (up) {
      state.base[up.id] = Number((data.base_levels || {})[up.id]) || 0;
      state.ascensions[up.id] = Number((data.ascensions || {})[up.id]) || 0;
    });
    B.grade_items.forEach(function (it) {
      state.grade[it.id] = Number((data.grade_levels || {})[it.id]) || 0;
    });
    B.prestige_items.forEach(function (it) {
      state.prestige[it.id] = Number((data.prestige_levels || {})[it.id]) || 0;
    });
    state.prestigePoints = Number(data.prestige_points) || 0;
    state.prestigeCount = Number(data.prestige_count) || 0;
    state.maxDifficulty = Number(data.max_difficulty_solved) || 0;

    var valid = {};
    B.operations.forEach(function (op) { valid[op.id] = true; });
    state.ops = (data.unlocked_ops && data.unlocked_ops.length ? data.unlocked_ops : ["add"])
      .filter(function (o) { return valid[o]; });
    if (state.ops.indexOf("add") < 0) state.ops.push("add");

    state.testLevel = Math.max(1, Number(data.test_level) || 1);
    state.testsPassed = Number(data.tests_passed) || 0;
    Object.keys(state.stats).forEach(function (key) {
      if (data.stats && data.stats[key] !== undefined) state.stats[key] = data.stats[key];
    });
    Object.keys(state.settings).forEach(function (key) {
      if (data.settings && data.settings[key] !== undefined) state.settings[key] = data.settings[key];
    });
    state.serverUrl = String(data.server_url || "");
    state.playTime = Number(data.play_time) || 0;
    if (data.account_token) {
      account.username = data.account_username;
      account.token = data.account_token;
    }
    state.easterEgg = !!state.stats.femboy;
  }

  function save() {
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(toDict())); } catch (e) { /* приватный режим */ }
  }

  function loadLocal() {
    try {
      var raw = localStorage.getItem(SETTINGS_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  var offlineEarned = 0, offlineAway = 0;

  function applyOffline(savedAt) {
    offlineAway = Math.max(0, nowSec() - (Number(savedAt) / 1000 || nowSec()));
    if (!B.offline.enabled || offlineAway < 60) return;
    var capped = Math.min(offlineAway, B.offline.cap_hours * 3600);
    var rate = passiveRate();
    if (rate > 0) {
      offlineEarned = rate * capped * passiveReward(topOperation()) * B.offline.efficiency;
      credit(offlineEarned, true);
    }
  }

  // --------------------------------------------------------------------- UI
  var ui = (function () {
    var el = {};
    var input = "";
    var tab = "upgrades";        // открытое меню
    var view = "play";           // что показано на телефоне: игра или меню
    var events = [];
    var floaters = [];
    var eggDismissed = false;
    var loginName = "", loginPass = "", accountError = "";

    var KIND_COLORS = {
      buy: "var(--accent)", unlock: "var(--gold)", pass: "var(--green)",
      fail: "var(--red)", test: "var(--blue)", info: "var(--muted)"
    };

    var TABS = [
      { id: "play", label: "Игра" },
      { id: "upgrades", label: "Улучшения" },
      { id: "test", label: "Проверки" },
      { id: "prestige", label: "Престиж" },
      { id: "shop", label: "Магазин" },
      { id: "settings", label: "Настройки" }
    ];

    function byId(id) { return document.getElementById(id); }

    function cache() {
      ["money", "passive", "passiveHint", "mult", "combo", "playTitle", "playHint",
        "timerWrap", "timerBar", "timerText", "testProgress", "problem", "speedGauge",
        "speedTrack", "speedFast", "speedMarker", "speedText", "diffWrap", "diffBar",
        "diffText", "answer", "answerText", "floaters", "log", "panel", "modal",
        "modalTitle", "modalBody", "modalClose", "egg", "eggVeil", "tabs"
      ].forEach(function (id) { el[id] = byId(id); });
      el.tabs = document.querySelectorAll(".tabs button");
    }

    function flash(kind) {
      document.body.classList.remove("flash-ok", "flash-bad");
      void document.body.offsetWidth;
      document.body.classList.add(kind === "ok" ? "flash-ok" : "flash-bad");
    }

    function log(text, kind, ttl) {
      events.push({ text: text, kind: kind, born: state.clock, ttl: ttl || 4.5 });
      if (events.length > 4) events.shift();
      renderLog();
    }

    function renderLog() {
      if (!setting("event_log")) { el.log.innerHTML = ""; events = []; return; }
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

    // ------------------------------------------------------------- верх
    function renderTop() {
      var rate = passiveRate();
      el.money.textContent = fmtMoney(state.money);
      el.passive.textContent = "+" + fmtMoney(rate * passiveReward(topOperation())) + "/с";
      var hint = fmtRate(rate) + " примера/с";
      if (setting("passive_counter")) {
        hint = state.sessionPassive > 0
          ? "за сессию +" + fmtMoney(state.sessionPassive) + " · " + hint
          : hint;
      }
      el.passiveHint.textContent = hint;
      el.mult.textContent = "×" + moneyMult().toFixed(1);
      el.combo.textContent = state.combo > 1 ? "серия " + state.combo : "";
    }

    // ------------------------------------------------------------- пример
    function renderPlay() {
      var testing = !!state.test;
      var tt = testing ? testType(state.test.type) : null;
      el.playTitle.textContent = testing
        ? tt.name + " №" + state.test.level + " · пример " + (state.test.index + 1) +
          " из " + state.test.problems.length
        : "Реши пример";
      el.playTitle.style.color = testing ? "var(--blue)" : "var(--muted)";

      if (testing) {
        var left = Math.max(0, state.test.limit - state.test.elapsed);
        var k = left / Math.max(1e-6, state.test.limit);
        el.timerWrap.classList.remove("hidden");
        el.timerBar.style.width = (k * 100).toFixed(1) + "%";
        el.timerBar.style.background = k < 0.25 ? "var(--red)"
          : (k < 0.5 ? "var(--gold)" : "var(--green)");
        el.timerText.textContent = "осталось " + fmtTime(left);
        el.testProgress.textContent = state.test.index + "/" + state.test.problems.length;
      } else {
        el.timerWrap.classList.add("hidden");
      }

      el.playHint.textContent = wantsHint() ? "шпаргалка" : "";
      el.playHint.classList.toggle("hidden", !wantsHint());

      if (state.current) {
        el.problem.textContent = state.current.text + " =";
        renderSpeedGauge();
        renderDifficulty();
      }

      el.answerText.textContent = input ? input : "…";
      el.answerText.style.color = input ? "var(--text)" : "var(--muted)";
      el.answer.classList.toggle("active", !!input);
    }

    /** Окно скорости: зелёная зона быстрого ответа и бегущий маркер. */
    function renderSpeedGauge() {
      if (!setting("speed_gauge")) { el.speedGauge.classList.add("hidden"); return; }
      el.speedGauge.classList.remove("hidden");
      var win = speedWindow();
      var elapsed = Math.max(0, state.clock - state.shownAt);
      var span = Math.max(win[1] * 1.25, 1);
      el.speedFast.style.width = (clamp(win[0] / span, 0, 1) * 100).toFixed(1) + "%";
      el.speedMarker.style.left = (clamp(elapsed / span, 0, 1) * 100).toFixed(1) + "%";
      el.speedText.textContent = "скорость ×" + speedFactor(elapsed).toFixed(2) +
        " · " + elapsed.toFixed(1) + "с";
    }

    function renderDifficulty() {
      if (!setting("difficulty_bar")) { el.diffWrap.classList.add("hidden"); return; }
      el.diffWrap.classList.remove("hidden");
      var d = state.current.difficulty;
      el.diffBar.style.width = (d * 100).toFixed(0) + "%";
      el.diffBar.style.background = d < 0.35 ? "var(--green)"
        : (d < 0.6 ? "var(--gold)" : "var(--red)");
      el.diffText.textContent = "сложность " + Math.round(d * 100) + "%";
    }

    // ------------------------------------------------------------- вкладки
    function tabLocked(id) {
      if (id === "play") return false;
      if (id === "shop" && !shopUnlocked()) return true;
      if (id === "prestige" && state.prestigeCount === 0 && !prestigeUnlocked()) return true;
      return false;
    }

    /** На широком экране игра и меню видны одновременно,
     *  на телефоне — по одному. */
    function isDesktop() {
      return window.matchMedia && window.matchMedia("(min-width: 760px)").matches;
    }

    function applyView() {
      document.body.classList.toggle("view-play", view === "play");
      document.body.classList.toggle("view-menu", view === "menu");
    }

    /** На телефоне активна вкладка «Игра», на десктопе — вкладка меню. */
    function activeTab() {
      return (view === "play" && !isDesktop()) ? "play" : tab;
    }

    /** Подсвечивает активную вкладку и обновляет блокировки. */
    function syncTabs() {
      var current = activeTab();
      for (var i = 0; i < el.tabs.length; i++) {
        var id = el.tabs[i].getAttribute("data-tab");
        el.tabs[i].classList.toggle("active", id === current);
        el.tabs[i].disabled = tabLocked(id);
      }
    }

    function setTab(id) {
      if (id === "play") {
        view = "play";
        applyView();
        syncTabs();
        renderPlay();
        return;
      }
      tab = id;
      view = "menu";
      renderPanel();
    }

    function renderPanel() {
      applyView();
      var html = "";
      if (tab === "upgrades") html = panelUpgrades();
      else if (tab === "test") html = panelTests();
      else if (tab === "prestige") html = panelPrestige();
      else if (tab === "settings") html = panelSettings();
      else html = panelGrades();
      el.panel.innerHTML = html;
      bindPanel();
      el.panel.scrollTop = 0;
      syncTabs();
    }

    function panelUpgrades() {
      var rate = passiveRate();
      var maxRate = 0;
      B.base_upgrades.forEach(function (u) { maxRate += u.max_rate; });
      var out = '<div class="small" style="margin-bottom:4px">Сейчас: ' + fmtRate(rate) +
        " примера/с · " + fmtMoney(rate * passiveReward(topOperation())) + "/с · всего " +
        fmtRate(maxRate) + " максимум</div>";
      out += setting("passive_counter")
        ? '<div class="small accent" style="margin-bottom:8px">Заработано пассивно за сессию: +' +
          fmtMoney(state.sessionPassive) + "</div>"
        : '<div class="small" style="margin-bottom:8px">Купи узелки — и деньги пойдут сами</div>';

      B.base_upgrades.forEach(function (up) {
        var id = up.id;
        var level = state.base[id] || 0;
        var maxl = maxLevelOf(up);
        var full = level >= maxl;
        var cost = upgradeCostOf(id);
        var asc = state.ascensions[id] || 0;
        var perLevel = up.rate_per_level * Math.pow(2, asc);
        var afford = !full && state.money >= cost;
        var sub = full
          ? (asc ? "максимум, вознесений: " + asc : "максимум улучшения")
          : "+" + perLevel + " примера/с · ур. " + level + "/" + maxl +
            " · цена: " + fmtMoney(cost);
        var badge = full ? "" : fmtMoney(cost);
        if (asc) badge = (badge + " ×" + Math.pow(2, asc)).trim();
        var prog = Math.min(1, upgradeRate(id) / (up.max_rate * Math.pow(2, asc)));
        out += '<button class="item' + (afford ? " affordable" : "") + '" data-buy="' + id + '"' +
          (full ? " disabled" : "") + ">" +
          '<div class="name">' + up.name + "</div>" +
          '<div class="sub">' + sub + "</div>" +
          '<div class="price">' + badge + "</div>" +
          '<div class="prog"><i style="width:' + (prog * 100).toFixed(0) + '%"></i></div></button>';

        if (asc || state.prestigeCount >= ASC.unlock_after_prestige) {
          var can = canAscend(id);
          var label = full
            ? "Вознести: ур. → 0, скорость ×" + Math.pow(2, asc + 1) + ", цена ×" +
              Math.pow(4, asc + 1)
            : "Вознести (нужен максимум, осталось " + (maxl - level) + ")";
          out += '<button class="item violet' + (can ? " affordable" : "") + '" data-ascend="' +
            id + '"' + (can ? "" : " disabled") + '>' +
            '<div class="name" style="color:var(--violet)">Вознесение</div>' +
            '<div class="sub">' + label + "</div></button>";
        }
      });
      out += '<button class="item affordable" data-buyall="1" style="border-color:var(--blue)">' +
        '<div class="name" style="color:var(--blue)">Купить максимум</div>' +
        '<div class="sub">всё, что позволяет баланс</div></button>';
      return out;
    }

    function panelTests() {
      var out = "";
      if (state.test) {
        var tt = testType(state.test.type);
        var ops = state.test.ops.map(function (o) { return operation(o).name; }).join(", ");
        out += '<div class="info-card"><h3>' + tt.name + " №" + state.test.level + " идёт</h3>" +
          line("Пример", (state.test.index + 1) + " из " + state.test.problems.length) +
          line("Темы", ops) +
          line("Осталось", fmtTime(state.test.limit - state.test.elapsed)) +
          line("Награда", fmtMoney(testReward(state.test.level, state.test.type))) +
          '<button class="big-btn danger" data-abort="1">Прервать (вернуть билет)</button></div>';
      } else {
        testTypesAvailable().forEach(function (tt) {
          var level = state.testLevel;
          var price = testPrice(tt.id);
          var can = canStartTest(tt.id);
          var accent = tt.id === "exam" ? "var(--violet)" : (tt.id === "final" ? "var(--gold)" : "var(--blue)");
          out += '<div class="info-card" style="border-color:' + (can ? accent : "var(--line)") + '">' +
            "<h3>" + tt.name + "</h3>" +
            '<div class="small" style="margin:-4px 0 8px">' + tt.desc + "</div>" +
            line("Билет", fmtMoney(price)) +
            line("Примеров", testProblemCount(level, tt.id)) +
            line("Сложность", Math.round(testDifficulty(level, tt.id) * 100) + "%") +
            line("Время", fmtTime(testTimeLimit(level, tt.id))) +
            line("Награда", fmtMoney(testReward(level, tt.id))) +
            '<button class="big-btn" data-start="' + tt.id + '"' + (can ? "" : " disabled") +
            " style=\"background:" + accent + '">Начать · ' + fmtMoney(price) + "</button></div>";
        });
      }
      out += '<div class="rules"><b>Правила проверок:</b><br>' +
        "• ни одной ошибки, иначе провал (билет возвращается)<br>" +
        "• не уложишься во время — тоже провал<br>" +
        "• сдаёшь — награда и следующий уровень<br><br>" +
        "В обычной контрольной — две СЛУЧАЙНЫЕ открытые операции.<br>" +
        "Итоговая и экзамен — все операции разом.</div>";
      return out;
    }

    function line(label, value) {
      return '<div class="line"><span>' + label + "</span><span>" + value + "</span></div>";
    }

    function panelPrestige() {
      var unlocked = prestigeUnlocked();
      var accent = unlocked ? "var(--gold)" : "var(--muted)";
      var out = '<div class="info-card" style="border-color:' + (unlocked ? accent : "var(--line)") + '">' +
        "<h3>Престиж #" + (state.prestigeCount + 1) + "</h3>" +
        line("Очков престижа", fmtMoney(state.prestigePoints)) +
        line("Набежит за этот забег", "+" + fmtMoney(pendingPrestigePoints())) +
        line("Курс", "1 деньга = " + P.points_per_money + " очка") +
        '<div class="rules">' +
        (state.maxDifficulty >= P.required_difficulty
          ? "[x] Пример сложности 100% решён"
          : "[ ] Нужен пример сложности 100% (сейчас " + Math.round(state.maxDifficulty * 100) + "%)") +
        "<br>[x] Заработано в этом забеге: " + fmtMoney(state.runEarned) +
        "<br><br>Престиж обнуляет: деньги, обычные улучшения, контрольные улучшения и " +
        "вознесения. Открытые операции остаются.</div>" +
        '<button class="big-btn" data-prestige="1"' + (unlocked ? "" : " disabled") +
        " style=\"background:" + accent + '">' +
        (unlocked ? "СДЕЛАТЬ ПРЕСТИЖ" : prestigeBlockedReason()) + "</button></div>";

      if (!prestigeShopUnlocked()) {
        return out + '<div class="rules">Магазин престижных улучшений откроется после ' +
          "первого престижа.</div>";
      }
      out += "<h4>Престижные улучшения</h4>";
      B.prestige_items.forEach(function (item) {
        var level = state.prestige[item.id] || 0;
        var full = level >= item.max_level;
        var cost = prestigeCost(item, level);
        var afford = !full && state.prestigePoints >= cost;
        if (item.easter_egg) {
          out += '<button class="item gold' + (afford ? " affordable" : "") +
            '" data-prestige-buy="' + item.id + '"' + (full ? " disabled" : "") + ">" +
            '<div class="name">' + item.name + "</div>" +
            '<div class="sub">' + item.desc + "</div>" +
            '<div class="price">' + (full ? "ЕСТЬ" : fmtMoney(cost)) + "</div>" +
            '<div class="sub" style="color:' + (full ? "var(--green)" : "var(--red)") +
            ';margin-top:6px">сейчас действует скидка 15% · полная цена ' +
            fmtMoney(item.price) + "</div></button>";
        } else {
          var sub = full ? "максимум (ур. " + item.max_level + ") · " + item.desc
            : "ур. " + level + "/" + item.max_level + " · " + item.desc;
          out += '<button class="item violet' + (afford ? " affordable" : "") +
            '" data-prestige-buy="' + item.id + '"' + (full ? " disabled" : "") + ">" +
            '<div class="name">' + item.name + "</div>" +
            '<div class="sub">' + sub + "</div>" +
            '<div class="price">' + (full ? "МАКС" : fmtMoney(cost)) + "</div></button>";
        }
      });
      out += '<div class="rules">«Femboy Futa house» — самая дорогая прокачка, без эффектов.</div>';
      return out;
    }

    function panelGrades() {
      if (!shopUnlocked()) {
        return '<div class="info-card"><h3>Магазин закрыт</h3><div class="rules">' +
          "Сдай первую контрольную — и здесь появятся контрольные улучшения.</div></div>";
      }
      var out = '<div class="small" style="margin-bottom:8px">Улучшения за деньги, ' +
        "полученные на контрольных.</div>";
      B.grade_items.forEach(function (item) {
        var level = state.grade[item.id] || 0;
        var full = level >= item.max_level;
        var cost = gradeCost(item, level);
        var isUnlock = item.effect === "unlock";
        var already = isUnlock && state.ops.indexOf(item.operation) >= 0;
        var afford = !full && !already && state.money >= cost;
        var cls = isUnlock ? "gold" : "violet";
        var sub = isUnlock ? (already ? "уже открыто" : item.desc)
          : (full ? "максимум" : "ур. " + level + "/" + item.max_level) + " · " + item.desc;
        var badge = isUnlock ? (already ? "ЕСТЬ" : fmtMoney(cost))
          : (full ? "МАКС" : fmtMoney(cost));
        out += '<button class="item ' + cls + (afford ? " affordable" : "") +
          '" data-grade="' + item.id + '"' + (full || already ? " disabled" : "") + ">" +
          '<div class="name">' + item.name + "</div>" +
          '<div class="sub">' + sub + "</div>" +
          '<div class="price">' + badge + "</div></button>";
      });
      return out;
    }

    function panelSettings() {
      var out = "<h4>Отображение</h4>";
      B.display_settings.forEach(function (item) {
        var on = setting(item.id);
        out += '<button class="item' + (on ? " affordable" : "") + '" data-setting="' + item.id + '">' +
          '<div class="name">' + item.name + '<span class="toggle">' + (on ? "ВКЛ" : "ВЫКЛ") + "</span></div>" +
          '<div class="sub">' + item.desc + "</div></button>";
      });

      out += "<h4>Аккаунт</h4>";
      if (account.signedIn()) {
        out += '<div class="small accent">Вы вошли как ' + account.username +
          " · прогресс синхронизируется</div>" +
          '<div class="small" style="margin:4px 0 8px">Сервер: ' + account.status() + "</div>" +
          serverUrlField() +
          '<button class="big-btn danger" data-signout="1">Выйти</button>';
      } else {
        out += '<div class="small">Войди, чтобы прогресс хранился на сервере, ' +
          "а не на устройстве</div>" +
          serverUrlField();
        if (account.lastError) {
          out += '<div class="warn" >' + escapeHtml(account.lastError) + "</div>";
        }
        if (accountError) {
          out += '<div class="warn">' + escapeHtml(accountError) + "</div>";
        }
        out += '<div class="row-fields">' +
          '<input id="loginName" type="text" placeholder="имя игрока" value="' +
          escapeHtml(loginName) + '" maxlength="24" autocomplete="username">' +
          '<input id="loginPass" type="password" placeholder="пароль (мин. 6)" ' +
          'maxlength="64" autocomplete="current-password"></div>' +
          '<button class="big-btn" data-login="1">Войти</button>' +
          '<button class="big-btn" data-register="1" style="background:var(--blue)">Регистрация</button>';
      }
      return out;
    }

    /** Адрес сервера аккаунтов — его надо задать, если игра открыта не с компьютера. */
    function serverUrlField() {
      var secure = /^https:/i.test(window.location.protocol);
      var found = account.discovered.length
        ? '<div class="small accent" style="margin-top:6px">Найдено в сети: ' +
          escapeHtml(account.discovered.join(", ")) + "</div>"
        : "";
      var hint = account.discovered.length
        ? "Найден сам, можно просто нажать «Регистрация»"
        : (window.MathIdleNative
            ? "Ищу сервер в сети… запусти его на компьютере: bash tools/serve_accounts.sh"
            : "Укажи адрес компьютера, где запущен сервер");
      return '<label class="small field-label">Адрес сервера аккаунтов' +
        (secure ? " (нужен https://)" : "") + "</label>" +
        '<input id="serverUrl" class="full-input" type="text" ' +
        'placeholder="http://192.168.1.10:8766" value="' +
        escapeHtml(state.serverUrl) + '" spellcheck="false">' +
        '<div class="small" style="margin-top:4px">' + hint + "</div>" +
        found +
        '<button class="small-btn" data-save-url="1">Сохранить адрес</button>';
    }

    function escapeHtml(text) {
      return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function bindPanel() {
      bind("[data-buy]", function (node) {
        return function () { flash(buyUpgrade(node.getAttribute("data-buy")) ? "ok" : "bad"); renderAll(); };
      });
      bind("[data-ascend]", function (node) {
        return function () { flash(ascend(node.getAttribute("data-ascend")) ? "ok" : "bad"); renderAll(); };
      });
      bind("[data-buyall]", function () {
        return function () { flash(buyAllUpgrades() ? "ok" : "bad"); renderAll(); };
      });
      bind("[data-grade]", function (node) {
        return function () { flash(buyGrade(node.getAttribute("data-grade")) ? "ok" : "bad"); renderAll(); };
      });
      bind("[data-prestige-buy]", function (node) {
        return function () {
          var bought = buyPrestige(node.getAttribute("data-prestige-buy"));
          flash(bought ? "ok" : "bad");
          renderAll();
        };
      });
      bind("[data-setting]", function (node) {
        return function () {
          var id = node.getAttribute("data-setting");
          state.settings[id] = !setting(id);
          renderAll();
        };
      });

      var prestigeBtn = el.panel.querySelector("[data-prestige]");
      if (prestigeBtn) prestigeBtn.onclick = function () {
        flash(doPrestige() ? "ok" : "bad");
        renderAll();
      };
      var startBtn = el.panel.querySelector("[data-start]");
      if (startBtn) startBtn.onclick = function () {
        if (startTest(startBtn.getAttribute("data-start"))) {
          input = ""; view = "play"; renderAll();   // сразу к примеру
        }
      };
      var abortBtn = el.panel.querySelector("[data-abort]");
      if (abortBtn) abortBtn.onclick = function () {
        var res = abortTest();
        if (res) { showModal(res); renderAll(); }
      };
      var loginBtn = el.panel.querySelector("[data-login]");
      if (loginBtn) loginBtn.onclick = function () { doAuth("login"); };
      var regBtn = el.panel.querySelector("[data-register]");
      if (regBtn) regBtn.onclick = function () { doAuth("register"); };
      var outBtn = el.panel.querySelector("[data-signout]");
      if (outBtn) outBtn.onclick = function () {
        save();
        account.logout();
        state.accountSaved = false;
        renderAll();
      };
      var urlBtn = el.panel.querySelector("[data-save-url]");
      if (urlBtn) urlBtn.onclick = function () {
        var input = document.getElementById("serverUrl");
        state.serverUrl = input ? input.value.trim().replace(/\/+$/, "") : "";
        account.url = null;
        account.lastError = null;
        accountError = "";
        save();
        renderAll();
      };
    }

    function bind(selector, factory) {
      var nodes = el.panel.querySelectorAll(selector);
      for (var i = 0; i < nodes.length; i++) {
        var handler = factory(nodes[i]);
        nodes[i].onclick = handler;
      }
    }

    function doAuth(kind) {
      var nameInput = document.getElementById("loginName");
      var passInput = document.getElementById("loginPass");
      var urlInput = document.getElementById("serverUrl");
      if (urlInput) {
        state.serverUrl = urlInput.value.trim().replace(/\/+$/, "");
        account.url = null;
        save();
      }
      var name = nameInput ? nameInput.value.trim() : loginName;
      var pass = passInput ? passInput.value : loginPass;
      loginName = name; loginPass = pass;
      accountError = "";

      var targets = account.candidateUrls();
      var action = kind === "login"
        ? account.login(name, pass)
        : account.register(name, pass);
      action.then(function () {
        save();
        return account.downloadSave();
      }).then(function (data) {
        if (data && data.save) applyDict(data.save);
        ui.log(kind === "login" ? "Вход выполнен, прогресс загружен" : "Аккаунт создан", "unlock");
        nextProblem();
        accountError = "";
        renderAll();
      }).catch(function (err) {
        accountError = explainAuthError(err, targets, kind);
        renderAll();
      });
    }

    /** Человеческое объяснение вместо технического «Failed to fetch». */
    function explainAuthError(err, targets, kind) {
      var secure = /^https:/i.test(window.location.protocol);
      var allHttp = targets.length > 0 && targets.every(function (u) { return /^http:/i.test(u); });
      if (secure && allHttp) {
        return "Игра открыта по HTTPS, а сервер аккаунтов — по HTTP. Браузер блокирует " +
          "такой запрос («Failed to fetch»). " + B.account.https_required_hint +
          " Или укажите https-адрес сервера в поле выше.";
      }
      if (err && /имя|пароль|занят|минимум/i.test(err.message)) {
        return err.message;
      }
      return (err && err.message ? err.message : "Не удалось связаться с сервером") +
        ". Проверьте, что сервер запущен (bash tools/serve_accounts.sh), адрес верен " +
        "и доступен с этого устройства" +
        (secure ? ". Для телефона нужен IP компьютера в локальной сети, а не 127.0.0.1" : "") +
        ".";
    }

    function syncToServer(silent) {
      if (!account.signedIn()) return Promise.resolve(false);
      return account.uploadSave(toDict()).then(function () {
        return true;
      }).catch(function (err) {
        if (!silent) log("Синхронизация не удалась: " + err.message, "fail");
        return false;
      });
    }

    // ------------------------------------------------------------- модалка
    function showModal(res) {
      var title, lines, fail;
      if (res.passed) {
        title = "Сдано!";
        lines = [res.name + " №" + res.level + " сдана",
                 "Награда: +" + fmtMoney(res.bonus),
                 "Осталось времени: " + fmtTime(res.spare)];
        if (res.shopUnlocked) lines.push("Открыт магазин контрольных улучшений!");
        fail = false;
      } else {
        var reasons = { time: "Время вышло", abort: "Проверка прервана", wrong: "Ошибка в примере" };
        title = reasons[res.reason] || "Провал";
        lines = [(res.name || "Проверка") + " №" + res.level + " не засчитана", "Билет возвращён"];
        fail = true;
      }
      el.modalTitle.textContent = title;
      el.modalBody.innerHTML = lines.map(function (l) {
        return '<div class="mline">' + l + "</div>";
      }).join("");
      el.modal.querySelector(".modal-card").classList.toggle("fail", fail);
      el.modal.classList.remove("hidden");
    }

    // ------------------------------------------------------------- ввод
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
        if (res.expected !== undefined) floater("ответ: " + res.expected, "var(--red)");
        flash("bad");
      }
      if (res.test) showModal(res.test);
      renderAll();
    }

    function onKey(e) {
      var k = e.key;
      if (state.easterEgg && !eggDismissed) {
        if (k === "Enter" || k === "Escape" || k === " ") { eggDismissed = true; renderEgg(); }
        e.preventDefault();
        return;
      }
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
        var order = ["play", "upgrades", "test", "prestige", "shop", "settings"];
        var start = view === "play" ? 0 : order.indexOf(tab);
        var next = order[(start + 1) % order.length];
        if (!tabLocked(next)) setTab(next);
        e.preventDefault();
      }
    }

    /** Затемнение после «Femboy Futa house». */
    function renderEgg() {
      var visible = state.easterEgg && !eggDismissed;
      el.egg.classList.toggle("hidden", !visible);
      if (visible) el.eggVeil.classList.remove("hidden");
      else el.eggVeil.classList.add("hidden");
    }

    /** Подгоняем высоту оболочки под реальное окно.
     *  В старых Android WebView нет dvh/svh, поэтому меряем сами. */
    function syncViewport() {
      var h = window.innerHeight;
      if (h > 0) document.documentElement.style.setProperty("--app-h", h + "px");
    }

    // ------------------------------------------------------------- init
    function init() {
      cache();
      tab = "upgrades";                   // открытое меню по умолчанию
      view = "play";                     // на телефоне открываемся на игре
      syncViewport();

      var keys = document.querySelectorAll(".keypad button");
      for (var i = 0; i < keys.length; i++) {
        (function (btn) {
          btn.addEventListener("click", function () { pressKey(btn.getAttribute("data-key")); });
        })(keys[i]);
      }

      for (var j = 0; j < el.tabs.length; j++) {
        (function (btn) {
          btn.addEventListener("click", function () {
            var id = btn.getAttribute("data-tab");
            if (tabLocked(id)) return;
            setTab(id);
          });
        })(el.tabs[j]);
      }

      el.modalClose.addEventListener("click", function () {
        el.modal.classList.add("hidden");
      });
      el.modal.addEventListener("click", function (e) {
        if (e.target === el.modal) el.modal.classList.add("hidden");
      });
      el.egg.addEventListener("click", function () { eggDismissed = true; renderEgg(); });

      document.addEventListener("keydown", onKey);
      window.addEventListener("beforeunload", function () {
        save();
        if (account.signedIn()) syncToServer(true);
      });
      document.addEventListener("visibilitychange", function () {
        if (document.hidden) { save(); syncToServer(true); }
        else { syncViewport(); renderPlay(); }
      });
      window.addEventListener("resize", function () {
        syncViewport();
        renderPlay();
      });
      window.addEventListener("orientationchange", function () {
        setTimeout(function () { syncViewport(); renderPlay(); }, 220);
      });
      renderEgg();
      account.discover();          // в приложении сервер ищется сам
    }

    function renderAll() {
      renderTop();
      renderPlay();
      renderPanel();
      renderLog();
      renderEgg();
    }

    /** Быстрое обновление без перерисовки панелей — для пассивного дохода. */
    function renderLive() {
      renderTop();
      renderPlay();
      renderLog();
    }

    return {
      init: init, log: log, floater: floater, renderAll: renderAll, renderLive: renderLive,
      showModal: showModal, flash: flash, syncToServer: syncToServer
    };
  })();

  // ------------------------------------------------------------------ старт
  function boot() {
    ui.init();
    var saved = loadLocal();
    if (saved) {
      applyDict(saved);
      applyOffline(saved.saved_at);
    }
    nextProblem();
    if (offlineEarned > 0) {
      ui.log("Пока тебя не было " + fmtTime(offlineAway) + ", пассивные примеры заработали " +
             fmtMoney(offlineEarned), "info", 8);
    }
    if (account.signedIn()) ui.syncToServer(true);
    ui.renderAll();
    document.body.classList.toggle("big-text", setting("big_text"));
    setInterval(tick, 1000 / 30);
    setInterval(function () { save(); ui.syncToServer(true); }, 15000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
