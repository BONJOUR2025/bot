package pw.bonjour.mdm

import android.content.Context
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CameraMetadata
import android.hardware.camera2.CaptureRequest
import android.media.ImageReader
import android.os.Handler
import android.os.HandlerThread
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Снимок с камеры без предпросмотра — для потерянного или украденного телефона.
 *
 *  Экран для этого не нужен: Camera2 отдаёт кадр напрямую в ImageReader.
 *  Индикатор доступа к камере на Android 12+ система показывает принудительно и
 *  отключить его нельзя — скрытой съёмки на этих аппаратах не бывает, и это
 *  правильно.
 *
 *  Съёмка синхронная, с таймаутами на каждом шаге: команда не должна повиснуть,
 *  если камеру занял кто-то другой или сенсор не отвечает.
 */
object Camera {

    private const val OPEN_TIMEOUT_MS = 8_000L
    private const val CAPTURE_TIMEOUT_MS = 12_000L
    private const val UPLOAD_TIMEOUT_MS = 30_000

    /** @return текст ошибки, если снять или отправить не вышло; null при успехе. */
    fun captureAndUpload(ctx: Context, commandId: String, lens: String): String? {
        if (ctx.checkSelfPermission(android.Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED
        ) {
            return "Агенту не выдано разрешение на камеру"
        }
        // Камера может быть заблокирована политикой даже когда в самой политике
        // запрета нет: состояние setCameraDisabled переживает переустановку
        // агента и однажды осталось включённым. Поэтому владелец устройства
        // снимает блокировку прямо здесь, если политика не требует запрета.
        val dpm = Dpm.manager(ctx)
        val policyWantsDisabled = Prefs.policy(ctx)
            .optJSONObject("restrictions")?.optBoolean("camera_disabled", false) ?: false
        if (policyWantsDisabled) {
            return "Камера отключена политикой — снимите запрет «Отключить камеру»"
        }
        // Снимаем блокировку сразу с двух уровней, безусловно. getCameraDisabled
        // на realme вернул false, а камера всё равно была «disabled by policy» —
        // значит запрет сидит не в setCameraDisabled, а в пользовательском
        // ограничении DISALLOW_CAMERA, которого тот флаг не видит.
        val admin = Dpm.admin(ctx)
        runCatching { dpm.clearUserRestriction(admin, "no_camera") }
        // Принудительное переключение, а не просто setCameraDisabled(false).
        // Диагностика показала: на момент съёмки политика уже «false», а камера
        // всё равно закрыта. Система уведомляет камеру-сервис только при реальной
        // СМЕНЕ состояния — камера была отключена при провижининге, повторный
        // «false» смены не даёт, и сервис остаётся при устаревшем «запрещено».
        // true -> false делает смену настоящей и сбрасывает застрявшее состояние.
        runCatching {
            dpm.setCameraDisabled(admin, true)
            Thread.sleep(300)
            dpm.setCameraDisabled(admin, false)
        }
        Thread.sleep(600)

        val manager = ctx.getSystemService(Context.CAMERA_SERVICE) as? CameraManager
            ?: return "На телефоне нет доступа к камере"
        val cameraId = pickCamera(manager, lens)
            ?: return "Не найдена " + (if (lens == "front") "фронтальная" else "основная") + " камера"

        val (jpeg, reason) = capture(ctx, manager, cameraId)
        if (jpeg == null) return (reason ?: "Кадр получить не удалось") + " | " + diagnostics(ctx, manager)
        return upload(ctx, lens, jpeg)
    }

    /** Ближайшая к запрошенной сторона; если такой нет — хоть какая-нибудь. */
    private fun pickCamera(manager: CameraManager, lens: String): String? {
        val wanted = if (lens == "front") {
            CameraMetadata.LENS_FACING_FRONT
        } else {
            CameraMetadata.LENS_FACING_BACK
        }
        var fallback: String? = null
        for (id in manager.cameraIdList) {
            val facing = manager.getCameraCharacteristics(id)
                .get(CameraCharacteristics.LENS_FACING)
            if (facing == wanted) return id
            if (fallback == null) fallback = id
        }
        return fallback
    }

    /** @return кадр и null, либо null и причина, на какой стадии сорвалось:
     *  без кабеля это единственный способ понять, что не так. */
    private fun capture(
        ctx: Context, manager: CameraManager, cameraId: String
    ): Pair<ByteArray?, String?> {
        val thread = HandlerThread("mdm-camera").apply { start() }
        val handler = Handler(thread.looper)
        val size = jpegSize(manager, cameraId)
        val reader = ImageReader.newInstance(size.first, size.second, ImageFormat.JPEG, 1)

        var jpeg: ByteArray? = null
        val done = CountDownLatch(1)

        reader.setOnImageAvailableListener({ r ->
            val image = r.acquireLatestImage()
            if (image != null) {
                val buffer = image.planes[0].buffer
                jpeg = ByteArray(buffer.remaining()).also { buffer.get(it) }
                image.close()
            }
            done.countDown()
        }, handler)

        var camera: CameraDevice? = null
        try {
            val opened = openCamera(ctx, manager, cameraId, handler)
            camera = opened.first
            if (camera == null) {
                return null to ("Камера не открылась: " + (opened.second ?: "неизвестно"))
            }

            // Держим поток предпросмотра, пока делаем снимок: без него на многих
            // прошивках автоэкспозиция не сходится и одиночный кадр просто не
            // приходит. Это и была причина отказа на realme.
            val preview = camera.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
                addTarget(reader.surface)
                set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_AUTO)
                set(CaptureRequest.CONTROL_AE_MODE, CameraMetadata.CONTROL_AE_MODE_ON)
            }.build()
            val still = camera.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE).apply {
                addTarget(reader.surface)
                set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_AUTO)
                set(CaptureRequest.CONTROL_AE_MODE, CameraMetadata.CONTROL_AE_MODE_ON)
                set(CaptureRequest.JPEG_QUALITY, 85.toByte())
            }.build()

            if (!startCaptureSession(camera, reader, preview, still, handler)) {
                return null to "Не удалось настроить съёмку"
            }
            if (!done.await(CAPTURE_TIMEOUT_MS, TimeUnit.MILLISECONDS)) {
                return null to "Камера не отдала кадр за отведённое время"
            }
            return if (jpeg != null) jpeg to null else (null to "Кадр пришёл пустым")
        } catch (e: Exception) {
            return null to ("Ошибка съёмки: " + e.message)
        } finally {
            camera?.close()
            reader.close()
            thread.quitSafely()
        }
    }

    private fun openCamera(
        ctx: Context, manager: CameraManager, cameraId: String, handler: Handler
    ): Pair<CameraDevice?, String?> {
        var opened: CameraDevice? = null
        var error: String? = "нет ответа"
        val latch = CountDownLatch(1)
        try {
            manager.openCamera(cameraId, object : CameraDevice.StateCallback() {
                override fun onOpened(device: CameraDevice) {
                    opened = device
                    error = null
                    latch.countDown()
                }

                override fun onDisconnected(device: CameraDevice) {
                    device.close()
                    error = "камеру занял кто-то другой"
                    latch.countDown()
                }

                override fun onError(device: CameraDevice, err: Int) {
                    device.close()
                    error = "код " + err
                    latch.countDown()
                }
            }, handler)
        } catch (e: SecurityException) {
            return null to "нет разрешения"
        }
        latch.await(OPEN_TIMEOUT_MS, TimeUnit.MILLISECONDS)
        return opened to error
    }

    private fun startCaptureSession(
        camera: CameraDevice,
        reader: ImageReader,
        preview: CaptureRequest,
        still: CaptureRequest,
        handler: Handler
    ): Boolean {
        val ready = CountDownLatch(1)
        var ok = false
        @Suppress("DEPRECATION")
        camera.createCaptureSession(
            listOf(reader.surface),
            object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(session: CameraCaptureSession) {
                    try {
                        // Держим предпросмотр, чтобы автоэкспозиция сошлась, и
                        // даём ей полторы секунды до кадра.
                        session.setRepeatingRequest(preview, null, handler)
                        handler.postDelayed({
                            runCatching { session.capture(still, null, handler) }
                        }, 1500)
                        ok = true
                    } catch (e: Exception) {
                        ok = false
                    }
                    ready.countDown()
                }

                override fun onConfigureFailed(session: CameraCaptureSession) {
                    ready.countDown()
                }
            },
            handler
        )
        ready.await(CAPTURE_TIMEOUT_MS, TimeUnit.MILLISECONDS)
        return ok
    }

    /** Разумный размер: самый большой JPEG, но не крупнее ~1080p, чтобы кадр не
     *  весил мегабайты и уехал через нестабильный туннель. */
    private fun jpegSize(manager: CameraManager, cameraId: String): Pair<Int, Int> {
        return try {
            val map = manager.getCameraCharacteristics(cameraId)
                .get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
            val sizes = map?.getOutputSizes(ImageFormat.JPEG)?.toList().orEmpty()
            val capped = sizes.filter { it.width <= 1920 && it.height <= 1920 }
                .maxByOrNull { it.width.toLong() * it.height }
            val chosen = capped ?: sizes.minByOrNull { it.width.toLong() * it.height }
            if (chosen != null) Pair(chosen.width, chosen.height) else Pair(1280, 720)
        } catch (e: Exception) {
            Pair(1280, 720)
        }
    }

    /** Фактическое состояние камерных ограничений — чтобы понять, что держит
     *  камеру, когда снять её нашими средствами не вышло. */
    private fun diagnostics(ctx: Context, manager: CameraManager): String {
        val dpm = Dpm.manager(ctx)
        val camDisabled = runCatching { dpm.getCameraDisabled(null) }.getOrNull()
        val restrictions = runCatching {
            val um = ctx.getSystemService(Context.USER_SERVICE) as android.os.UserManager
            um.userRestrictions.keySet().filter { um.userRestrictions.getBoolean(it) }
                .filter { it.contains("camera") || it == "no_camera" }
        }.getOrElse { emptyList() }
        val ids = runCatching { manager.cameraIdList.toList() }.getOrElse { emptyList() }
        val owner = Dpm.isOwner(ctx)
        return "owner=" + owner + " camDisabled=" + camDisabled +
            " restrictions=" + restrictions + " cameraIds=" + ids
    }

    private fun upload(ctx: Context, lens: String, jpeg: ByteArray): String? {
        val boundary = "----mdm" + System.currentTimeMillis()
        val body = ByteArrayOutputStream()
        body.write(("--" + boundary + "\r\n").toByteArray())
        body.write(
            ("Content-Disposition: form-data; name=\"file\"; filename=\"snapshot.jpg\"\r\n" +
                "Content-Type: image/jpeg\r\n\r\n").toByteArray()
        )
        body.write(jpeg)
        body.write(("\r\n--" + boundary + "--\r\n").toByteArray())

        val connection = URL(Prefs.serverUrl(ctx) + "/api/mdm/device/snapshot")
            .openConnection() as HttpURLConnection
        connection.requestMethod = "POST"
        connection.connectTimeout = UPLOAD_TIMEOUT_MS
        connection.readTimeout = UPLOAD_TIMEOUT_MS
        connection.doOutput = true
        connection.setRequestProperty("X-Device-Token", Prefs.token(ctx))
        connection.setRequestProperty("X-Lens", lens)
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary)
        return try {
            connection.outputStream.use { it.write(body.toByteArray()) }
            val code = connection.responseCode
            if (code in 200..299) null else "Сервер не принял снимок (" + code + ")"
        } catch (e: Exception) {
            "Снимок не отправился: " + e.message
        } finally {
            connection.disconnect()
        }
    }
}
