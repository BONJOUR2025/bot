package pw.bonjour.mdm

import android.content.Context
import android.net.wifi.WifiConfiguration
import android.net.wifi.WifiManager
import android.net.wifi.WifiNetworkSuggestion
import android.os.Build

/** Раздача Wi-Fi на телефон.
 *
 *  Владелец устройства может прописать сеть, чтобы аппарат подключался к
 *  салонному Wi-Fi сам, без ручного ввода на каждом телефоне. На Android 10+
 *  старый способ (addNetwork) убрали для обычных приложений, но владельцу
 *  устройства оставили — используем его, а на новых версиях подстраховываемся
 *  предложениями сети (network suggestions).
 */
object WifiActions {

    fun addNetwork(ctx: Context, ssid: String, password: String, hidden: Boolean): Pair<String, String?> {
        val wifi = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            ?: return "failed" to "нет доступа к Wi-Fi"

        // Основной путь для владельца устройства: постоянная конфигурация сети.
        val legacy = runCatching { addLegacy(wifi, ssid, password, hidden) }.getOrDefault(false)
        if (legacy) return "done" to "сеть добавлена"

        // Подстраховка на новых версиях: предложение сети (подключится, когда
        // окажется в зоне действия).
        val suggested = runCatching { addSuggestion(ctx, ssid, password) }.getOrDefault(false)
        return if (suggested) "done" to "сеть предложена системе"
        else "failed" to "не удалось добавить сеть"
    }

    @Suppress("DEPRECATION")
    private fun addLegacy(wifi: WifiManager, ssid: String, password: String, hidden: Boolean): Boolean {
        val config = WifiConfiguration().apply {
            SSID = "\"" + ssid + "\""
            hiddenSSID = hidden
            if (password.isBlank()) {
                allowedKeyManagement.set(WifiConfiguration.KeyMgmt.NONE)
            } else {
                preSharedKey = "\"" + password + "\""
                allowedKeyManagement.set(WifiConfiguration.KeyMgmt.WPA_PSK)
            }
        }
        val netId = wifi.addNetwork(config)
        if (netId == -1) return false
        wifi.enableNetwork(netId, false)
        wifi.saveConfiguration()
        return true
    }

    private fun addSuggestion(ctx: Context, ssid: String, password: String): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return false
        val wifi = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        val builder = WifiNetworkSuggestion.Builder().setSsid(ssid)
        if (password.isNotBlank()) builder.setWpa2Passphrase(password)
        val status = wifi.addNetworkSuggestions(listOf(builder.build()))
        return status == WifiManager.STATUS_NETWORK_SUGGESTIONS_SUCCESS
    }
}
