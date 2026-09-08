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
            Dpm.manager(ctx).setApplicationHidden(Dpm.admin(ctx), pkg, !enabled)
            "done" to (if (enabled) "показано" else "скрыто")
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

    /** Установлено ли приложение. */
    fun isInstalled(ctx: Context, pkg: String): Boolean = try {
        ctx.packageManager.getPackageInfo(pkg, 0)
        true
    } catch (e: PackageManager.NameNotFoundException) {
        false
    }
}
