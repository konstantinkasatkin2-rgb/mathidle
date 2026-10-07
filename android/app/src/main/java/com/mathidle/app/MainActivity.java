package com.mathidle.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Context;
import android.net.Uri;
import android.net.wifi.WifiManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.IOException;
import java.io.InputStream;
import java.net.DatagramPacket;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.net.UnknownHostException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;

/**
 * Тонкая нативная обёртка над HTML5-игрой (assets/www).
 *
 * Игра отдаётся не через file://, а через свой домен appassets.mathidle.local,
 * который отдаёт WebViewClient. Так у страницы нормальный origin — иначе в
 * Chromium WebView localStorage (сохранения игры) может не работать.
 *
 * Домен именно http://, а не https://. Страница на https не может обратиться
 * к серверу аккаунтов на http: браузер блокирует такой запрос, и игра
 * показывает «Failed to fetch». А сервер аккаунтов запускается дома, по
 * обычному http, — поэтому и страница должна быть без https. Раньше здесь
 * стоял https, и регистрация в приложении не работала вообще.
 *
 * Зависимостей нет вообще (без AndroidX), поэтому APK весит меньше 100 КБ.
 */
public class MainActivity extends Activity {

    private static final String HOST = "appassets.mathidle.local";
    private static final String START_URL = "http://" + HOST + "/index.html";

    /**
     * Сохранения живут в localStorage, а он привязан к origin вместе со
     * схемой. В версиях 1.2.0–1.2.3 игра открывалась по https, а начиная
     * с 1.2.4 — по http (иначе браузер блокирует запрос к серверу
     * аккаунтов на http). Для игрока это выглядело как «прогресс сбросился»:
     * телефон просто смотрел в другое хранилище, а старые данные лежали
     * нетронутыми. Поэтому один раз переносим сохранение со старого адреса
     * на новый.
     */
    private static final String LEGACY_START_URL = "https://" + HOST + "/index.html";
    private static final String SAVE_KEY = "mathidle.save";
    private static final String PREF_MIGRATED = "migrated_https_save";

    private static final String ASSET_ROOT = "www";
    private static final int DISCOVERY_PORT = 8766;
    private static final String DISCOVERY_TOKEN = "mathidle";

    private static final Map<String, String> MIME = new HashMap<>();

    static {
        MIME.put("html", "text/html");
        MIME.put("js", "text/javascript");
        MIME.put("css", "text/css");
        MIME.put("json", "application/json");
        MIME.put("png", "image/png");
        MIME.put("jpg", "image/jpeg");
        MIME.put("svg", "image/svg+xml");
        MIME.put("ico", "image/x-icon");
    }

    private WebView web;
    private String legacySave;                 // сохранение со старого origin
    private boolean mergePending;            // ждём загрузки игры для переноса
    private final Handler ui = new Handler(Looper.getMainLooper());

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        web = new WebView(this);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);      // сохранения игры живут в localStorage
        settings.setAllowFileAccess(false);       // Assets отдаёт наш клиент
        settings.setAllowContentAccess(false);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setTextZoom(100);                // системный размер шрифта не ломает вёрстку
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        // на случай, если где-то внутри останется https-ссылка
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return serveAsset(request.getUrl());
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                // Страница загрузилась — можно переносить сохранение.
                if (mergePending) {
                    mergePending = false;
                    mergeLegacySave();
                }
            }
        });
        web.addJavascriptInterface(new NativeBridge(), "MathIdleNative");

        web.setBackgroundColor(0xFF101420);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.setFocusable(true);
        web.setFocusableInTouchMode(true);

        setContentView(web);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        loadGame();
    }

    private void loadGame() {
        if (alreadyMigrated()) {
            web.loadUrl(START_URL);
            return;
        }
        // Сначала читаем сохранение со старого адреса, потом открываем игру:
        // перенос должен случиться до того, как игра успеет загрузить данные.
        readLegacySave(new Runnable() {
            @Override
            public void run() {
                web.loadUrl(START_URL);
            }
        });
    }

    private boolean alreadyMigrated() {
        return getSharedPreferences("mathidle", MODE_PRIVATE).getBoolean(PREF_MIGRATED, false);
    }

    private void rememberMigrated() {
        getSharedPreferences("mathidle", MODE_PRIVATE)
                .edit().putBoolean(PREF_MIGRATED, true).apply();
    }

    /**
     * Читает сохранение из старого origin (https) во временном WebView.
     * Сам WebView в окно не добавляется и сразу уничтожается.
     */
    private void readLegacySave(final Runnable then) {
        final WebView tmp = new WebView(this);
        tmp.getSettings().setJavaScriptEnabled(true);
        tmp.getSettings().setDomStorageEnabled(true);
        tmp.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                view.evaluateJavascript(
                        "localStorage.getItem('" + SAVE_KEY + "')", value -> {
                            legacySave = fromJsString(value);
                            view.destroy();
                            if (legacySave != null) {
                                // перенос запустится, когда игра догрузится
                                mergePending = true;
                            }
                            then.run();
                        });
            }
        });
        tmp.loadUrl(LEGACY_START_URL);
    }

    /**
     * Переносит сохранение, если оно «дальше» нынешнего: игрок мог успеть
     * поиграть и в 1.2.3, и в 1.2.4–1.2.5, и обе игрыны сохранения важны.
     * Сначала пишем новое, только потом стираем старое — чтобы обрыв на
     * середине не привёл к потере данных.
     */
    private void mergeLegacySave() {
        if (legacySave == null) {
            rememberMigrated();
            return;
        }
        web.evaluateJavascript("localStorage.getItem('" + SAVE_KEY + "')", value -> {
            String current = fromJsString(value);
            if (progress(current) >= progress(legacySave)) {
                rememberMigrated();
                forgetLegacySave();
                return;
            }
            web.evaluateJavascript(
                    "localStorage.setItem('" + SAVE_KEY + "'," + JSONObject.quote(legacySave) + ")",
                    written -> {
                        rememberMigrated();
                        forgetLegacySave();
                        web.postDelayed(web::reload, 150);
                    });
        });
    }

    /** Стирает перенесённое сохранение по старому адресу, чтобы не трогать снова. */
    private void forgetLegacySave() {
        final WebView tmp = new WebView(this);
        tmp.getSettings().setJavaScriptEnabled(true);
        tmp.getSettings().setDomStorageEnabled(true);
        tmp.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                view.evaluateJavascript("localStorage.removeItem('" + SAVE_KEY + "')",
                        value -> view.destroy());
            }
        });
        tmp.loadUrl(LEGACY_START_URL);
    }

    /** Распаковывает значение, пришедшее из evaluateJavascript. */
    private static String fromJsString(String value) {
        if (value == null || value.equals("null")) {
            return null;
        }
        try {
            return new JSONArray("[" + value + "]").optString(0, null);
        } catch (JSONException err) {
            return null;
        }
    }

    /**
     * Насколько далеко продвинулось сохранение. Сравниваем по числу решённых
     * примеров: оно только растёт и не зависит от того, много ли сейчас денег.
     */
    private static double progress(String saveJson) {
        if (saveJson == null) {
            return -1;
        }
        try {
            JSONObject save = new JSONObject(saveJson);
            JSONObject stats = save.optJSONObject("stats");
            double solved = stats == null ? 0 : stats.optDouble("solved", 0);
            double earned = stats == null ? 0 : stats.optDouble("earned", 0);
            return solved + earned / 1e9;    // деньги лишь различают равные по примерам
        } catch (JSONException err) {
            return -1;
        }
    }

    // ------------------------------------------------------------------
    // Мост к игре: поиск сервера аккаунтов в локальной сети
    // ------------------------------------------------------------------
    /**
     * Игра зовёт MathIdleNative.findServers(), получает список адресов и
     * пробует их сама. Сделано нативно по двум причинам: из JavaScript
     * нельзя отправить UDP-пакет, а обычный fetch не проходит мимо CORS
     * и запрета на небезопасные подключения.
     */
    private class NativeBridge {

        @JavascriptInterface
        public void findServers() {
            Executors.newSingleThreadExecutor().execute(new Runnable() {
                @Override
                public void run() {
                    final List<String> found = new ArrayList<>();
                    try {
                        for (String url : discover()) {
                            if (!found.contains(url)) {
                                found.add(url);
                            }
                        }
                    } catch (Exception err) {
                        // Поиск — необязательная удобная функция: его поломка
                        // не должна ронять игру, адрес вводят и руками.
                        found.clear();
                    }
                    final String json = toJson(found);
                    ui.post(new Runnable() {
                        @Override
                        public void run() {
                            if (web == null) {
                                return;
                            }
                            web.evaluateJavascript(
                                    "window.MathIdleNativeServers && "
                                            + "window.MathIdleNativeServers(" + json + ")", null);
                        }
                    });
                }
            });
        }
    }

    private String toJson(List<String> items) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < items.size(); i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append('"').append(items.get(i).replace("\\", "\\\\").replace("\"", "\\\"")).append('"');
        }
        return sb.append(']').toString();
    }

    /** Ищем сервер: спросим по UDP, а если не вышло — переберём адреса сети. */
    private List<String> discover() {
        List<String> urls = new ArrayList<>();
        try {
            urls.addAll(byBroadcast());
            if (urls.isEmpty()) {
                urls.addAll(byProbing());
            }
        } catch (Exception err) {
            // Поиск — необязательная удобная функция. Любая его поломка
            // не должна ронять игру: адрес можно ввести и руками.
            urls.clear();
        }
        return urls;
    }

    /**
     * UDP-«пинг»: телефон спрашивает «есть ли тут сервер?» — так делают все
     * приложения для поиска принтеров и колонок в сети. Отвечает сервер
     * аккаунтов, запущенный на компьютере.
     */
    private List<String> byBroadcast() {
        List<String> urls = new ArrayList<>();
        DatagramSocket socket = null;
        try {
            socket = new DatagramSocket();
            socket.setBroadcast(true);
            socket.setSoTimeout(1200);
            byte[] ping = DISCOVERY_TOKEN.getBytes("UTF-8");
            for (String broadcast : broadcastAddresses()) {
                socket.send(new DatagramPacket(ping, ping.length,
                        InetAddress.getByName(broadcast), DISCOVERY_PORT));
            }
            long until = System.currentTimeMillis() + 1500;
            byte[] buffer = new byte[512];
            while (System.currentTimeMillis() < until) {
                DatagramPacket reply = new DatagramPacket(buffer, buffer.length);
                socket.receive(reply);
                String text = new String(reply.getData(), 0, reply.getLength(), "UTF-8");
                if (text.contains(DISCOVERY_TOKEN)) {
                    urls.add("http://" + reply.getAddress().getHostAddress() + ":" + DISCOVERY_PORT);
                }
            }
        } catch (Exception ignored) {
            // сеть может быть без широковещания — это не ошибка
        } finally {
            if (socket != null) {
                socket.close();
            }
        }
        return urls;
    }

    /**
     * Запасной путь: узнаём свою подсеть и спрашиваем сервер по HTTP
     * несколько адресов подряд. Отвечает только наш сервер — он отдаёт
     * заголовок X-MathIdle.
     */
    private List<String> byProbing() {
        List<String> urls = new ArrayList<>();
        String prefix = subnetPrefix();
        if (prefix == null) {
            return urls;
        }
        // prefix уже кончается точкой: «192.168.1.» — просто дописываем
        // номер узла. Ничего разбирать не надо: префикс всегда с точкой.
        // Нашли несколько — хватит, дальше идти незачем.
        for (int host = 1; host <= 254 && urls.size() < 3; host++) {
            if (responds(prefix + host)) {
                urls.add("http://" + prefix + host + ":" + DISCOVERY_PORT);
            }
        }
        return urls;
    }

    private boolean responds(String ip) {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(
                    "http://" + ip + ":" + DISCOVERY_PORT + "/api/health").openConnection();
            conn.setConnectTimeout(400);
            conn.setReadTimeout(400);
            conn.setRequestMethod("GET");
            if (conn.getResponseCode() == 200
                    && "mathidle".equalsIgnoreCase(conn.getHeaderField("X-MathIdle"))) {
                return true;
            }
        } catch (SocketTimeoutException ignored) {
            // адрес не наш
        } catch (Exception ignored) {
            // адрес не наш
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
        return false;
    }

    /** Адреса широковещания: 255.255.255.255 и адрес сети этого Wi-Fi. */
    private List<String> broadcastAddresses() {
        List<String> list = new ArrayList<>();
        list.add("255.255.255.255");
        String prefix = subnetPrefix();
        if (prefix != null) {
            list.add(prefix + "255");
        }
        return list;
    }

    /** «192.168.1.» — префикс подсети телефона по данным Wi-Fi. */
    private String subnetPrefix() {
        try {
            WifiManager wifi = (WifiManager) getApplicationContext()
                    .getSystemService(Context.WIFI_SERVICE);
            int ip = wifi.getConnectionInfo().getIpAddress();
            if (ip != 0) {
                return String.format("%d.%d.%d.",
                        ip & 0xFF, (ip >> 8) & 0xFF, (ip >> 16) & 0xFF);
            }
        } catch (Exception ignored) {
            // нет доступа к Wi-Fi — попробуем иначе
        }
        // запасной вариант: адрес сервера DNS обычно в той же подсети
        try {
            InetAddress local = InetAddress.getLocalHost();
            byte[] raw = local.getAddress();
            if (raw != null && raw.length == 4) {
                return String.format("%d.%d.%d.", raw[0] & 0xFF, raw[1] & 0xFF, raw[2] & 0xFF);
            }
        } catch (UnknownHostException ignored) {
            // ничего не вышло
        }
        return null;
    }

    /** Отдаёт файл из assets/www по «виртуальному» домену. */
    private WebResourceResponse serveAsset(Uri uri) {
        if (uri == null || !HOST.equals(uri.getHost())) {
            return null;
        }
        String path = uri.getPath();
        if (path == null || path.equals("/")) {
            path = "/index.html";
        }
        if (path.contains("..")) {           // никаких выходов из assets
            return null;
        }
        String assetPath = ASSET_ROOT + path;
        try {
            InputStream stream = getAssets().open(assetPath);
            WebResourceResponse response = new WebResourceResponse(
                    mimeOf(path), "utf-8", stream);
            response.setStatusCodeAndReasonPhrase(200, "OK");
            Map<String, String> headers = new HashMap<>();
            headers.put("Cache-Control", "no-cache");
            response.setResponseHeaders(headers);
            return response;
        } catch (IOException e) {
            return null;
        }
    }

    private static String mimeOf(String path) {
        int dot = path.lastIndexOf('.');
        if (dot < 0) {
            return "application/octet-stream";
        }
        String type = MIME.get(path.substring(dot + 1).toLowerCase());
        return type != null ? type : "application/octet-stream";
    }

    /** Аппаратная клавиатура: навигацию ведём сами, системный ввод не нужен. */
    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getAction() == KeyEvent.ACTION_DOWN) {
            int code = event.getKeyCode();
            if (code >= KeyEvent.KEYCODE_0 && code <= KeyEvent.KEYCODE_9) {
                return true;
            }
            if (code == KeyEvent.KEYCODE_DEL || code == KeyEvent.KEYCODE_ENTER
                    || code == KeyEvent.KEYCODE_TAB || code == KeyEvent.KEYCODE_BACK) {
                return true;
            }
        }
        return super.dispatchKeyEvent(event);
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (web != null) {
            web.evaluateJavascript("window.dispatchEvent(new Event('beforeunload'))", null);
            web.onPause();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) {
            web.onResume();
        }
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
