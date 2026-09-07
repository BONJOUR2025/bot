package pw.bonjour.mdm

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.os.Build
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.zip.ZipFile

/** Тихая установка и удаление приложений правами владельца устройства.
 *
 *  Умеет и одиночный APK, и контейнер вроде XAPK — набор из базового APK и
 *  довесков под процессор, экран и язык. У приложений, которые Google раздаёт
 *  набором, единого файла не существует, а ставится набор одной транзакцией:
 *  все части пишутся в одну сессию установки, и она подтверждается целиком.
 *
 *  Результат приходит асинхронно в InstallResultReceiver, поэтому подтверждение
 *  команды пишется там, а не здесь.
 */
object ApkInstaller {

    private const val DOWNLOAD_TIMEOUT_MS = 60000

    /** @return текст ошибки, если до установки дело не дошло; null — сессия отдана системе. */
    fun install(ctx: Context, commandId: String, url: String): String? {
        if (!Dpm.isOwner(ctx)) return "not_device_owner"

        // Скачиваем в файл, а не пишем сразу в сессию: чтобы понять, набор
        // перед нами или один APK, нужно прочитать оглавление архива, а оно
        // лежит в конце.
        val downloaded = File(ctx.cacheDir, "install-" + commandId + ".bin")
        try {
            download(url, downloaded)?.let { return it }
            return installFile(ctx, commandId, downloaded)
        } catch (e: Exception) {
            return "install_failed: " + e.message
        } finally {
            downloaded.delete()
        }
    }

    private fun download(url: String, target: File): String? {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = DOWNLOAD_TIMEOUT_MS
        connection.readTimeout = DOWNLOAD_TIMEOUT_MS
        try {
            val code = connection.responseCode
            if (code < 200 || code > 299) return "download_failed_http_" + code
            connection.inputStream.use { input ->
                target.outputStream().use { output -> input.copyTo(output) }
            }
            return null
        } finally {
            connection.disconnect()
        }
    }

    private fun installFile(ctx: Context, commandId: String, file: File): String? {
        val parts = containerParts(file)
        val hasObb = parts.second
        val installer = ctx.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(
            PackageInstaller.SessionParams.MODE_FULL_INSTALL
        )
        val sessionId = installer.createSession(params)

        installer.openSession(sessionId).use { session ->
            if (parts.first.isEmpty()) {
                session.openWrite("base.apk", 0, file.length()).use { output ->
                    file.inputStream().use { input -> input.copyTo(output) }
                    session.fsync(output)
                }
            } else {
                ZipFile(file).use { zip ->
                    for (name in parts.first) {
                        val entry = zip.getEntry(name) ?: continue
                        // Имя части в сессии должно быть плоским: вложенные пути
                        // установщик не принимает.
                        val partName = name.substringAfterLast('/')
                        session.openWrite(partName, 0, entry.size).use { output ->
                            zip.getInputStream(entry).use { input -> input.copyTo(output) }
                            session.fsync(output)
                        }
                    }
                }
            }
            val kind = when {
                parts.first.isEmpty() -> "install"
                hasObb -> "install набором из " + parts.first.size + " частей, OBB пропущены"
                else -> "install набором из " + parts.first.size + " частей"
            }
            session.commit(resultIntent(ctx, commandId, kind).intentSender)
        }
        return null
    }

    /** @return список вложенных APK (пусто, если это обычный APK) и признак,
     *  что внутри лежат данные для игр, которые мы не раскладываем. */
    private fun containerParts(file: File): Pair<List<String>, Boolean> = try {
        ZipFile(file).use { zip ->
            val names = zip.entries().toList().map { it.name }
            // Обычный APK — тоже архив, но вложенных APK внутри не содержит.
            Pair(
                names.filter { it.endsWith(".apk", ignoreCase = true) },
                names.any { it.endsWith(".obb", ignoreCase = true) }
            )
        }
    } catch (e: Exception) {
        Pair(emptyList(), false)
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
