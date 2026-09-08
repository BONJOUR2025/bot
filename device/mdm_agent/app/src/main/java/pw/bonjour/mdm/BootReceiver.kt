package pw.bonjour.mdm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Восстановление расписания после перезагрузки телефона и после обновления
 *  самого агента.
 *
 *  Обновление здесь не для симметрии: система гасит будильники приложения,
 *  когда его пакет заменяют, и без этого обработчика телефон после накатывания
 *  новой версии перестал бы опрашивать команды — до перезагрузки или до того,
 *  как кто-то откроет экран агента руками.
 *
 *  Политика применяется заново по той же причине: часть запретов система хранит
 *  сама, но проверить и восстановить дешевле, чем гадать.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val handled = intent.action == Intent.ACTION_BOOT_COMPLETED ||
            intent.action == Intent.ACTION_MY_PACKAGE_REPLACED
        if (!handled) return

        PolicyApplier.apply(context, Prefs.policy(context))
        CheckinWorker.schedule(context)
        AlarmScheduler.schedule(context)
        AgentService.start(context)
    }
}
