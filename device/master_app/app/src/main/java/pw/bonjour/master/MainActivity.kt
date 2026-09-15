package pw.bonjour.master

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.webkit.CookieManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.ProgressBar
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity

/**
 * Оболочка над кабинетом сотрудника на app.bonjour.pw.
 *
 * Своих экранов у приложения нет намеренно: всё, что видит мастер, — это
 * веб-кабинет, поэтому новый раздел или исправление приезжают на телефоны
 * вместе с деплоем сервера, без пересборки и переустановки APK.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var errorView: View
    private lateinit var progress: ProgressBar

    // Выбор фото в профиле: WebView сам диалог выбора файла не показывает,
    // он ждёт ответа через этот колбэк.
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private val pickFile = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        fileCallback?.onReceiveValue(if (uri != null) arrayOf(uri) else null)
        fileCallback = null
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.web)
        errorView = findViewById(R.id.error)
        progress = findViewById(R.id.progress)
        findViewById<Button>(R.id.retry).setOnClickListener { retry() }

        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        CookieManager.getInstance().setAcceptCookie(true)
        webView.settings.apply {
            javaScriptEnabled = true
            // Кабинет держит токен входа в localStorage: без DOM storage
            // мастеру пришлось бы входить заново при каждом запуске.
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            setSupportZoom(false)
            // По этой метке кабинет прячет то, что внутри WebView не работает:
            // push-уведомления браузера и скачивание файлов.
            userAgentString = "$userAgentString $USER_AGENT_MARK/${BuildConfig.VERSION_NAME}"
        }
        webView.webViewClient = Client()
        webView.webChromeClient = Chrome()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack() else finish()
            }
        })

        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            webView.loadUrl(BuildConfig.START_URL)
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        webView.saveState(outState)
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
    }

    override fun onPause() {
        webView.onPause()
        // Иначе куки, выданные при входе, могут не успеть лечь на диск, если
        // система выгрузит приложение из фона.
        CookieManager.getInstance().flush()
        super.onPause()
    }

    override fun onDestroy() {
        webView.destroy()
        super.onDestroy()
    }

    private fun showError() {
        webView.visibility = View.INVISIBLE
        progress.visibility = View.GONE
        errorView.visibility = View.VISIBLE
    }

    private fun retry() {
        errorView.visibility = View.GONE
        webView.visibility = View.VISIBLE
        val url = webView.url
        if (url.isNullOrBlank() || url == "about:blank") {
            webView.loadUrl(BuildConfig.START_URL)
        } else {
            webView.reload()
        }
    }

    private fun openExternally(uri: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        } catch (e: ActivityNotFoundException) {
            // Открыть нечем (например, tel: на планшете без звонков) —
            // остаёмся на месте, для кабинета это не ошибка.
        }
    }

    private inner class Client : WebViewClient() {
        private var mainFrameFailed = false

        override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
            mainFrameFailed = false
            progress.visibility = View.VISIBLE
        }

        override fun onPageFinished(view: WebView, url: String?) {
            progress.visibility = View.GONE
            if (!mainFrameFailed) {
                errorView.visibility = View.GONE
                webView.visibility = View.VISIBLE
            }
        }

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (request.isForMainFrame) {
                mainFrameFailed = true
                showError()
            }
        }

        // Туннель, потерявший связь с сервером, отвечает 502/503 — для мастера
        // это та же «нет связи», а не страница с кодом ошибки.
        override fun onReceivedHttpError(
            view: WebView,
            request: WebResourceRequest,
            errorResponse: WebResourceResponse,
        ) {
            if (request.isForMainFrame && errorResponse.statusCode >= 500) {
                mainFrameFailed = true
                showError()
            }
        }

        // Внутри приложения — только кабинет. Всё остальное (звонок, почта,
        // сторонний сайт) открывается там, где ему место.
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val uri = request.url
            if (uri.scheme == "https" && uri.host == BuildConfig.APP_HOST) return false
            openExternally(uri)
            return true
        }
    }

    private inner class Chrome : WebChromeClient() {
        override fun onProgressChanged(view: WebView, newProgress: Int) {
            progress.progress = newProgress
        }

        override fun onShowFileChooser(
            view: WebView,
            filePathCallback: ValueCallback<Array<Uri>>,
            fileChooserParams: FileChooserParams,
        ): Boolean {
            fileCallback?.onReceiveValue(null)
            fileCallback = filePathCallback
            val type = fileChooserParams.acceptTypes.firstOrNull { it.isNotBlank() } ?: "*/*"
            return try {
                pickFile.launch(type)
                true
            } catch (e: ActivityNotFoundException) {
                fileCallback = null
                false
            }
        }
    }

    companion object {
        const val USER_AGENT_MARK = "BonjourMasterApp"
    }
}
