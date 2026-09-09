package pw.bonjour.mdm

import org.json.JSONObject
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL

/** Тонкий HTTP-клиент. Намеренно на голом HttpURLConnection: агенту нельзя
 *  зависеть от библиотек больше необходимого — он должен ставиться и работать
 *  на телефонах без сервисов Google и с любым состоянием системы. */
object Api {

    data class Response(val code: Int, val body: String) {
        val ok: Boolean get() = code in 200..299
        fun json(): JSONObject = runCatching { JSONObject(body) }.getOrElse { JSONObject() }
    }

    private const val TIMEOUT_MS = 20_000

    /** @param readTimeoutMs ожидание ответа. Длинный опрос молчит, пока сервер
     *  держит запрос, поэтому ему нужен запас поверх времени удержания —
     *  обычные 20 секунд оборвали бы его на середине ожидания. */
    fun post(
        url: String,
        headers: Map<String, String>,
        payload: JSONObject,
        readTimeoutMs: Int = TIMEOUT_MS,
    ): Response {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = TIMEOUT_MS
            readTimeout = readTimeoutMs
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            headers.forEach { (key, value) -> setRequestProperty(key, value) }
        }
        return try {
            connection.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val body = stream?.bufferedReader()?.use(BufferedReader::readText) ?: ""
            Response(code, body)
        } finally {
            connection.disconnect()
        }
    }
}
