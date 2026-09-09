package pw.bonjour.mdm

import android.content.Context
import android.os.BatteryManager
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/** Сам чек-ин: отчитаться о состоянии, забрать политику и команды, исполнить.
 *
 *  Вынесен из воркера в общий код, потому что вызывающих двое и они разные:
 *  постоянный сервис (основной путь — он жив всегда и не зависит от планировщика,
 *  который прошивки душат) и WorkManager (страховка, если сервис всё же убили).
 *
 *  Политика применяется здесь же и живёт на телефоне дальше сама по себе —
 *  недоступность сервера не снимает запреты, она лишь откладывает их изменение.
 */
object Checkin {

    /** @return true, если цикл отработал; false — есть смысл повторить позже.
     *
     *  Синхронизирован: вызывающих теперь трое — свой поток сервиса, поток
     *  длинного опроса (когда увидел чужую версию политики) и страховочный
     *  воркер. Два чек-ина разом забрали бы одну очередь команд дважды и
     *  подрались бы за отчёт о применённой политике.
     */
    @Synchronized
    fun run(ctx: Context): Boolean {
        var token = Prefs.token(ctx)
        if (token.isBlank()) {
            // При настройке по QR ключ регистрации приезжает внутри самого QR,
            // но сети в тот момент может ещё не быть. Тогда регистрацию
            // доделывает первый же чек-ин — иначе телефон, настроенный в
            // салоне без интернета, навсегда остался бы вне панели.
            if (Prefs.enrollKey(ctx).isBlank()) return true
            Enroller.enroll(ctx)
            token = Prefs.token(ctx)
            if (token.isBlank()) return false
        }

        // Что ушло в этом запросе. Запоминаем доставленным только после ответа
        // сервера: иначе при обрыве связи результат команды и список приложений
        // считались бы отправленными и не уехали бы никогда.
        val sent = Sent()
        val response = try {
            Api.post(
                Prefs.serverUrl(ctx) + "/api/mdm/device/checkin",
                mapOf("X-Device-Token" to token),
                payload(ctx, sent)
            )
        } catch (e: Exception) {
            Prefs.setLastError(ctx, "checkin: " + e.message)
            return false
        }

        if (!response.ok) {
            Prefs.setLastError(ctx, "checkin_http_" + response.code)
            // 401 — токен отозван (телефон удалили из панели). Повторять нечего,
            // пока его не зарегистрируют заново.
            return response.code == 401
        }

        Prefs.setLastCheckin(ctx, now())
        Prefs.clearAcks(ctx, sent.acks)
        sent.appsHash?.let { Prefs.setReportedAppsHash(ctx, it) }

        val body = response.json()
        val version = body.optInt("policy_version", 0)
        val policy = body.optJSONObject("policy") ?: JSONObject()
        Prefs.setPolicy(ctx, policy, version)

        val poll = body.optInt("command_poll_seconds", 0)
        if (poll > 0) Prefs.setPollSeconds(ctx, poll)
        // Расписание восстанавливается на каждом удачном чек-ине, что бы его ни
        // погасило — обновление пакета, очистка данных, причуды прошивки.
        AlarmScheduler.schedule(ctx)

        var problem: String? = null
        var appliedNow: Int? = null
        if (version != Prefs.appliedVersion(ctx)) {
            problem = PolicyApplier.apply(ctx, policy)
            if (problem == null) {
                Prefs.setAppliedVersion(ctx, version)
                appliedNow = version
            }
        }
        Prefs.setLastError(ctx, problem)

        runCommands(ctx, body.optJSONArray("commands") ?: JSONArray())
        report(ctx, appliedNow)
        return true
    }

    private class Sent {
        var acks: JSONArray = JSONArray()
        var appsHash: String? = null
    }

    private fun runCommands(ctx: Context, commands: JSONArray) {
        for (i in 0 until commands.length()) {
            val command = commands.optJSONObject(i) ?: continue
            val outcome = CommandRunner.run(ctx, command)
            // null — установка приложения или снимок с камеры: подтверждение
            // придёт асинхронно, когда система закончит работу.
            if (outcome != null) {
                Prefs.addAck(ctx, command.optString("id"), outcome.first, outcome.second)
            }
        }
    }

    /** Догоняющий отчёт: что исполнено и какая версия политики применена.
     *
     *  Отдельная ручка, а не повторный чек-ин: чек-ин забрал бы новые команды и
     *  пометил их отправленными, а исполнить их этот проход уже не успевает —
     *  они молча повисли бы до следующего цикла.
     *
     *  Применённую версию можно сообщить только здесь: политику агент получает
     *  ответом на чек-ин и применяет, когда тот запрос уже ушёл, поэтому в самом
     *  чек-ине он всегда назвал бы предыдущую.
     */
    private fun report(ctx: Context, appliedVersion: Int?) {
        val acks = Prefs.pendingAcks(ctx)
        if (acks.length() == 0 && appliedVersion == null) return
        val payload = JSONObject().put("acks", acks)
        if (appliedVersion != null) payload.put("applied_policy_version", appliedVersion)
        val response = try {
            Api.post(
                Prefs.serverUrl(ctx) + "/api/mdm/device/ack",
                mapOf("X-Device-Token" to Prefs.token(ctx)),
                payload
            )
        } catch (e: Exception) {
            return  // не доставили — уедут следующим чек-ином
        }
        if (response.ok) Prefs.clearAcks(ctx, acks)
    }

    private fun payload(ctx: Context, sent: Sent): JSONObject {
        val acks = Prefs.pendingAcks(ctx)
        sent.acks = acks

        val json = JSONObject()
            .put("model", Build.MODEL)
            .put("manufacturer", Build.MANUFACTURER)
            .put("android_version", Build.VERSION.RELEASE)
            .put("agent_version", BuildConfig.VERSION_NAME)
            .put("device_owner", Dpm.isOwner(ctx))
            .put("applied_policy_version", Prefs.appliedVersion(ctx))
            .put("acks", acks)

        val apps = AppInventory.collect(ctx)
        val hash = AppInventory.fingerprint(apps)
        json.put("apps_hash", hash)
        if (hash != Prefs.reportedAppsHash(ctx)) {
            json.put("apps", apps)
            sent.appsHash = hash
        }

        json.put("play_protect", playProtectEnabled(ctx))

        // Телеметрия: место, память, сеть, аптайм, защита экрана.
        val tele = Telemetry.collect(ctx)
        for (key in tele.keys()) json.put(key, tele.get(key))

        battery(ctx)?.let { json.put("battery", it) }
        Prefs.lastError(ctx).takeIf { it.isNotBlank() }?.let { json.put("last_error", it) }
        Prefs.takePendingLocation(ctx)?.let { (lat, lon, at) ->
            json.put("latitude", lat).put("longitude", lon).put("location_at", at)
        }
        return json
    }

    /** Включена ли Play Защита.
     *
     *  Она отклоняет тихую установку приложений, подписанных неизвестным ей
     *  ключом, — то есть любых наших. Отключить её программно нельзя: владелец
     *  устройства не вправе менять эту системную настройку. Зато прочитать
     *  можно, и тогда отказ установки перестаёт быть загадкой: панель прямо
     *  скажет, что и где выключить на телефоне.
     */
    private fun playProtectEnabled(ctx: Context): Boolean = try {
        android.provider.Settings.Global.getInt(
            ctx.contentResolver, "package_verifier_user_consent", 1
        ) > 0
    } catch (e: Exception) {
        true
    }

    private fun battery(ctx: Context): Int? {
        val manager = ctx.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager ?: return null
        val level = manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        return if (level in 0..100) level else null
    }

    private fun now(): String = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).apply {
        timeZone = TimeZone.getDefault()
    }.format(Date())
}
