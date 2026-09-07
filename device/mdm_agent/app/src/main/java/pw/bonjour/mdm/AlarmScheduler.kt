package pw.bonjour.mdm

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build

/** Частый опрос команд поверх пятнадцатиминутного чек-ина.
 *
 *  `WorkManager` не умеет период короче 15 минут — система урезает любой
 *  меньший. Для «заблокируй телефон, его унесли» это неприемлемо долго,
 *  поэтому команды опрашиваются будильником, а периодическая работа остаётся
 *  страховкой на случай, если будильник прибьёт прошивка.
 *
 *  Будильник одноразовый по своей природе: следующий ставится из
 *  [AlarmReceiver] после каждого срабатывания.
 */
object AlarmScheduler {

    private const val REQUEST_CODE = 4001

    /** Запасной интервал до первого ответа сервера. */
    const val DEFAULT_POLL_SECONDS = 120

    fun schedule(ctx: Context) {
        val manager = ctx.getSystemService(Context.ALARM_SERVICE) as? AlarmManager ?: return
        val at = System.currentTimeMillis() + Prefs.pollSeconds(ctx) * 1000L
        val intent = pendingIntent(ctx)

        // ...AndAllowWhileIdle — обязательно: без него в дремоте телефон
        // просыпался бы раз в девять минут, и вся затея теряет смысл.
        runCatching {
            if (canBeExact(ctx, manager)) {
                manager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, intent)
            } else {
                // Точные будильники с Android 13 требуют отдельного разрешения,
                // которое владелец устройства сам себе выдать не может. Неточный
                // будильник у приложения, выведенного из-под энергосбережения,
                // на практике опаздывает на секунды — этого достаточно.
                manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, intent)
            }
        }
    }

    fun cancel(ctx: Context) {
        val manager = ctx.getSystemService(Context.ALARM_SERVICE) as? AlarmManager ?: return
        runCatching { manager.cancel(pendingIntent(ctx)) }
    }

    fun canBeExact(ctx: Context, manager: AlarmManager? = null): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        val am = manager ?: ctx.getSystemService(Context.ALARM_SERVICE) as? AlarmManager ?: return false
        return am.canScheduleExactAlarms()
    }

    private fun pendingIntent(ctx: Context): PendingIntent {
        val intent = Intent(ctx, AlarmReceiver::class.java)
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        return PendingIntent.getBroadcast(ctx, REQUEST_CODE, intent, flags)
    }
}
