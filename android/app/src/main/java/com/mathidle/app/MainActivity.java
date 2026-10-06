package com.mathidle.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;

/**
 * Тонкая нативная обёртка над HTML5-игрой (assets/www).
 *
 * Игра отдаётся не через file://, а через свой домен appassets.mathidle.local,
 * который отдаёт WebViewClient. Так у страницы нормальный https-origin —
 * иначе в Chromium WebView localStorage (сохранения игры) может не работать.
 *
 * Зависимостей нет вообще (без AndroidX), поэтому APK весит меньше 100 КБ.
 */
public class MainActivity extends Activity {

    private static final String HOST = "appassets.mathidle.local";
    private static final String START_URL = "https://" + HOST + "/index.html";
    private static final String ASSET_ROOT = "www";

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

        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return serveAsset(request.getUrl());
            }
        });

        web.setBackgroundColor(0xFF101420);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.setFocusable(true);
        web.setFocusableInTouchMode(true);

        setContentView(web);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        web.loadUrl(START_URL);
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
