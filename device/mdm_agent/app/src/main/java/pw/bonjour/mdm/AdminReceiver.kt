package pw.bonjour.mdm

import android.app.admin.DeviceAdminReceiver
import android.content.Context
import android.content.Intent

class AdminReceiver : DeviceAdminReceiver() {

    override fun onEnabled(context: Context, intent: Intent) {
        super.onEnabled(context, intent)
        // Как только права получены — сразу ставим регулярный чек-ин, чтобы
        // телефон не остался неуправляемым, если до настроек так и не дошли.
        CheckinWorker.schedule(context)
        AlarmScheduler.schedule(context)
    }
}
