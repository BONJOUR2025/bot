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
    private const val CAPTURE_TIMEOUT_MS = 8_000L
    private const val UPLOAD_TIMEOUT_MS = 30_000

    /** @return текст ошибки, если снять или отправить не вышло; null при успехе. */
    fun captureAndUpload(ctx: Context, commandId: String, lens: String): String? {
        if (ctx.checkSelfPermission(android.Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED
        ) {
            return "Агенту не выдано разрешение на камеру"
        }
        // Запрет камеры в политике блокирует её даже владельцу устройства —
        // без этой проверки снимок падал бы с невнятной ошибкой открытия.
        if (Dpm.manager(ctx).getCameraDisabled(null)) {
            return "Камера отключена политикой — снимите запрет «Отключить камеру»"
        }

        val manager = ctx.getSystemService(Context.CAMERA_SERVICE) as? CameraManager
            ?: return "На телефоне нет доступа к камере"
        val cameraId = pickCamera(manager, lens)
            ?: return "Не найдена " + (if (lens == "front") "фронтальная" else "основная") + " камера"

        val jpeg = capture(ctx, manager, cameraId) ?: return "Кадр получить не удалось"
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

    private fun capture(ctx: Context, manager: CameraManager, cameraId: String): ByteArray? {
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
            camera = openCamera(ctx, manager, cameraId, handler) ?: return null
            val request = camera.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE).apply {
                addTarget(reader.surface)
                // Полный автомат: снимаем вслепую, наводить и выставлять некому.
                set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_AUTO)
                set(CaptureRequest.CONTROL_AE_MODE, CameraMetadata.CONTROL_AE_MODE_ON)
                set(CaptureRequest.CONTROL_AF_MODE, CameraMetadata.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
            }.build()

            if (!startCaptureSession(camera, reader, request, handler)) return null
            if (!done.await(CAPTURE_TIMEOUT_MS, TimeUnit.MILLISECONDS)) return null
            return jpeg
        } catch (e: Exception) {
            return null
        } finally {
            camera?.close()
            reader.close()
            thread.quitSafely()
        }
    }

    private fun openCamera(
        ctx: Context, manager: CameraManager, cameraId: String, handler: Handler
    ): CameraDevice? {
        var opened: CameraDevice? = null
        val latch = CountDownLatch(1)
        try {
            manager.openCamera(cameraId, object : CameraDevice.StateCallback() {
                override fun onOpened(device: CameraDevice) {
                    opened = device
                    latch.countDown()
                }

                override fun onDisconnected(device: CameraDevice) {
                    device.close()
                    latch.countDown()
                }

                override fun onError(device: CameraDevice, error: Int) {
                    device.close()
                    latch.countDown()
                }
            }, handler)
        } catch (e: SecurityException) {
            return null
        }
        latch.await(OPEN_TIMEOUT_MS, TimeUnit.MILLISECONDS)
        return opened
    }

    private fun startCaptureSession(
        camera: CameraDevice, reader: ImageReader, request: CaptureRequest, handler: Handler
    ): Boolean {
        val ready = CountDownLatch(1)
        var ok = false
        @Suppress("DEPRECATION")
        camera.createCaptureSession(
            listOf(reader.surface),
            object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(session: CameraCaptureSession) {
                    try {
                        session.capture(request, null, handler)
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
