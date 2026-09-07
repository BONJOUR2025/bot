package pw.bonjour.mdm

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder

/** Снимок с камеры из foreground-сервиса.
 *
 *  На Android 14 доступ к камере из фона запрещён, если приложение не работает
 *  как foreground-сервис с типом `camera` — иначе `openCamera` падает, а
 *  системная формулировка отказа сбивает с толку («disabled by policy» при
 *  чистой политике). Поэтому съёмка вынесена сюда: сервис поднимается на
 *  передний план, снимает и сразу гаснет.
 *
 *  Уведомление обязательно (иначе foreground-сервис не стартует) и заодно
 *  честно сообщает сотруднику, что делается снимок — как того и требует
 *  регламент.
 */
class CameraService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val commandId = intent?.getStringExtra(EXTRA_COMMAND_ID) ?: ""
        val lens = intent?.getStringExtra(EXTRA_LENS) ?: "back"

        startForeground(NOTIFICATION_ID, buildNotification())

        Thread {
            val result = Camera.captureAndUpload(applicationContext, commandId, lens)
            // Результат — асинхронный ack, как у установки приложений: сам
            // чек-ин к этому моменту уже завершился.
            Prefs.addAck(applicationContext, commandId, if (result == null) "done" else "failed", result ?: lens)
            CheckinWorker.runNow(applicationContext)
            stopForegroundCompat()
            stopSelf()
        }.start()

        return START_NOT_STICKY
    }

    private fun buildNotification(): Notification {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Служебные операции", NotificationManager.IMPORTANCE_LOW
            )
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
                .createNotificationChannel(channel)
        }
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setContentTitle("BONJOUR MDM")
            .setContentText("Идёт съёмка с камеры")
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setOngoing(true)
            .build()
    }

    @Suppress("DEPRECATION")
    private fun stopForegroundCompat() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            stopForeground(true)
        }
    }

    companion object {
        const val EXTRA_COMMAND_ID = "pw.bonjour.mdm.CAMERA_COMMAND_ID"
        const val EXTRA_LENS = "pw.bonjour.mdm.CAMERA_LENS"
        private const val CHANNEL_ID = "mdm-camera"
        private const val NOTIFICATION_ID = 4201

        /** Запускает съёмку. Возврат null означает «ack придёт асинхронно» —
         *  сервис отчитается сам, когда снимок готов или сорвался. */
        fun capture(ctx: Context, commandId: String, lens: String) {
            val intent = Intent(ctx, CameraService::class.java)
                .putExtra(EXTRA_COMMAND_ID, commandId)
                .putExtra(EXTRA_LENS, lens)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ctx.startForegroundService(intent)
            } else {
                ctx.startService(intent)
            }
        }
    }
}
