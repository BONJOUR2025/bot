package pw.bonjour.mdm

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder

/** Постоянный сервис агента: держит телефон на связи.
 *
 *  Зачем он есть. Планировщик и будильники прошивка душит: на realme телефон
 *  замолкал на час с лишним, хотя будильник был исправно запланирован — система
 *  просто резала ему сеть в дремоте. Исключение из энергосбережения помогает, но
 *  оно ставится руками на каждом аппарате и слетает при сбросе, то есть на парке
 *  салонов не живёт.
 *
 *  Сервис на переднем плане система не усыпляет. Поэтому чек-ин выполняется
 *  прямо здесь, в собственном цикле, а не через планировщик. Будильник и
 *  периодическая работа остаются страховкой на случай, если сервис всё-таки
 *  убьют — тогда они его и поднимут обратно.
 *
 *  Цена — постоянное уведомление в шторке. На корпоративном телефоне это скорее
 *  плюс: сотрудник видит, что аппарат под управлением, и это честно.
 */
class AgentService : Service() {

    @Volatile
    private var running = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification())

        if (!running) {
            running = true
            Thread({ loop() }, "mdm-agent").start()
        }
        // START_STICKY: если процесс всё же убьют, система поднимет сервис снова.
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        super.onDestroy()
    }

    private fun loop() {
        while (running) {
            val ok = try {
                Checkin.run(applicationContext)
            } catch (e: Exception) {
                false
            }
            // Неудачный заход (нет сети, сервер лежит) — ждём меньше, чтобы
            // вернуться в строй быстрее, но не молотим впустую.
            val seconds = if (ok) Prefs.pollSeconds(applicationContext) else 30
            sleep(seconds)
        }
    }

    private fun sleep(seconds: Int) {
        // Спим короткими отрезками: так остановка сервиса не ждёт полного
        // интервала, а замечается почти сразу.
        var left = seconds
        while (running && left > 0) {
            try {
                Thread.sleep(1000)
            } catch (e: InterruptedException) {
                return
            }
            left -= 1
        }
    }

    private fun buildNotification(): Notification {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Управление устройством", NotificationManager.IMPORTANCE_MIN
            )
            channel.setShowBadge(false)
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
            .setContentText("Телефон под управлением компании")
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val CHANNEL_ID = "mdm-agent"
        private const val NOTIFICATION_ID = 4200

        /** Поднять сервис. Вызывается отовсюду, где агент оживает: загрузка
         *  телефона, обновление пакета, регистрация, открытие экрана, удачный
         *  чек-ин из страховочного воркера. Повторный вызов безвреден. */
        fun start(ctx: Context) {
            // Без регистрации сервису нечего делать: чек-ин всё равно упрётся в
            // отсутствие токена, а уведомление уже висело бы.
            if (Prefs.token(ctx).isBlank() && Prefs.enrollKey(ctx).isBlank()) return
            val intent = Intent(ctx, AgentService::class.java)
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    ctx.startForegroundService(intent)
                } else {
                    ctx.startService(intent)
                }
            } catch (e: Exception) {
                // Из фона на Android 12+ запуск сервиса иногда запрещён; тогда
                // его поднимет ближайший будильник или загрузка телефона.
            }
        }
    }
}
