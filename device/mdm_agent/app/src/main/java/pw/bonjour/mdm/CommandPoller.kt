package pw.bonjour.mdm

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Длинный опрос команд: телефон висит на открытом запросе.
 *
 *  Зачем отдельно от чек-ина. Чек-ин — тяжёлый отчёт (телеметрия, список
 *  приложений, политика), его незачем гонять часто. А команду оператор ждёт
 *  здесь и сейчас: пока команды приезжали ответом на чек-ин, отклик равнялся
 *  интервалу опроса — две минуты, и уменьшать его пришлось бы за счёт батареи,
 *  потому что каждый заход будит радио.
 *
 *  Здесь наоборот: запрос уходит один раз и молчит, пока сервер его держит,
 *  а команда уходит в него в тот же момент, когда её поставили. Радио будится
 *  на переподключение раз в hold_seconds, но отклик при этом — секунды, а не
 *  интервал. Разрыв соединения не теряет команду: она остаётся в очереди
 *  сервера до следующего запроса.
 *
 *  Результаты команд едут в следующем же запросе опроса, а не отдельной ручкой:
 *  агент исполнил команду и тут же снова встаёт на ожидание, так что отдельный
 *  отчёт был бы вторым запросом на ровном месте.
 */
object CommandPoller {

    const val DEFAULT_HOLD_SECONDS = 25

    /** Запас поверх времени удержания: сервер отвечает ровно на hold_seconds,
     *  и таймаут чтения должен пережить и ответ, и медленную сеть. */
    private const val READ_TIMEOUT_MARGIN_MS = 20_000

    /** Пауза после неудачи. Растёт до минуты, чтобы телефон без сети не
     *  молотил впустую, но не дольше: чек-ин всё равно идёт своим чередом и
     *  подхватит команды, если опрос почему-то не работает вовсе. */
    private const val BACKOFF_START_SECONDS = 5
    private const val BACKOFF_MAX_SECONDS = 60

    /** Один заход: отчитаться, подождать команду, исполнить.
     *
     *  @return сколько секунд ждать перед следующим заходом (0 — сразу).
     */
    fun once(ctx: Context, failures: Int): Int {
        val token = Prefs.token(ctx)
        // Без токена ждать нечего: регистрацию доделает чек-ин, он умеет.
        if (token.isBlank()) return BACKOFF_MAX_SECONDS

        val acks = Prefs.pendingAcks(ctx)
        val payload = JSONObject().put("acks", acks)

        val hold = Prefs.holdSeconds(ctx)
        val response = try {
            Api.post(
                Prefs.serverUrl(ctx) + "/api/mdm/device/poll",
                mapOf("X-Device-Token" to token),
                payload,
                hold * 1000 + READ_TIMEOUT_MARGIN_MS
            )
        } catch (e: Exception) {
            // Обрыв на ожидании — обычное дело: туннели и операторы рвут
            // долгие простаивающие соединения. Это не ошибка агента, поэтому
            // last_error не трогаем, чтобы не мигать красным в панели.
            return backoff(failures)
        }

        if (!response.ok) {
            // 401 — телефон удалили из панели. Ждать перестаём до перерегистрации.
            if (response.code == 401) return BACKOFF_MAX_SECONDS
            return backoff(failures)
        }

        // Отчёт принят вместе с запросом — можно забыть.
        Prefs.clearAcks(ctx, acks)

        val body = response.json()
        body.optInt("hold_seconds", 0).takeIf { it > 0 }?.let { Prefs.setHoldSeconds(ctx, it) }
        body.optInt("command_poll_seconds", 0).takeIf { it > 0 }?.let { Prefs.setPollSeconds(ctx, it) }

        runCommands(ctx, body.optJSONArray("commands") ?: JSONArray())

        // Политику сменили из панели — не ждём своего чек-ина, идём за ней
        // сразу: иначе запрет вступал бы в силу через интервал чек-ина, тогда
        // как команда доезжает за секунды, и разница выглядела бы поломкой.
        val version = body.optInt("policy_version", 0)
        if (version > 0 && version != Prefs.appliedVersion(ctx)) {
            runCatching { Checkin.run(ctx) }
        }

        return 0
    }

    private fun runCommands(ctx: Context, commands: JSONArray) {
        for (i in 0 until commands.length()) {
            val command = commands.optJSONObject(i) ?: continue
            val outcome = runCatching { CommandRunner.run(ctx, command) }.getOrNull()
            // null — установка приложения или снимок с камеры: подтверждение
            // придёт асинхронно, когда система закончит работу.
            if (outcome != null) {
                Prefs.addAck(ctx, command.optString("id"), outcome.first, outcome.second)
            }
        }
    }

    private fun backoff(failures: Int): Int {
        var seconds = BACKOFF_START_SECONDS
        repeat(failures) { seconds = minOf(seconds * 2, BACKOFF_MAX_SECONDS) }
        return minOf(seconds, BACKOFF_MAX_SECONDS)
    }
}
