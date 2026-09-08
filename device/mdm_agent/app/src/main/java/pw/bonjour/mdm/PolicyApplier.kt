package pw.bonjour.mdm

import android.app.admin.DevicePolicyManager
import android.content.Context
import android.os.UserManager
import org.json.JSONObject

/** Применяет политику к телефону.
 *
 *  Каждый запрет ставится отдельно и в своём try/catch: прошивки вендоров
 *  расходятся в том, какие ограничения поддерживают, и один неподдерживаемый
 *  запрет не должен ронять применение всей политики. Что не встало — уезжает
 *  на сервер текстом в last_error, а не молча теряется.
 */
object PolicyApplier {

    private val RESTRICTIONS: Map<String, String> = mapOf(
        "no_factory_reset" to UserManager.DISALLOW_FACTORY_RESET,
        "no_install_apps" to UserManager.DISALLOW_INSTALL_APPS,
        "no_uninstall_apps" to UserManager.DISALLOW_UNINSTALL_APPS,
        "no_install_unknown_sources" to UserManager.DISALLOW_INSTALL_UNKNOWN_SOURCES,
        "no_safe_boot" to UserManager.DISALLOW_SAFE_BOOT,
        "no_add_user" to UserManager.DISALLOW_ADD_USER,
        "no_modify_accounts" to UserManager.DISALLOW_MODIFY_ACCOUNTS,
        "no_config_mobile_networks" to UserManager.DISALLOW_CONFIG_MOBILE_NETWORKS,
        "no_config_tethering" to UserManager.DISALLOW_CONFIG_TETHERING,
        "no_debugging_features" to UserManager.DISALLOW_DEBUGGING_FEATURES,
        "no_outgoing_calls" to UserManager.DISALLOW_OUTGOING_CALLS,
        "no_sms" to UserManager.DISALLOW_SMS,
        "no_bluetooth" to UserManager.DISALLOW_BLUETOOTH,
        "no_usb_file_transfer" to UserManager.DISALLOW_USB_FILE_TRANSFER,
        "no_config_wifi" to UserManager.DISALLOW_CONFIG_WIFI
    )

    /** Разрешения, которые агент выдаёт себе сам. Фоновое — обязательно:
     *  чек-ин работает в фоне, а с Android 10 без него координат не получить. */
    private val GRANTED_PERMISSIONS = listOf(
        android.Manifest.permission.ACCESS_FINE_LOCATION,
        android.Manifest.permission.ACCESS_COARSE_LOCATION,
        android.Manifest.permission.ACCESS_BACKGROUND_LOCATION,
        android.Manifest.permission.CAMERA,
        // С Android 13 без него уведомление постоянного сервиса не показывается,
        // а сервис без видимого уведомления система вправе прибить.
        android.Manifest.permission.POST_NOTIFICATIONS
    )

    /** @return строка с описанием проблем или null, если всё применилось. */
    fun apply(ctx: Context, policy: JSONObject): String? {
        if (!Dpm.isOwner(ctx)) return "not_device_owner"

        val dpm = Dpm.manager(ctx)
        val admin = Dpm.admin(ctx)
        val problems = mutableListOf<String>()

        // Автовыдача разрешений: иначе запрос координат по команде locate
        // упрётся в системный диалог, которого на телефоне никто не увидит.
        runCatching {
            dpm.setPermissionPolicy(admin, DevicePolicyManager.PERMISSION_POLICY_AUTO_GRANT)
        }.onFailure { problems.add("permission_policy: " + it.message) }

        // Автовыдача срабатывает только когда приложение само запрашивает
        // разрешение, а агент ничего не запрашивает — у него нет экранов, где
        // показать диалог. Поэтому владелец устройства выдаёт их себе напрямую.
        GRANTED_PERMISSIONS.forEach { permission ->
            runCatching {
                dpm.setPermissionGrantState(
                    admin,
                    ctx.packageName,
                    permission,
                    DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED
                )
            }.onFailure { problems.add(permission.substringAfterLast('.') + ": " + it.message) }
        }

        val restrictions = policy.optJSONObject("restrictions") ?: JSONObject()
        RESTRICTIONS.forEach { entry ->
            val enabled = restrictions.optBoolean(entry.key, false)
            runCatching {
                if (enabled) {
                    dpm.addUserRestriction(admin, entry.value)
                } else {
                    dpm.clearUserRestriction(admin, entry.value)
                }
            }.onFailure { problems.add(entry.key + ": " + it.message) }
        }

        runCatching {
            dpm.setCameraDisabled(admin, restrictions.optBoolean("camera_disabled", false))
        }.onFailure { problems.add("camera_disabled: " + it.message) }

        runCatching {
            dpm.setScreenCaptureDisabled(admin, restrictions.optBoolean("no_screen_capture", false))
        }.onFailure { problems.add("no_screen_capture: " + it.message) }

        // Киоск: разрешаем перечисленным приложениям залипать на экране.
        // Полноценный киоск (автозапуск и подмена рабочего стола) — отдельная
        // задача; здесь только список допущенных пакетов.
        val kiosk = policy.optJSONObject("kiosk") ?: JSONObject()
        val kioskPackages = kiosk.optJSONArray("packages")
        val packages = if (kiosk.optBoolean("enabled", false) && kioskPackages != null) {
            val collected = mutableListOf<String>()
            for (i in 0 until kioskPackages.length()) {
                val name = kioskPackages.optString(i)
                if (name.isNotBlank()) collected.add(name)
            }
            collected.toTypedArray()
        } else {
            emptyArray()
        }
        runCatching {
            dpm.setLockTaskPackages(admin, packages)
        }.onFailure { problems.add("kiosk: " + it.message) }

        return if (problems.isEmpty()) null else problems.joinToString("; ")
    }
}
