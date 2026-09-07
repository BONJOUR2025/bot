package pw.bonjour.mdm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** После перезагрузки телефона политика применяется заново: часть запретов
 *  система хранит сама, но проверить и восстановить дешевле, чем гадать. */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        PolicyApplier.apply(context, Prefs.policy(context))
        CheckinWorker.schedule(context)
        CheckinWorker.runNow(context)
    }
}
