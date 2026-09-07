package pw.bonjour.mdm

import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest

/** Список приложений на телефоне.
 *
 *  Отправляется не на каждом чек-ине, а только когда изменился: полный список —
 *  это несколько килобайт, а чек-ины идут раз в две минуты. Поэтому каждый раз
 *  уезжает короткий отпечаток, а сам список — лишь когда отпечаток разошёлся с
 *  тем, что сервер подтвердил в прошлый раз.
 */
object AppInventory {

    fun collect(ctx: Context): JSONArray {
        val pm = ctx.packageManager
        val result = JSONArray()

        val installed = try {
            pm.getInstalledApplications(0)
        } catch (e: Exception) {
            return result
        }

        for (info in installed) {
            val system = (info.flags and ApplicationInfo.FLAG_SYSTEM) != 0
            val launchable = pm.getLaunchIntentForPackage(info.packageName) != null
            // Системные приложения без значка в меню — это сотни служебных
            // пакетов вендора, которые оператору не о чем спросить. Показываем
            // то, что сотрудник может запустить, плюс всё пользовательское.
            if (system && !launchable) continue

            val pkg = try {
                pm.getPackageInfo(info.packageName, 0)
            } catch (e: Exception) {
                null
            }
            val versionCode = when {
                pkg == null -> 0L
                Build.VERSION.SDK_INT >= Build.VERSION_CODES.P -> pkg.longVersionCode
                else -> @Suppress("DEPRECATION") pkg.versionCode.toLong()
            }

            result.put(
                JSONObject()
                    .put("package", info.packageName)
                    .put("label", pm.getApplicationLabel(info).toString())
                    .put("version_name", pkg?.versionName ?: "")
                    .put("version_code", versionCode)
                    .put("system", system)
                    .put("enabled", info.enabled)
            )
        }
        return result
    }

    /** Короткий отпечаток состава: пакет и версия каждого приложения. */
    fun fingerprint(apps: JSONArray): String {
        val parts = ArrayList<String>(apps.length())
        for (i in 0 until apps.length()) {
            val app = apps.optJSONObject(i) ?: continue
            parts.add(app.optString("package") + ":" + app.optLong("version_code"))
        }
        parts.sort()
        val digest = MessageDigest.getInstance("SHA-256").digest(
            parts.joinToString(",").toByteArray(Charsets.UTF_8)
        )
        return digest.joinToString("") { "%02x".format(it) }
    }
}
