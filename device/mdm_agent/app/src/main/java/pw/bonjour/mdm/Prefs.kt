package pw.bonjour.mdm

import android.content.Context
import android.provider.Settings
import org.json.JSONArray
import org.json.JSONObject

/** Локальное состояние агента. Всё, что нужно пережить перезагрузку телефона. */
object Prefs {
    private const val FILE = "bonjour_mdm"

    private fun sp(ctx: Context) = ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    fun serverUrl(ctx: Context): String =
        sp(ctx).getString("server_url", null)?.takeIf { it.isNotBlank() }
            ?: BuildConfig.DEFAULT_SERVER_URL

    fun setServerUrl(ctx: Context, value: String) =
        sp(ctx).edit().putString("server_url", value.trimEnd('/')).apply()

    fun enrollKey(ctx: Context): String = sp(ctx).getString("enroll_key", "") ?: ""

    fun setEnrollKey(ctx: Context, value: String) =
        sp(ctx).edit().putString("enroll_key", value.trim()).apply()

    fun token(ctx: Context): String = sp(ctx).getString("token", "") ?: ""

    fun setToken(ctx: Context, value: String) = sp(ctx).edit().putString("token", value).apply()

    /** ANDROID_ID — стабилен для пары «устройство + ключ подписи приложения». */
    @Suppress("HardwareIds")
    fun deviceId(ctx: Context): String =
        Settings.Secure.getString(ctx.contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown"

    fun policy(ctx: Context): JSONObject =
        runCatching { JSONObject(sp(ctx).getString("policy", "{}") ?: "{}") }.getOrElse { JSONObject() }

    fun setPolicy(ctx: Context, policy: JSONObject, version: Int) =
        sp(ctx).edit().putString("policy", policy.toString()).putInt("policy_version", version).apply()

    fun policyVersion(ctx: Context): Int = sp(ctx).getInt("policy_version", 0)

    fun appliedVersion(ctx: Context): Int = sp(ctx).getInt("applied_version", 0)

    fun setAppliedVersion(ctx: Context, value: Int) =
        sp(ctx).edit().putInt("applied_version", value).apply()

    /** Интервал опроса команд, заданный сервером: менять частоту можно без
     *  пересборки APK и переустановки на каждом телефоне. */
    fun pollSeconds(ctx: Context): Int =
        sp(ctx).getInt("poll_seconds", AlarmScheduler.DEFAULT_POLL_SECONDS)

    fun setPollSeconds(ctx: Context, value: Int) =
        sp(ctx).edit().putInt("poll_seconds", value.coerceIn(30, 3600)).apply()

    fun lastCheckin(ctx: Context): String = sp(ctx).getString("last_checkin", "") ?: ""

    fun setLastCheckin(ctx: Context, value: String) =
        sp(ctx).edit().putString("last_checkin", value).apply()

    fun lastError(ctx: Context): String = sp(ctx).getString("last_error", "") ?: ""

    fun setLastError(ctx: Context, value: String?) =
        sp(ctx).edit().putString("last_error", value ?: "").apply()

    // --- подтверждения выполненных команд -------------------------------
    // Копятся локально: команда могла выполниться в момент, когда сети нет, и
    // терять этот факт нельзя — иначе на сервере она навсегда останется в
    // статусе "отправлена".

    @Synchronized
    fun addAck(ctx: Context, commandId: String, status: String, result: String?) {
        val acks = pendingAcks(ctx)
        acks.put(
            JSONObject()
                .put("command_id", commandId)
                .put("status", status)
                .put("result", result ?: JSONObject.NULL)
        )
        sp(ctx).edit().putString("acks", acks.toString()).apply()
    }

    @Synchronized
    fun pendingAcks(ctx: Context): JSONArray =
        runCatching { JSONArray(sp(ctx).getString("acks", "[]") ?: "[]") }.getOrElse { JSONArray() }

    @Synchronized
    fun clearAcks(ctx: Context, delivered: JSONArray) {
        val deliveredIds = (0 until delivered.length())
            .mapNotNull { delivered.optJSONObject(it)?.optString("command_id") }
            .toSet()
        val remaining = JSONArray()
        val current = pendingAcks(ctx)
        for (i in 0 until current.length()) {
            val ack = current.optJSONObject(i) ?: continue
            if (ack.optString("command_id") !in deliveredIds) remaining.put(ack)
        }
        sp(ctx).edit().putString("acks", remaining.toString()).apply()
    }

    /** Координаты, снятые по команде locate, — уезжают ближайшим чек-ином. */
    @Synchronized
    fun setPendingLocation(ctx: Context, lat: Double, lon: Double, at: String) =
        sp(ctx).edit()
            .putString("loc", "$lat;$lon;$at")
            .apply()

    @Synchronized
    fun takePendingLocation(ctx: Context): Triple<Double, Double, String>? {
        val raw = sp(ctx).getString("loc", "") ?: ""
        if (raw.isBlank()) return null
        sp(ctx).edit().remove("loc").apply()
        val parts = raw.split(";")
        if (parts.size < 3) return null
        val lat = parts[0].toDoubleOrNull() ?: return null
        val lon = parts[1].toDoubleOrNull() ?: return null
        return Triple(lat, lon, parts[2])
    }
}
