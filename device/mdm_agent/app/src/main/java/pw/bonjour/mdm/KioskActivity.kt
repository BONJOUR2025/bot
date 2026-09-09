package pw.bonjour.mdm

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/** Домашний экран киоска.
 *
 *  Когда киоск включён, эта активность назначена домашним экраном (HOME) через
 *  addPersistentPreferredActivity. Она сразу запускает целевое приложение в
 *  режиме закрепления (lock task) и заново запускает его, если сотрудник из него
 *  вышел — так телефон залипает в одном приложении, как терминал.
 *
 *  Своего экрана у неё нет: она мгновенно перебрасывает в целевое приложение.
 *  Выключается киоск командой kiosk_exit или снятием политики — тогда домашний
 *  экран возвращается системе, а закрепление снимается.
 */
class KioskActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
    }

    override fun onResume() {
        super.onResume()
        val policy = Prefs.policy(this).optJSONObject("kiosk")
        val home = policy?.optString("home")
        if (policy == null || policy.optBoolean("enabled", false).not() || home.isNullOrBlank()) {
            // Киоск выключили — эта активность больше не должна быть домашней;
            // просто уходим, система покажет свой лаунчер.
            finish()
            return
        }

        // Целевое приложение — само наш агент? тогда показывать нечего, остаёмся.
        if (home == packageName) return

        val launch = packageManager.getLaunchIntentForPackage(home)
        if (launch == null) {
            // Приложения нет — не залипаем в пустоту, отдаём управление системе.
            finish()
            return
        }
        // Закрепление запускается на самой активности киоска: целевое приложение
        // из белого списка lock task работает внутри той же закреплённой сессии.
        runCatching { startLockTask() }
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        runCatching { startActivity(launch) }
    }
}
