package pw.bonjour.mdm

import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioManager
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Мелкие действия над устройством и приложениями правами владельца устройства. */
object DeviceActions {

    /** Очистить данные приложения. Себя чистить нельзя — снесём собственный
     *  токен и выпадем из-под управления. */
    fun clearAppData(ctx: Context, pkg: String): Pair<String, String?> {
        if (pkg == ctx.packageName) return "failed" to "нельзя чистить сам агент"
        val dpm = Dpm.manager(ctx)
        val executor = Executors.newSingleThreadExecutor()
        val latch = CountDownLatch(1)
        var ok = false
        return try {
            dpm.clearApplicationUserData(
                Dpm.admin(ctx), pkg, executor
            ) { _, succeeded ->
                ok = succeeded
                latch.countDown()
            }
            latch.await(20, TimeUnit.SECONDS)
            if (ok) "done" to null else "failed" to "очистка не удалась"
        } catch (e: Exception) {
            "failed" to (e.message ?: "не удалось")
        } finally {
            executor.shutdown()
        }
    }

    /** Скрыть/показать приложение. Владелец устройства прячет пакет целиком —
     *  для сотрудника его как будто нет, но приложение и его данные на месте. */
    fun setAppEnabled(ctx: Context, pkg: String, enabled: Boolean): Pair<String, String?> {
        if (pkg == ctx.packageName) return "failed" to "нельзя скрыть сам агент"
        return try {
            // Возврат false означает, что состояние не поменялось — почти всегда
            // потому, что такого пакета на телефоне нет. Не выдаём это за успех.
            val ok = Dpm.manager(ctx).setApplicationHidden(Dpm.admin(ctx), pkg, !enabled)
            if (ok) "done" to (if (enabled) "показано" else "скрыто")
            else "failed" to "приложение не найдено"
        } catch (e: Exception) {
            "failed" to (e.message ?: "не удалось")
        }
    }

    /** Выставить громкость (все основные потоки) в процентах. */
    fun setVolume(ctx: Context, percent: Int) {
        val audio = ctx.getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return
        val p = percent.coerceIn(0, 100)
        for (stream in intArrayOf(
            AudioManager.STREAM_MUSIC, AudioManager.STREAM_RING,
            AudioManager.STREAM_NOTIFICATION, AudioManager.STREAM_ALARM
        )) {
            runCatching {
                val max = audio.getStreamMaxVolume(stream)
                audio.setStreamVolume(stream, max * p / 100, 0)
            }
        }
    }

    /** Открыть приложение на телефоне. */
    fun launchApp(ctx: Context, pkg: String): Pair<String, String?> {
        val intent = ctx.packageManager.getLaunchIntentForPackage(pkg)
            ?: return "failed" to "приложение не найдено"
        intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        return try {
            ctx.startActivity(intent)
            "done" to null
        } catch (e: Exception) {
            "failed" to (e.message ?: "не удалось запустить")
        }
    }

    /** Выдать или отозвать разрешение приложению правами владельца устройства. */
    fun grantPermission(ctx: Context, pkg: String, permission: String, grant: Boolean): Pair<String, String?> {
        val state = if (grant) {
            android.app.admin.DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED
        } else {
            android.app.admin.DevicePolicyManager.PERMISSION_GRANT_STATE_DENIED
        }
        return try {
            val ok = Dpm.manager(ctx).setPermissionGrantState(Dpm.admin(ctx), pkg, permission, state)
            if (ok) "done" to (if (grant) "выдано" else "отозвано")
            else "failed" to "система отклонила"
        } catch (e: Exception) {
            "failed" to (e.message ?: "не удалось")
        }
    }

    /** Часовой пояс. */
    fun setTimeZone(ctx: Context, zone: String): Pair<String, String?> = try {
        Dpm.manager(ctx).setTimeZone(Dpm.admin(ctx), zone)
        "done" to zone
    } catch (e: Exception) {
        "failed" to (e.message ?: "не удалось")
    }

    /** Автосинхронизация времени. */
    fun setAutoTime(ctx: Context, enabled: Boolean): Pair<String, String?> = try {
        Dpm.manager(ctx).setAutoTimeEnabled(Dpm.admin(ctx), enabled)
        "done" to (if (enabled) "включена" else "выключена")
    } catch (e: Exception) {
        "failed" to (e.message ?: "не удалось")
    }

    /** Не гасить экран при зарядке — для терминала на подставке. */
    fun setStayAwake(ctx: Context, enabled: Boolean): Pair<String, String?> = try {
        // BatteryManager.BATTERY_PLUGGED_* маской: AC|USB|WIRELESS = 1|2|4 = 7.
        val value = if (enabled) "7" else "0"
        Dpm.manager(ctx).setGlobalSetting(Dpm.admin(ctx), "stay_on_while_plugged_in", value)
        "done" to (if (enabled) "экран не гаснет при зарядке" else "как обычно")
    } catch (e: Exception) {
        "failed" to (e.message ?: "не удалось")
    }

    /** Скрыть/показать строку состояния (для киоска). */
    fun setStatusBar(ctx: Context, disabled: Boolean): Pair<String, String?> = try {
        Dpm.manager(ctx).setStatusBarDisabled(Dpm.admin(ctx), disabled)
        "done" to (if (disabled) "скрыта" else "показана")
    } catch (e: Exception) {
        "failed" to (e.message ?: "не удалось")
    }

    /** Выставить точное время. */
    fun setTime(ctx: Context, epochMs: Long): Pair<String, String?> = try {
        Dpm.manager(ctx).setTime(Dpm.admin(ctx), epochMs)
        "done" to null
    } catch (e: Exception) {
        "failed" to (e.message ?: "не удалось")
    }

    /** Установлено ли приложение. */
    fun isInstalled(ctx: Context, pkg: String): Boolean = try {
        ctx.packageManager.getPackageInfo(pkg, 0)
        true
    } catch (e: PackageManager.NameNotFoundException) {
        false
    }
}
