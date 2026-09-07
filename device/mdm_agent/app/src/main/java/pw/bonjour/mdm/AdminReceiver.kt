package pw.bonjour.mdm

import android.app.admin.DeviceAdminReceiver
import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.Intent
import android.os.PersistableBundle

class AdminReceiver : DeviceAdminReceiver() {

    override fun onEnabled(context: Context, intent: Intent) {
        super.onEnabled(context, intent)
        // Как только права получены — сразу ставим расписание, чтобы телефон
        // не остался неуправляемым, если до настроек так и не дошли.
        CheckinWorker.schedule(context)
        AlarmScheduler.schedule(context)
    }

    /** Телефон настроили по QR: агент уже скачан, установлен и стал владельцем
     *  устройства. Адрес сервера и ключ регистрации приехали внутри самого QR,
     *  поэтому регистрируемся молча — экрана агента в этот момент никто не
     *  видит, и вводить что-то руками некому.
     */
    override fun onProfileProvisioningComplete(context: Context, intent: Intent) {
        super.onProfileProvisioningComplete(context, intent)

        val extras: PersistableBundle? = intent.getParcelableExtra(
            DevicePolicyManager.EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE
        )
        extras?.getString("server_url")?.takeIf { it.isNotBlank() }?.let {
            Prefs.setServerUrl(context, it)
        }
        extras?.getString("enroll_key")?.takeIf { it.isNotBlank() }?.let {
            Prefs.setEnrollKey(context, it)
        }

        CheckinWorker.schedule(context)
        AlarmScheduler.schedule(context)
        // Сети в момент настройки может ещё не быть; если регистрация не
        // пройдёт, её повторит ближайший чек-ин по расписанию.
        Enroller.enrollAsync(context)
    }
}
