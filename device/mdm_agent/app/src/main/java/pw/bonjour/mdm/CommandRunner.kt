package pw.bonjour.mdm

import android.content.Context
import android.os.Build
import org.json.JSONObject

/** Исполнитель команд, пришедших с сервера.
 *
 *  Набор типов держится в синхроне с app/schemas/mdm.py::CommandType.
 *  Возврат null означает «подтверждение придёт асинхронно» — так устроены
 *  установка и удаление приложений.
 */
object CommandRunner {

    /** @return пара (статус, текст результата) или null, если ack придёт позже. */
    fun run(ctx: Context, command: JSONObject): Pair<String, String?>? {
        val type = command.optString("type")
        val params = command.optJSONObject("params") ?: JSONObject()
        val commandId = command.optString("id")

        return try {
            when (type) {
                "refresh_apps" -> {
                    // Сбрасываем отпечаток: ближайший чек-ин увидит расхождение
                    // и отправит полный список заново.
                    Prefs.setReportedAppsHash(ctx, "")
                    "done" to null
                }

                "apply_policy" -> {
                    val problem = PolicyApplier.apply(ctx, Prefs.policy(ctx))
                    if (problem == null) "done" to null else "failed" to problem
                }

                "lock" -> {
                    Dpm.manager(ctx).lockNow()
                    "done" to null
                }

                "reboot" -> {
                    // Требует владельца устройства и отсутствия активного звонка.
                    Dpm.manager(ctx).reboot(Dpm.admin(ctx))
                    "done" to null
                }

                "locate" -> Locator.locate(ctx)

                "camera" -> {
                    val lens = if (params.optString("lens") == "front") "front" else "back"
                    val error = Camera.captureAndUpload(ctx, commandId, lens)
                    if (error == null) "done" to lens else "failed" to error
                }

                "install_apk" -> {
                    val url = params.optString("url")
                    if (url.isBlank()) {
                        "failed" to "no_url"
                    } else {
                        val error = ApkInstaller.install(ctx, commandId, url)
                        if (error == null) null else "failed" to error
                    }
                }

                "uninstall" -> {
                    val packageName = params.optString("package")
                    if (packageName.isBlank()) {
                        "failed" to "no_package"
                    } else {
                        val error = ApkInstaller.uninstall(ctx, commandId, packageName)
                        if (error == null) null else "failed" to error
                    }
                }

                "release_owner" -> {
                    // Аварийный люк: агент добровольно перестаёт быть владельцем
                    // устройства. Без него APK с другой подписью можно поставить
                    // только сбросом телефона до заводских настроек.
                    Dpm.manager(ctx).clearDeviceOwnerApp(ctx.packageName)
                    "done" to null
                }

                "wipe" -> {
                    // Возврата отсюда не будет: телефон уходит в сброс.
                    //
                    // wipeData на Android 14 не сбрасывает аппарат, а пытается
                    // удалить пользователя, и падает с «User 0 is a system user
                    // and cannot be removed» — проверено на realme RMX3938.
                    // Для полностью управляемых устройств там появился отдельный
                    // wipeDevice, который делает именно заводской сброс.
                    val dpm = Dpm.manager(ctx)
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                        dpm.wipeDevice(0)
                    } else {
                        dpm.wipeData(0)
                    }
                    "done" to null
                }

                else -> "failed" to ("unknown_command_" + type)
            }
        } catch (e: Exception) {
            "failed" to (e.javaClass.simpleName + ": " + e.message)
        }
    }
}
