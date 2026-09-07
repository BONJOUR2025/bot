package pw.bonjour.mdm

import android.app.Activity
import android.app.admin.DevicePolicyManager
import android.content.Intent
import android.os.Bundle
import android.os.PersistableBundle

/** Две служебные активности, которых система требует от агента при настройке
 *  телефона по QR, начиная с Android 11.
 *
 *  Пока приложение целилось в старые версии, провижининг обходился одним
 *  получателем. Для targetSdk 30 и выше система в середине настройки спрашивает
 *  у самого агента, каким устройством управлять, и показывает ему экран
 *  завершения. Не находит этих активностей — прекращает настройку с
 *  обезличенным «Can't set up device», ничего не поясняя.
 *
 *  Экрана здесь нет намеренно: обе активности отвечают системе и сразу
 *  закрываются, сотрудник в салоне видит только штатный мастер настройки.
 */
class ProvisioningActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        when (intent.action) {
            DevicePolicyManager.ACTION_GET_PROVISIONING_MODE -> {
                // Управляем аппаратом целиком, а не рабочим профилем внутри
                // личного телефона: телефоны корпоративные.
                setResult(
                    RESULT_OK,
                    Intent().putExtra(
                        DevicePolicyManager.EXTRA_PROVISIONING_MODE,
                        DevicePolicyManager.PROVISIONING_MODE_FULLY_MANAGED_DEVICE
                    )
                )
            }

            DevicePolicyManager.ACTION_ADMIN_POLICY_COMPLIANCE -> {
                // Последний шаг мастера. Настройки из QR могли не доехать до
                // получателя (порядок шагов у разных прошивок разный), поэтому
                // забираем их и здесь — лишним не будет, значения те же.
                applyProvisioningExtras()
                CheckinWorker.schedule(this)
                AlarmScheduler.schedule(this)
                Enroller.enrollAsync(this)
                setResult(RESULT_OK)
            }

            else -> setResult(RESULT_CANCELED)
        }
        finish()
    }

    private fun applyProvisioningExtras() {
        val extras: PersistableBundle? = intent.getParcelableExtra(
            DevicePolicyManager.EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE
        )
        extras?.getString("server_url")?.takeIf { it.isNotBlank() }?.let {
            Prefs.setServerUrl(this, it)
        }
        extras?.getString("enroll_key")?.takeIf { it.isNotBlank() }?.let {
            Prefs.setEnrollKey(this, it)
        }
    }
}
