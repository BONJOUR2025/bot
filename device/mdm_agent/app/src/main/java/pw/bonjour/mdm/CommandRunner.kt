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

                "wake" -> WakeActivity.wake(
                    ctx,
                    params.optInt("seconds", 60),
                    params.optBoolean("show_home", true)
                )

                "reboot" -> {
                    // Требует владельца устройства и отсутствия активного звонка.
                    Dpm.manager(ctx).reboot(Dpm.admin(ctx))
                    "done" to null
                }

                "locate" -> Locator.locate(ctx)

                "camera" -> {
                    val lens = if (params.optString("lens") == "front") "front" else "back"
                    // Съёмка идёт в foreground-сервисе: из фона Android 14 к
                    // камере не пускает. Подтверждение придёт оттуда асинхронно.
                    CameraService.capture(ctx, commandId, lens)
                    null
                }

                "install_apk" -> {
                    val url = params.optString("url")
                    if (url.isBlank()) {
                        "failed" to "no_url"
                    } else {
                        val error = ApkInstaller.install(ctx, commandId, url)
                        when {
                            error == null -> null  // ставится, ack придёт асинхронно
                            // Та же версия уже стоит — это не сбой, а нечего делать.
                            error.startsWith("already_installed") -> "done" to error
                            else -> "failed" to error
                        }
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

                "ring" -> {
                    Ringer.start(ctx, params.optInt("seconds", 30))
                    "done" to (params.optInt("seconds", 30).toString() + "с")
                }

                "stop_ring" -> {
                    Ringer.stop(ctx)
                    "done" to null
                }

                "message" -> {
                    // Пустой текст снимает сообщение — законный сценарий.
                    val text = params.optString("text")
                    Dpm.manager(ctx).setDeviceOwnerLockScreenInfo(
                        Dpm.admin(ctx), if (text.isBlank()) null else text
                    )
                    "done" to null
                }

                "alert" -> {
                    AlertActivity.show(
                        ctx,
                        params.optString("title"),
                        params.optString("text"),
                        params.optBoolean("dismissible", true)
                    )
                    "done" to (if (params.optBoolean("dismissible", true)) "показано" else "показано, без закрытия")
                }

                "set_password" -> ScreenLock.setPassword(ctx, params.optString("password"))

                "set_play_protect" -> PlayProtect.set(ctx, params.optBoolean("enabled", false))

                "stop_alert" -> {
                    val closed = AlertActivity.close()
                    "done" to (if (closed) "окно закрыто" else "окна не было")
                }

                "clear_app_data" -> {
                    val pkg = params.optString("package")
                    if (pkg.isBlank()) "failed" to "no_package"
                    else DeviceActions.clearAppData(ctx, pkg)
                }

                "set_app_enabled" -> {
                    val pkg = params.optString("package")
                    if (pkg.isBlank()) "failed" to "no_package"
                    else DeviceActions.setAppEnabled(ctx, pkg, params.optBoolean("enabled", true))
                }

                "set_volume" -> {
                    DeviceActions.setVolume(ctx, params.optInt("percent", 100))
                    "done" to null
                }

                "launch_app" -> {
                    val pkg = params.optString("package")
                    if (pkg.isBlank()) "failed" to "no_package"
                    else DeviceActions.launchApp(ctx, pkg)
                }

                "grant_permission" -> {
                    val pkg = params.optString("package")
                    val perm = params.optString("permission")
                    if (pkg.isBlank() || perm.isBlank()) "failed" to "no_package_or_permission"
                    else DeviceActions.grantPermission(ctx, pkg, perm, params.optBoolean("grant", true))
                }

                "set_time_zone" -> {
                    val zone = params.optString("zone")
                    if (zone.isBlank()) "failed" to "no_zone"
                    else DeviceActions.setTimeZone(ctx, zone)
                }

                "set_auto_time" -> DeviceActions.setAutoTime(ctx, params.optBoolean("enabled", true))

                "kiosk_exit" -> Kiosk.exit(ctx)

                "add_wifi" -> {
                    val ssid = params.optString("ssid")
                    if (ssid.isBlank()) "failed" to "no_ssid"
                    else WifiActions.addNetwork(ctx, ssid, params.optString("password"), params.optBoolean("hidden", false))
                }

                "set_stay_awake" -> DeviceActions.setStayAwake(ctx, params.optBoolean("enabled", true))

                "set_status_bar" -> DeviceActions.setStatusBar(ctx, params.optBoolean("disabled", true))

                "set_time" -> {
                    val ms = params.optLong("epoch_ms", 0L)
                    if (ms <= 0L) "failed" to "no_epoch_ms"
                    else DeviceActions.setTime(ctx, ms)
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
