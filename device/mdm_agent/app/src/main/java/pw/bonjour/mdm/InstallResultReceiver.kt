package pw.bonjour.mdm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller

class InstallResultReceiver : BroadcastReceiver() {

    companion object {
        const val EXTRA_COMMAND_ID = "pw.bonjour.mdm.COMMAND_ID"
        const val EXTRA_KIND = "pw.bonjour.mdm.KIND"
    }

    override fun onReceive(context: Context, intent: Intent) {
        val commandId = intent.getStringExtra(EXTRA_COMMAND_ID) ?: return
        val kind = intent.getStringExtra(EXTRA_KIND) ?: "install"
        val status = intent.getIntExtra(
            PackageInstaller.EXTRA_STATUS,
            PackageInstaller.STATUS_FAILURE
        )
        val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)

        when (status) {
            PackageInstaller.STATUS_SUCCESS ->
                Prefs.addAck(context, commandId, "done", kind)

            PackageInstaller.STATUS_PENDING_USER_ACTION ->
                // На владельце устройства этого быть не должно: система ставит
                // молча. Если всё-таки случилось — значит прав нет, и честнее
                // сказать об этом, чем показывать диалог в пустом салоне.
                Prefs.addAck(context, commandId, "failed", "requires_user_action")

            else ->
                Prefs.addAck(context, commandId, "failed", message ?: ("status_" + status))
        }
        CheckinWorker.runNow(context)
    }
}
