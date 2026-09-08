package pw.bonjour.mdm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Срабатывание будильника: сходить за командами и завести следующий.
 *
 *  Следующий будильник ставится здесь, а не после успешного чек-ина: связи
 *  может не быть, и тогда цепочка оборвалась бы навсегда — телефон замолчал бы
 *  до ближайшей периодической работы или перезагрузки.
 */
class AlarmReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        AlarmScheduler.schedule(context)
        // Будильник — страховка: если сервис убили, он поднимет его обратно.
        AgentService.start(context)
        CheckinWorker.runNow(context)
    }
}
