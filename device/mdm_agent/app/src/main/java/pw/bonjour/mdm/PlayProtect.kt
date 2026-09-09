package pw.bonjour.mdm

import android.content.Context
import android.provider.Settings

/** Попытка управлять Play Защитой правами владельца устройства.
 *
 *  Play Защита отклоняет тихую установку приложений, подписанных незнакомым ей
 *  ключом, — то есть всех наших. До сих пор её выключали руками на каждом
 *  телефоне или строкой через кабель при взятии под управление.
 *
 *  Здесь проверяется, отдаёт ли Android эти настройки владельцу устройства.
 *  `setGlobalSetting` принимает лишь короткий белый список ключей и на всё
 *  прочее бросает SecurityException, поэтому каждый ключ пробуем отдельно.
 *
 *  Главное: об успехе судим по ПЕРЕЧИТАННОМУ значению, а не по тому, что вызов
 *  не бросил исключение. Настройка может молча не примениться, и рапорт «готово»
 *  тогда соврал бы — а по нему оператор решает, поедет ли установка приложений
 *  на телефон, стоящий в другом городе.
 */
object PlayProtect {

    /** Ключи, которыми система решает, проверять ли устанавливаемое.
     *  Значения даны парой: (выключено, включено). */
    private val KEYS = listOf(
        Triple("package_verifier_user_consent", "-1", "1"),
        Triple("package_verifier_enable", "0", "1"),
        Triple("verifier_verify_adb_installs", "0", "1")
    )

    fun set(ctx: Context, enabled: Boolean): Pair<String, String?> {
        val dpm = Dpm.manager(ctx)
        val admin = Dpm.admin(ctx)

        val refused = mutableListOf<String>()
        for ((key, off, on) in KEYS) {
            val value = if (enabled) on else off
            runCatching { dpm.setGlobalSetting(admin, key, value) }
                .onFailure { refused.add(key.substringAfter("package_").substringAfter("verifier_")) }
        }

        // Перечитываем: система могла принять вызов и не применить настройку.
        val consent = readInt(ctx, "package_verifier_user_consent", 1)
        val nowOn = consent > 0
        val achieved = nowOn == enabled

        return when {
            achieved && refused.isEmpty() ->
                "done" to (if (enabled) "Play Защита включена" else "Play Защита выключена")
            achieved ->
                "done" to ((if (enabled) "включена" else "выключена") + "; часть ключей не отдалась: " + refused.joinToString())
            else ->
                "failed" to ("Android не отдал настройку владельцу устройства" +
                    (if (refused.isEmpty()) "" else " (отказ: " + refused.joinToString() + ")") +
                    ". Выключать придётся руками на телефоне или строкой через кабель.")
        }
    }

    private fun readInt(ctx: Context, key: String, fallback: Int): Int = try {
        Settings.Global.getInt(ctx.contentResolver, key, fallback)
    } catch (e: Exception) {
        fallback
    }
}
