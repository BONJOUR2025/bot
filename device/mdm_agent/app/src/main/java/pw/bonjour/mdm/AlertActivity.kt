package pw.bonjour.mdm

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import java.lang.ref.WeakReference

/** Сообщение сотруднику во весь экран.
 *
 *  Текст на экране блокировки (`message`) видно только когда телефон заблокирован
 *  и только тому, кто на него посмотрит. Это годится для потерянного аппарата,
 *  но не годится, когда надо сказать что-то работающему человеку прямо сейчас:
 *  он смотрит в приложение и никакой надписи под замком не увидит.
 *
 *  Поэтому здесь отдельный экран: он поднимается поверх всего, будит телефон и
 *  показывается даже поверх блокировки.
 *
 *  Закрыть можно кнопкой, если оператор это разрешил. Неснимаемое окно — не
 *  каприз: им останавливают работу на телефоне (например, аппарат уносят из
 *  салона), и тогда закрывать его должен тот же, кто открыл, командой
 *  stop_alert. Кнопка «назад» в таком режиме тоже не спасает.
 */
class AlertActivity : Activity() {

    private var dismissible = true

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        showOverLockScreen()
        current = WeakReference(this)
        render(intent)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        // Второе сообщение подряд не должно плодить экраны: перерисовываем это.
        if (intent != null) {
            setIntent(intent)
            render(intent)
        }
    }

    private fun render(intent: Intent) {
        val title = intent.getStringExtra(EXTRA_TITLE).orEmpty()
        val text = intent.getStringExtra(EXTRA_TEXT).orEmpty()
        dismissible = intent.getBooleanExtra(EXTRA_DISMISSIBLE, true)
        setContentView(buildView(title, text))
    }

    private fun buildView(title: String, text: String): ViewGroup {
        val density = resources.displayMetrics.density
        val pad = (24 * density).toInt()

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.parseColor("#101418"))
            setPadding(pad, pad, pad, pad)
        }

        if (title.isNotBlank()) {
            root.addView(TextView(this).apply {
                setText(title)
                setTextColor(Color.WHITE)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 26f)
                gravity = Gravity.CENTER
                setPadding(0, 0, 0, (16 * density).toInt())
            })
        }

        root.addView(TextView(this).apply {
            setText(text)
            setTextColor(Color.parseColor("#E6E9EC"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 19f)
            gravity = Gravity.CENTER
        })

        if (dismissible) {
            root.addView(Button(this).apply {
                setText("Понятно")
                setOnClickListener { finish() }
                (layoutParams as? LinearLayout.LayoutParams ?: LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT
                )).also {
                    it.topMargin = (28 * density).toInt()
                    layoutParams = it
                }
            })
        }
        return root
    }

    /** Поверх блокировки и с включением экрана: сообщение бесполезно, если его
     *  увидят только через час, когда телефон возьмут в руки. */
    private fun showOverLockScreen() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                    or WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
            )
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    override fun onBackPressed() {
        // Неснимаемое окно не должно закрываться «назад»: иначе запрет работы
        // на телефоне снимается одним нажатием и смысла в нём нет.
        if (dismissible) super.onBackPressed()
    }

    override fun onDestroy() {
        if (current?.get() === this) current = null
        super.onDestroy()
    }

    companion object {
        private const val EXTRA_TITLE = "title"
        private const val EXTRA_TEXT = "text"
        private const val EXTRA_DISMISSIBLE = "dismissible"

        /** Ссылка на открытый экран, чтобы его можно было закрыть по команде.
         *  Слабая: держать активность жёстко — это утечка, а если её уже нет,
         *  закрывать всё равно нечего. */
        private var current: WeakReference<AlertActivity>? = null

        fun show(ctx: Context, title: String, text: String, dismissible: Boolean) {
            val intent = Intent(ctx, AlertActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                putExtra(EXTRA_TITLE, title)
                putExtra(EXTRA_TEXT, text)
                putExtra(EXTRA_DISMISSIBLE, dismissible)
            }
            ctx.startActivity(intent)
        }

        /** @return true, если было что закрывать.
         *
         *  Вызывается из потока команд, а не из главного, поэтому finish()
         *  переносим на UI-поток. Всё обёрнуто: закрытие окна не должно уметь
         *  провалить команду — если активности уже нет, цель и так достигнута.
         */
        fun close(): Boolean {
            val activity = current?.get()
            current = null
            if (activity == null) return false
            runCatching { activity.runOnUiThread { runCatching { activity.finish() } } }
            return true
        }
    }
}
