package pw.bonjour.mdm

import android.app.ActivityManager
import android.app.KeyguardManager
import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Environment
import android.os.StatFs
import android.os.SystemClock
import org.json.JSONObject
import java.net.NetworkInterface

/** Состояние телефона: место, память, сеть, аптайм, защита экрана.
 *
 *  Всё «лучшим усилием»: что не прочиталось — просто не кладём в отчёт, чтобы
 *  редкий сбой чтения не портил чек-ин.
 */
object Telemetry {

    fun collect(ctx: Context): JSONObject {
        val json = JSONObject()

        runCatching {
            val stat = StatFs(Environment.getDataDirectory().path)
            json.put("storage_total_mb", (stat.blockCountLong * stat.blockSizeLong / 1048576L))
            json.put("storage_free_mb", (stat.availableBlocksLong * stat.blockSizeLong / 1048576L))
        }

        runCatching {
            val am = ctx.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            val mem = ActivityManager.MemoryInfo()
            am.getMemoryInfo(mem)
            json.put("ram_total_mb", mem.totalMem / 1048576L)
        }

        runCatching { network(ctx, json) }

        json.put("uptime_seconds", SystemClock.elapsedRealtime() / 1000L)

        runCatching {
            val km = ctx.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
            json.put("secure_lock", km.isDeviceSecure)
        }

        return json
    }

    private fun network(ctx: Context, json: JSONObject) {
        val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return
        val caps = cm.getNetworkCapabilities(cm.activeNetwork)
        val type = when {
            caps == null -> "none"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "mobile"
            else -> "other"
        }
        json.put("network", type)

        if (type == "wifi") {
            runCatching {
                val wifi = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
                @Suppress("DEPRECATION")
                val ssid = wifi?.connectionInfo?.ssid?.trim('"')
                if (!ssid.isNullOrBlank() && ssid != "<unknown ssid>") json.put("wifi_ssid", ssid)
            }
        }

        runCatching { ipAddress()?.let { json.put("ip_address", it) } }
    }

    /** Локальный IPv4 первого активного интерфейса. */
    private fun ipAddress(): String? {
        for (nif in NetworkInterface.getNetworkInterfaces()) {
            if (!nif.isUp || nif.isLoopback) continue
            for (addr in nif.inetAddresses) {
                if (!addr.isLoopbackAddress && addr.hostAddress?.contains('.') == true) {
                    return addr.hostAddress
                }
            }
        }
        return null
    }
}
