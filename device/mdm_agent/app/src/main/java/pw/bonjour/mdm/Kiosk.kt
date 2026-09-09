package pw.bonjour.mdm

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import org.json.JSONObject

/** Управление киоском правами владельца устройства.
 *
 *  Настоящий киоск (COSU — corporate single-use): целевое приложение становится
 *  домашним экраном и работает в режиме закрепления, телефон больше ничем не
 *  занять. Собрано из штатных механизмов Device Owner, без рутинга.
 */
object Kiosk {

    /** Применить настройки киоска из политики. Возврат — текст проблемы или null. */
    fun apply(ctx: Context, kiosk: JSONObject): String? {
        val dpm = Dpm.manager(ctx)
        val admin = Dpm.admin(ctx)
        val enabled = kiosk.optBoolean("enabled", false)
        val home = kiosk.optString("home")

        return try {
            if (!enabled) {
                clear(ctx)
                return null
            }

            // Разрешаем закрепление целевому приложению, дополнительным и самому
            // агенту (чтобы он мог работать и, если надо, показать свой экран).
            val allowed = linkedSetOf(ctx.packageName)
            if (home.isNotBlank()) allowed.add(home)
            kiosk.optJSONArray("packages")?.let { arr ->
                for (i in 0 until arr.length()) arr.optString(i).takeIf { it.isNotBlank() }?.let(allowed::add)
            }
            dpm.setLockTaskPackages(admin, allowed.toTypedArray())

            // Что оставить доступным в киоске: кнопка домой, недавние,
            // уведомления, системная информация.
            var features = 0
            if (kiosk.optBoolean("allow_home_button", false)) features = features or DevicePolicyManager.LOCK_TASK_FEATURE_HOME
            if (kiosk.optBoolean("allow_recents", false)) features = features or DevicePolicyManager.LOCK_TASK_FEATURE_OVERVIEW
            if (kiosk.optBoolean("allow_notifications", true)) features = features or DevicePolicyManager.LOCK_TASK_FEATURE_NOTIFICATIONS
            if (kiosk.optBoolean("allow_system_info", true)) features = features or DevicePolicyManager.LOCK_TASK_FEATURE_SYSTEM_INFO
            runCatching { dpm.setLockTaskFeatures(admin, features) }

            // Наша активность становится домашним экраном: нажатие «домой» и
            // перезагрузка ведут в киоск, а не на обычный рабочий стол.
            val filter = IntentFilter(Intent.ACTION_MAIN).apply {
                addCategory(Intent.CATEGORY_HOME)
                addCategory(Intent.CATEGORY_DEFAULT)
            }
            dpm.addPersistentPreferredActivity(
                admin, filter, ComponentName(ctx, KioskActivity::class.java)
            )
            null
        } catch (e: Exception) {
            "kiosk: " + e.message
        }
    }

    /** Снять киоск: вернуть домашний экран системе и очистить закрепление. */
    fun clear(ctx: Context) {
        val dpm = Dpm.manager(ctx)
        val admin = Dpm.admin(ctx)
        runCatching { dpm.clearPackagePersistentPreferredActivities(admin, ctx.packageName) }
        runCatching { dpm.setLockTaskPackages(admin, emptyArray()) }
        runCatching { dpm.setLockTaskFeatures(admin, DevicePolicyManager.LOCK_TASK_FEATURE_NONE) }
    }

    /** Аварийный выход по команде: снять киоск и погасить политику локально,
     *  чтобы KioskActivity больше не перехватывала домашний экран. */
    fun exit(ctx: Context): Pair<String, String?> {
        clear(ctx)
        val policy = Prefs.policy(ctx)
        policy.optJSONObject("kiosk")?.put("enabled", false)
        Prefs.setPolicy(ctx, policy, Prefs.policyVersion(ctx))
        return "done" to "киоск снят"
    }
}
