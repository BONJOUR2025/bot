package pw.bonjour.mdm

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.os.Build
import java.net.HttpURLConnection
import java.net.URL

/** Тихая установка и удаление приложений правами владельца устройства.
 *
 *  Результат приходит асинхронно в InstallResultReceiver, поэтому подтверждение
 *  команды пишется там, а не здесь: в момент возврата из install() система ещё
 *  только начала ставить пакет.
 */
object ApkInstaller {

    private const val DOWNLOAD_TIMEOUT_MS = 60000

    /** @return текст ошибки, если до установки дело не дошло; null — сессия отдана системе. */
    fun install(ctx: Context, commandId: String, url: String): String? {
        if (!Dpm.isOwner(ctx)) return "not_device_owner"

        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = DOWNLOAD_TIMEOUT_MS
        connection.readTimeout = DOWNLOAD_TIMEOUT_MS
        try {
            val code = connection.responseCode
            if (code < 200 || code > 299) {
                return "download_failed_http_" + code
            }
            val installer = ctx.packageManager.packageInstaller
            val params = PackageInstaller.SessionParams(
                PackageInstaller.SessionParams.MODE_FULL_INSTALL
            )
            val sessionId = installer.createSession(params)
            installer.openSession(sessionId).use { session ->
                session.openWrite("apk", 0, -1).use { output ->
                    connection.inputStream.use { input -> input.copyTo(output) }
                    session.fsync(output)
                }
                session.commit(resultIntent(ctx, commandId, "install").intentSender)
            }
            return null
        } catch (e: Exception) {
            return "install_failed: " + e.message
        } finally {
            connection.disconnect()
        }
    }

    fun uninstall(ctx: Context, commandId: String, packageName: String): String? {
        if (!Dpm.isOwner(ctx)) return "not_device_owner"
        return try {
            ctx.packageManager.packageInstaller.uninstall(
                packageName,
                resultIntent(ctx, commandId, "uninstall").intentSender
            )
            null
        } catch (e: Exception) {
            "uninstall_failed: " + e.message
        }
    }

    private fun resultIntent(ctx: Context, commandId: String, kind: String): PendingIntent {
        val intent = Intent(ctx, InstallResultReceiver::class.java)
            .putExtra(InstallResultReceiver.EXTRA_COMMAND_ID, commandId)
            .putExtra(InstallResultReceiver.EXTRA_KIND, kind)
        // MUTABLE обязателен: систему нужно пустить дописать в intent свой статус.
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        return PendingIntent.getBroadcast(ctx, commandId.hashCode(), intent, flags)
    }
}
