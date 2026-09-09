package pw.bonjour.mdm

import android.app.Activity
import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.view.WindowManager

/** Разбудить экран и показать рабочий стол.
 *
 *  Обратное к `lock`. Телефон лежит с погашенным экраном — оператор нажимает
 *  кнопку, экран загорается, и виден рабочий стол, а не замок.
 *
 *  Своего вида у активности нет: она нужна только как повод разбудить экран.
 *  Разбудить его иначе нельзя — включение дисплея привязано к окну, которое
 *  просит `turnScreenOn`, а не к отдельному вызову.
 *
 *  Замок снимается только если он не защищённый. Если на телефоне стоит код,
 *  система покажет запрос кода — и это правильно: обойти его значило бы
 *  сделать код бесполезным. Поставить или снять код можно отдельной командой
 *  (см. ScreenLock), и это осознанное действие, а не побочный эффект побудки.
 */
class WakeActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

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

        val showHome = intent.getBooleanExtra(EXTRA_HOME, true)

        val keyguard = getSystemService(Context.KEYGUARD_SERVICE) as? KeyguardManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && keyguard != null) {
            // Незащищённый замок система снимет сама; защищённый — покажет
            // запрос кода. В обоих случаях идём дальше: наша задача кончается
            // на том, что экран горит.
            runCatching {
                keyguard.requestDismissKeyguard(this, object : KeyguardManager.KeyguardDismissCallback() {
                    override fun onDismissSucceeded() = finishTo(showHome)
                    override fun onDismissError() = finishTo(showHome)
                    override fun onDismissCancelled() = finishTo(false)
                })
            }.onFailure { finishTo(showHome) }
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD)
            finishTo(showHome)
        }
    }

    /** Уйти с дороги, оставив на экране то, что просили. */
    private fun finishTo(showHome: Boolean) {
        if (showHome) {
            // Явно просим рабочий стол: без этого на экране останется то
            // приложение, в котором телефон уснул. В киоске «домой» — это сам
            // киоск, что для такого телефона и есть рабочий стол.
            runCatching {
                startActivity(
                    Intent(Intent.ACTION_MAIN)
                        .addCategory(Intent.CATEGORY_HOME)
                        .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                )
            }
        }
        finish()
    }

    companion object {
        private const val EXTRA_HOME = "home"

        /** @param keepSeconds сколько удерживать экран включённым.
         *  @param showHome показать рабочий стол вместо того, что было открыто. */
        fun wake(ctx: Context, keepSeconds: Int, showHome: Boolean): Pair<String, String?> = try {
            // Блокировка питания — подстраховка к активности: на части прошивок
            // экран гаснет обратно быстрее, чем оператор успеет посмотреть.
            // Со своим таймаутом, чтобы забытая блокировка не жгла батарею.
            runCatching {
                val pm = ctx.getSystemService(Context.POWER_SERVICE) as PowerManager
                @Suppress("DEPRECATION")
                val lock = pm.newWakeLock(
                    PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP,
                    "mdm:wake"
                )
                lock.acquire(keepSeconds * 1000L)
            }

            ctx.startActivity(
                Intent(ctx, WakeActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                    .putExtra(EXTRA_HOME, showHome)
            )
            "done" to (if (showHome) "экран включён, показан рабочий стол" else "экран включён")
        } catch (e: Exception) {
            "failed" to (e.javaClass.simpleName + ": " + e.message)
        }
    }
}
