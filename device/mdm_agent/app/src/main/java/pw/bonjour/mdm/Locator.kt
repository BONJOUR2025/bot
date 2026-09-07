package pw.bonjour.mdm

import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.os.Looper
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Определение местоположения телефона по команде из панели.
 *
 *  Тексты ошибок здесь по-русски и человеческим языком: в отличие от остальных
 *  команд, их читает не разработчик, а оператор в панели, и по ним он должен
 *  понять, что делать с телефоном.
 */
object Locator {

    /** Сколько ждём свежую точку. В помещении спутники не видны, но сеть и
     *  Wi-Fi дают координаты за несколько секунд; больше ждать нет смысла —
     *  команда не должна висеть. */
    private const val FIX_TIMEOUT_MS = 20_000L

    fun locate(ctx: Context): Pair<String, String?> {
        val manager = ctx.getSystemService(Context.LOCATION_SERVICE) as? LocationManager
            ?: return "failed" to "На телефоне нет службы геолокации"

        if (!hasPermission(ctx)) {
            return "failed" to "Агенту не выдано разрешение на геолокацию"
        }
        enableLocationIfPossible(ctx, manager)?.let { return "failed" to it }

        // Сначала пробуем получить свежую точку и только потом смотрим на
        // последнюю известную: её может не быть вовсе, если геолокацией на
        // телефоне давно никто не интересовался.
        val location = requestFix(ctx, manager) ?: lastKnown(manager)
            ?: return "failed" to "Координаты получить не удалось: телефон не видит ни сети, ни спутников"

        Prefs.setPendingLocation(ctx, location.latitude, location.longitude, isoTime(location.time))
        val accuracy = if (location.hasAccuracy()) " ±" + location.accuracy.toInt() + " м" else ""
        return "done" to (location.latitude.toString() + "," + location.longitude.toString() + accuracy)
    }

    private fun hasPermission(ctx: Context): Boolean =
        ctx.checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED ||
            ctx.checkSelfPermission(android.Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    /** @return текст проблемы или null, если геолокация включена. */
    private fun enableLocationIfPossible(ctx: Context, manager: LocationManager): String? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) return null
        if (manager.isLocationEnabled) return null

        // Владелец устройства может включить геолокацию сам — сотруднику в
        // салоне для этого ничего делать не нужно.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            runCatching { Dpm.manager(ctx).setLocationEnabled(Dpm.admin(ctx), true) }
                .onSuccess { return null }
        }
        return "Геолокация выключена на телефоне, и включить её не удалось"
    }

    private fun lastKnown(manager: LocationManager): Location? {
        var best: Location? = null
        for (provider in providers(manager)) {
            val location = try {
                manager.getLastKnownLocation(provider)
            } catch (e: SecurityException) {
                null
            } ?: continue
            if (best == null || location.time > best.time) best = location
        }
        return best
    }

    /** Просит точку у всех доступных источников и берёт ту, что придёт первой. */
    private fun requestFix(ctx: Context, manager: LocationManager): Location? {
        val available = providers(manager).filter {
            runCatching { manager.isProviderEnabled(it) }.getOrDefault(false)
        }
        if (available.isEmpty()) return null

        val latch = CountDownLatch(1)
        var result: Location? = null
        val listener = object : LocationListener {
            override fun onLocationChanged(location: Location) {
                if (result == null) {
                    result = location
                    latch.countDown()
                }
            }

            // Абстрактными эти методы остаются на старых версиях Android:
            // без них слушатель не соберётся под minSdk 24.
            override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit
            override fun onProviderEnabled(provider: String) = Unit
            override fun onProviderDisabled(provider: String) = Unit
        }

        try {
            for (provider in available) {
                runCatching {
                    manager.requestLocationUpdates(provider, 0L, 0f, listener, Looper.getMainLooper())
                }
            }
            latch.await(FIX_TIMEOUT_MS, TimeUnit.MILLISECONDS)
        } catch (e: SecurityException) {
            return null
        } finally {
            runCatching { manager.removeUpdates(listener) }
        }
        return result
    }

    private fun providers(manager: LocationManager): List<String> {
        val result = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            result.add(LocationManager.FUSED_PROVIDER)
        }
        result.add(LocationManager.NETWORK_PROVIDER)
        result.add(LocationManager.GPS_PROVIDER)
        return result.filter { manager.allProviders.contains(it) }
    }

    private fun isoTime(millis: Long): String =
        java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", java.util.Locale.US).apply {
            timeZone = java.util.TimeZone.getTimeZone("UTC")
        }.format(java.util.Date(millis))
}
