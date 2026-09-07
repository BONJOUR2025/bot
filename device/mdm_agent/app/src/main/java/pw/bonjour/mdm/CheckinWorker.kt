package pw.bonjour.mdm

import android.content.Context
import android.os.BatteryManager
import android.os.Build
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.TimeUnit

/** Регулярный чек-ин: отчитаться о состоянии, забрать политику и команды.
 *
 *  Политика применяется здесь же и живёт на телефоне дальше сама по себе —
 *  недоступность сервера не снимает запреты, она лишь откладывает их изменение.
 */
class CheckinWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {

    /** Подтверждения, ушедшие в текущем запросе. Чистим их из локального
     *  хранилища только после подтверждённого HTTP 2xx, иначе результат
     *  выполненной команды потеряется при обрыве связи. */
    private var sentAcks = JSONArray()

    override fun doWork(): Result {
        val ctx = applicationContext
        var token = Prefs.token(ctx)
        if (token.isBlank()) {
            // При настройке по QR ключ регистрации приезжает внутри самого QR,
            // но сети в тот момент может ещё не быть. Тогда регистрацию
            // доделывает первый же чек-ин — иначе телефон, настроенный в
            // салоне без интернета, навсегда остался бы вне панели.
            if (Prefs.enrollKey(ctx).isBlank()) return Result.success()
            Enroller.enroll(ctx)
            token = Prefs.token(ctx)
            if (token.isBlank()) return Result.retry()
        }

        val base = Prefs.serverUrl(ctx)
        val response = try {
            Api.post(base + "/api/mdm/device/checkin", mapOf("X-Device-Token" to token), payload(ctx))
        } catch (e: Exception) {
            Prefs.setLastError(ctx, "checkin: " + e.message)
            return Result.retry()
        }

        if (!response.ok) {
            Prefs.setLastError(ctx, "checkin_http_" + response.code)
            // 401 — токен отозван (телефон удалили из панели). Ретраить нечего,
            // пока его не зарегистрируют заново.
            return if (response.code == 401) Result.success() else Result.retry()
        }

        Prefs.setLastCheckin(ctx, now())
        Prefs.clearAcks(ctx, sentAcks)
        sentAcks = JSONArray()

        val body = response.json()
        val version = body.optInt("policy_version", 0)
        val policy = body.optJSONObject("policy") ?: JSONObject()
        Prefs.setPolicy(ctx, policy, version)

        // Интервал опроса задаёт сервер. Перезаводим будильник с новым значением
        // сразу: PendingIntent один и тот же, так что прежний просто заменяется.
        val poll = body.optInt("command_poll_seconds", 0)
        if (poll > 0) Prefs.setPollSeconds(ctx, poll)
        // Заводим будильник на каждом удачном чек-ине, а не только при смене
        // интервала: так расписание восстанавливается само, что бы его ни
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
        return Result.success()
    }

    private fun runCommands(ctx: Context, commands: JSONArray) {
        for (i in 0 until commands.length()) {
            val command = commands.optJSONObject(i) ?: continue
            val outcome = CommandRunner.run(ctx, command)
            // null — установка/удаление приложения: подтверждение придёт из
            // InstallResultReceiver, когда система закончит работу.
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

    private fun payload(ctx: Context): JSONObject {
        val acks = Prefs.pendingAcks(ctx)
        sentAcks = acks

        val json = JSONObject()
            .put("model", Build.MODEL)
            .put("manufacturer", Build.MANUFACTURER)
            .put("android_version", Build.VERSION.RELEASE)
            .put("agent_version", BuildConfig.VERSION_NAME)
            .put("device_owner", Dpm.isOwner(ctx))
            .put("applied_policy_version", Prefs.appliedVersion(ctx))
            .put("acks", acks)

        battery(ctx)?.let { json.put("battery", it) }
        Prefs.lastError(ctx).takeIf { it.isNotBlank() }?.let { json.put("last_error", it) }
        Prefs.takePendingLocation(ctx)?.let { (lat, lon, at) ->
            json.put("latitude", lat).put("longitude", lon).put("location_at", at)
        }
        return json
    }

    private fun battery(ctx: Context): Int? {
        val manager = ctx.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager ?: return null
        val level = manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        return if (level in 0..100) level else null
    }

    private fun now(): String = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).apply {
        timeZone = TimeZone.getDefault()
    }.format(Date())

    companion object {
        private const val PERIODIC = "mdm-checkin-periodic"
        private const val ONESHOT = "mdm-checkin-now"

        private fun constraints() = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        fun schedule(ctx: Context) {
            // 15 минут — минимальный период, который WorkManager вообще
            // соблюдает; просить чаще бесполезно, система всё равно урежет.
            val request = PeriodicWorkRequestBuilder<CheckinWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints())
                .setBackoffCriteria(BackoffPolicy.LINEAR, 1, TimeUnit.MINUTES)
                .build()
            WorkManager.getInstance(ctx)
                .enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.UPDATE, request)
        }

        fun runNow(ctx: Context) {
            val request = OneTimeWorkRequestBuilder<CheckinWorker>()
                .setConstraints(constraints())
                .setBackoffCriteria(BackoffPolicy.LINEAR, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(ctx)
                .enqueueUniqueWork(ONESHOT, ExistingWorkPolicy.REPLACE, request)
        }
    }
}
