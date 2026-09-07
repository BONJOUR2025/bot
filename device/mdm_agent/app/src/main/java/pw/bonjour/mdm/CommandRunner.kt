package pw.bonjour.mdm

import android.content.Context
import android.location.LocationManager
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

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

                "locate" -> locate(ctx)

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
                    Dpm.manager(ctx).wipeData(0)
                    "done" to null
                }

                else -> "failed" to ("unknown_command_" + type)
            }
        } catch (e: Exception) {
            "failed" to (e.javaClass.simpleName + ": " + e.message)
        }
    }

    private fun locate(ctx: Context): Pair<String, String?> {
        val manager = ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        // Берём последнюю известную точку, а не запрашиваем свежую: телефон в
        // салоне лежит в помещении, ожидание фикса GPS упрётся в таймаут, а
        // сетевая точка с точностью до квартала отвечает на вопрос «где аппарат».
        val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
        var best: android.location.Location? = null
        for (provider in providers) {
            val location = try {
                manager.getLastKnownLocation(provider)
            } catch (e: SecurityException) {
                null
            } ?: continue
            if (best == null || location.time > best.time) best = location
        }
        val found = best ?: return "failed" to "no_location"

        val stamp = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }.format(Date(found.time))

        Prefs.setPendingLocation(ctx, found.latitude, found.longitude, stamp)
        return "done" to (found.latitude.toString() + "," + found.longitude.toString())
    }
}
