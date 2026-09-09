package pw.bonjour.mdm

import android.app.admin.DevicePolicyManager
import android.content.Context
import android.os.Build
import java.security.SecureRandom

/** Удалённая смена и снятие блокировки экрана.
 *
 *  Прямой `resetPassword()` владельцу устройства запрещён с Android 8: любой
 *  MDM мог бы молча поставить свой PIN на чужой телефон. Вместо него оставили
 *  `resetPasswordWithToken` — сброс по токену, который надо выдать телефону
 *  ЗАРАНЕЕ, пока к нему есть доступ.
 *
 *  Важная тонкость, из-за которой это нельзя включить задним числом: если на
 *  телефоне УЖЕ стоит PIN, выданный токен не работает, пока владелец один раз
 *  не разблокирует аппарат руками — система привязывает токен к ключу,
 *  выведенному из PIN-а. То есть удалённое снятие блокировки возможно только
 *  на телефонах, где агент успел выдать токен и телефон после этого хотя бы раз
 *  разблокировали. Поэтому токен выдаём при каждом чек-ине, не дожидаясь
 *  случая: к моменту, когда сотрудник забудет PIN, всё уже должно быть готово.
 *
 *  Токен лежит в приватном хранилище агента. Это ключ от экрана блокировки, и
 *  относиться к нему надо соответственно — но добраться до приватных данных
 *  приложения можно только уже имея доступ к аппарату, так что новой дыры это
 *  не открывает.
 */
object ScreenLock {

    /** Выдать телефону токен сброса, если ещё не выдан. Идемпотентно. */
    fun ensureToken(ctx: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        if (!Dpm.isOwner(ctx)) return
        runCatching {
            val dpm = Dpm.manager(ctx)
            val admin = Dpm.admin(ctx)
            val existing = Prefs.resetToken(ctx)
            if (existing != null && dpm.isResetPasswordTokenActive(admin)) return

            val token = existing ?: ByteArray(32).also { SecureRandom().nextBytes(it) }
            if (dpm.setResetPasswordToken(admin, token)) {
                Prefs.setResetToken(ctx, token)
            }
        }
    }

    /** Работает ли удалённый сброс прямо сейчас. */
    fun tokenActive(ctx: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return false
        return runCatching {
            Prefs.resetToken(ctx) != null && Dpm.manager(ctx).isResetPasswordTokenActive(Dpm.admin(ctx))
        }.getOrDefault(false)
    }

    /** Поставить новый PIN или снять блокировку (пустая строка).
     *
     *  @return пара (статус, пояснение) для отчёта на сервер.
     */
    fun setPassword(ctx: Context, password: String): Pair<String, String?> {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return "failed" to "нужен Android 8 и новее"
        }
        val token = Prefs.resetToken(ctx)
            ?: return "failed" to "токен сброса не выдан — телефон недоступен для удалённой разблокировки"

        val dpm = Dpm.manager(ctx)
        val admin = Dpm.admin(ctx)
        if (!runCatching { dpm.isResetPasswordTokenActive(admin) }.getOrDefault(false)) {
            // Ровно тот случай из описания класса: токен выдан, но телефон с
            // момента выдачи ни разу не разблокировали руками.
            return "failed" to "токен не активен — телефон нужно один раз разблокировать вручную"
        }

        return runCatching {
            val ok = dpm.resetPasswordWithToken(admin, password.ifBlank { null }, token, 0)
            if (ok) {
                "done" to (if (password.isBlank()) "блокировка снята" else "новый код установлен")
            } else {
                "failed" to "система отклонила код (не подходит под требования к сложности)"
            }
        }.getOrElse { "failed" to (it.javaClass.simpleName + ": " + it.message) }
    }
}
