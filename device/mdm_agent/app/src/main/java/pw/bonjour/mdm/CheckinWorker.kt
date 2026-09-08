package pw.bonjour.mdm

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

/** Страховка на случай, если постоянный сервис убили: поднимает его обратно и,
 *  раз уж проснулись, делает чек-ин сам. Основной ритм держит AgentService —
 *  планировщик прошивки душат, и полагаться на него нельзя.
 */
class CheckinWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {

    override fun doWork(): Result {
        val ctx = applicationContext
        AgentService.start(ctx)
        return if (Checkin.run(ctx)) Result.success() else Result.retry()
    }

    companion object {
        private const val PERIODIC = "mdm-checkin-periodic"
        private const val ONESHOT = "mdm-checkin-now"

        private fun constraints() = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        fun schedule(ctx: Context) {
            // 15 минут — минимальный период, который WorkManager вообще
            // соблюдает; просить чаще бесполезно, система всё равно урежет.
            val request = PeriodicWorkRequestBuilder<CheckinWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints())
                .setBackoffCriteria(BackoffPolicy.LINEAR, 1, TimeUnit.MINUTES)
                .build()
            WorkManager.getInstance(ctx)
                .enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.UPDATE, request)
        }

        fun runNow(ctx: Context) {
            val request = OneTimeWorkRequestBuilder<CheckinWorker>()
                .setConstraints(constraints())
                .setBackoffCriteria(BackoffPolicy.LINEAR, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(ctx)
                .enqueueUniqueWork(ONESHOT, ExistingWorkPolicy.REPLACE, request)
        }
    }
}
