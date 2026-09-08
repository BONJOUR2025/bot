package pw.bonjour.mdm

import android.content.Context
import android.os.Build
import org.json.JSONObject

/** Регистрация телефона на сервере.
 *
 *  Вынесено отдельно, потому что путей сюда два и они непохожи: руками с экрана
 *  агента и автоматически после провижининга по QR, где никакого экрана нет и
 *  нажать некому.
 */
object Enroller {

    /** @return человекочитаемый результат для показа на экране. */
    fun enroll(ctx: Context): String {
        val url = Prefs.serverUrl(ctx).trimEnd('/')
        val key = Prefs.enrollKey(ctx)
        if (url.isBlank() || key.isBlank()) return "Не заданы адрес сервера или ключ регистрации"

        val payload = JSONObject()
            .put("device_id", Prefs.deviceId(ctx))
            .put("model", Build.MODEL)
            .put("manufacturer", Build.MANUFACTURER)
            .put("android_version", Build.VERSION.RELEASE)
            .put("agent_version", BuildConfig.VERSION_NAME)
            .put("device_owner", Dpm.isOwner(ctx))

        return try {
            val response = Api.post(url + "/api/mdm/device/enroll", mapOf("X-Enroll-Key" to key), payload)
            if (!response.ok) {
                "Сервер ответил " + response.code + ": " + response.body.take(200)
            } else {
                val body = response.json()
                Prefs.setToken(ctx, body.optString("token"))
                val version = body.optInt("policy_version", 0)
                val policy = body.optJSONObject("policy") ?: JSONObject()
                Prefs.setPolicy(ctx, policy, version)
                val problem = PolicyApplier.apply(ctx, policy)
                if (problem == null) Prefs.setAppliedVersion(ctx, version)
                Prefs.setLastError(ctx, problem)
                CheckinWorker.schedule(ctx)
                AlarmScheduler.schedule(ctx)
                AgentService.start(ctx)
                "Телефон зарегистрирован"
            }
        } catch (e: Exception) {
            "Не удалось связаться с сервером: " + e.message
        }
    }

    /** Регистрация в фоне — для путей, где ждать сеть нельзя (провижининг). */
    fun enrollAsync(ctx: Context, onDone: (String) -> Unit = {}) {
        Thread {
            val result = enroll(ctx)
            onDone(result)
        }.start()
    }
}
