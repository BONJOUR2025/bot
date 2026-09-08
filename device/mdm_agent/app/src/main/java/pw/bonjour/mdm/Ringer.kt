package pw.bonjour.mdm

import android.content.Context
import android.media.AudioManager
import android.media.RingtoneManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator

/** «Найти телефон»: громкий сигнал и вибрация на заданное время.
 *
 *  Для потерянного в салоне аппарата — как звонок в Find My Device. Громкость
 *  сигнала выкручивается принудительно на время звонка и возвращается обратно,
 *  чтобы беззвучный режим не заглушил поиск.
 */
object Ringer {

    private var ringtone: android.media.Ringtone? = null
    private var previousVolume: Int = -1
    private val handler = Handler(Looper.getMainLooper())
    private var stopper: Runnable? = null

    @Synchronized
    fun start(ctx: Context, seconds: Int) {
        stop(ctx)

        val audio = ctx.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
        if (audio != null) {
            previousVolume = audio.getStreamVolume(AudioManager.STREAM_ALARM)
            audio.setStreamVolume(
                AudioManager.STREAM_ALARM,
                audio.getStreamMaxVolume(AudioManager.STREAM_ALARM),
                0
            )
        }

        val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
        ringtone = RingtoneManager.getRingtone(ctx, uri)?.apply {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                isLooping = true
            }
            play()
        }

        vibrate(ctx)

        stopper = Runnable { stop(ctx) }
        handler.postDelayed(stopper!!, seconds.coerceIn(5, 300) * 1000L)
    }

    @Synchronized
    fun stop(ctx: Context) {
        stopper?.let { handler.removeCallbacks(it) }
        stopper = null
        ringtone?.let { runCatching { it.stop() } }
        ringtone = null
        (ctx.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator)?.cancel()
        if (previousVolume >= 0) {
            (ctx.getSystemService(Context.AUDIO_SERVICE) as? AudioManager)
                ?.setStreamVolume(AudioManager.STREAM_ALARM, previousVolume, 0)
            previousVolume = -1
        }
    }

    private fun vibrate(ctx: Context) {
        val vibrator = ctx.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator ?: return
        val pattern = longArrayOf(0, 600, 400)
        runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator.vibrate(VibrationEffect.createWaveform(pattern, 0))
            } else {
                @Suppress("DEPRECATION")
                vibrator.vibrate(pattern, 0)
            }
        }
    }
}
