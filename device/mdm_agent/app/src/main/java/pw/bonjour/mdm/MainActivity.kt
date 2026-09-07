package pw.bonjour.mdm

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

/** Служебный экран агента: показать состояние и провести первичную регистрацию.
 *
 *  Сотруднику здесь делать нечего — экран нужен тому, кто настраивает телефон.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var status: TextView
    private lateinit var serverUrl: EditText
    private lateinit var enrollKey: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        status = findViewById(R.id.status)
        serverUrl = findViewById(R.id.serverUrl)
        enrollKey = findViewById(R.id.enrollKey)

        serverUrl.setText(Prefs.serverUrl(this))
        enrollKey.setText(Prefs.enrollKey(this))

        findViewById<Button>(R.id.enroll).setOnClickListener { enroll() }
        findViewById<Button>(R.id.checkNow).setOnClickListener {
            CheckinWorker.runNow(this)
            toast("Запрос отправлен, обновите экран через несколько секунд")
        }
        findViewById<Button>(R.id.battery).setOnClickListener { requestBatteryExemption() }
        findViewById<Button>(R.id.release).setOnClickListener { confirmRelease() }
    }

    override fun onResume() {
        super.onResume()
        // Открытый экран — последний рубеж восстановления расписания:
        // сюда приходят руками именно тогда, когда что-то пошло не так.
        if (Prefs.token(this).isNotBlank()) {
            CheckinWorker.schedule(this)
            AlarmScheduler.schedule(this)
        }
        render()
    }

    private fun render() {
        val applied = Prefs.appliedVersion(this)
        val known = Prefs.policyVersion(this)
        val lines = listOf(
            "Владелец устройства: " + if (Dpm.isOwner(this)) "да" else "НЕТ",
            "ID устройства: " + Prefs.deviceId(this),
            "Модель: " + Build.MANUFACTURER + " " + Build.MODEL + " (Android " + Build.VERSION.RELEASE + ")",
            "Версия агента: " + BuildConfig.VERSION_NAME,
            "Регистрация: " + if (Prefs.token(this).isBlank()) "не пройдена" else "пройдена",
            "Политика: применена " + applied + " из " + known,
            "Последняя связь: " + Prefs.lastCheckin(this).ifBlank { "нет" },
            "Опрос команд: раз в " + Prefs.pollSeconds(this) + " с" +
                (if (AlarmScheduler.canBeExact(this)) "" else " (будильник неточный)"),
            "Ошибка: " + Prefs.lastError(this).ifBlank { "нет" }
        )
        status.text = lines.joinToString("\n")
    }

    private fun enroll() {
        val url = serverUrl.text.toString().trim().trimEnd('/')
        val key = enrollKey.text.toString().trim()
        if (url.isBlank() || key.isBlank()) {
            toast("Заполните адрес сервера и ключ регистрации")
            return
        }
        Prefs.setServerUrl(this, url)
        Prefs.setEnrollKey(this, key)

        Enroller.enrollAsync(this) { result ->
            runOnUiThread {
                toast(result)
                render()
            }
        }
    }

    /** Без этого Xiaomi, Honor и прочие агрессивные прошивки усыпляют агента,
     *  и телефон перестаёт выходить на связь до следующего открытия экрана. */
    private fun requestBatteryExemption() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            toast("Не требуется на этой версии Android")
            return
        }
        val power = getSystemService(POWER_SERVICE) as PowerManager
        if (power.isIgnoringBatteryOptimizations(packageName)) {
            toast("Экономия батареи для агента уже отключена")
            return
        }
        startActivity(
            Intent(
                Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                Uri.parse("package:" + packageName)
            )
        )
    }

    private fun confirmRelease() {
        if (enrollKey.text.toString().trim() != Prefs.enrollKey(this) || Prefs.enrollKey(this).isBlank()) {
            toast("Введите ключ регистрации, чтобы снять управление")
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Снять управление?")
            .setMessage(
                "Телефон перестанет подчиняться серверу, все запреты будут сняты, " +
                    "а вернуть управление можно будет только сбросом до заводских настроек."
            )
            .setNegativeButton("Отмена", null)
            .setPositiveButton("Снять") { _, _ ->
                try {
                    Dpm.manager(this).clearDeviceOwnerApp(packageName)
                    toast("Управление снято")
                } catch (e: Exception) {
                    toast("Не удалось: " + e.message)
                }
                render()
            }
            .show()
    }

    private fun toast(text: String) = Toast.makeText(this, text, Toast.LENGTH_LONG).show()
}
