package pw.bonjour.mdm

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context

object Dpm {
    fun manager(ctx: Context): DevicePolicyManager =
        ctx.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager

    fun admin(ctx: Context): ComponentName = ComponentName(ctx, AdminReceiver::class.java)

    fun isOwner(ctx: Context): Boolean = manager(ctx).isDeviceOwnerApp(ctx.packageName)
}
