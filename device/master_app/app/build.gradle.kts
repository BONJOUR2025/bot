plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// versionCode обязан расти с каждой выпущенной сборкой: APK с тем же или
// меньшим кодом Android поверх установленного не поставит.
// 1.1.0 — сканер бирок камерой (мост BonjourApp) и скачивание файлов браузером.
val appVersionName = "1.1.0"
val appVersionCode = 2

// Версия кладётся внутрь APK — сервер показывает её на странице установки,
// не разбирая бинарный манифест и не доверяя имени файла (так же у агента MDM).
val appAssetsDir = layout.buildDirectory.get().asFile.resolve("generated/appAssets")
val writeAppVersion = tasks.register("writeAppVersion") {
    val target = appAssetsDir
    val content = """{"version_name":"$appVersionName","version_code":$appVersionCode}"""
    outputs.dir(target)
    doLast {
        target.mkdirs()
        target.resolve("app_version.json").writeText(content)
    }
}
tasks.named("preBuild") { dependsOn(writeAppVersion) }

android {
    namespace = "pw.bonjour.master"
    compileSdk = 34

    defaultConfig {
        applicationId = "pw.bonjour.master"
        minSdk = 24
        targetSdk = 34
        versionCode = appVersionCode
        versionName = appVersionName
        buildConfigField("String", "START_URL", "\"https://app.bonjour.pw/employee/earnings\"")
        buildConfigField("String", "APP_HOST", "\"app.bonjour.pw\"")
    }

    // Ключ приходит из окружения (в CI — из секретов репозитория). Подпись
    // должна быть стабильной: обновление с другим ключом поверх установленного
    // приложения не встанет, мастеру придётся удалять и ставить заново.
    signingConfigs {
        create("release") {
            val keystorePath = System.getenv("SIGNING_KEYSTORE_PATH")
            if (!keystorePath.isNullOrBlank()) {
                storeFile = file(keystorePath)
                storeType = "PKCS12"
                storePassword = System.getenv("SIGNING_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("SIGNING_KEY_ALIAS") ?: "mdm"
                keyPassword = System.getenv("SIGNING_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    sourceSets["main"].assets.srcDir(appAssetsDir)

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    // Сканер штрихкодов Google Play: своя камера и распознавание, приложению
    // не нужно ни разрешение на камеру, ни собственный экран сканирования.
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")
}
