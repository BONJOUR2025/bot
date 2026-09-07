plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val agentVersionName = "0.2.3"
val agentVersionCode = 6

// Версия кладётся внутрь самого APK: сервер читает её из assets, чтобы знать,
// какая версия лежит у него и какие телефоны отстали. Альтернативы хуже —
// разбирать бинарный манифест Android или доверять имени файла, которое любой
// может переименовать по дороге.
val agentAssetsDir = layout.buildDirectory.get().asFile.resolve("generated/agentAssets")
val writeAgentVersion = tasks.register("writeAgentVersion") {
    val target = agentAssetsDir
    val content = """{"version_name":"$agentVersionName","version_code":$agentVersionCode}"""
    outputs.dir(target)
    doLast {
        target.mkdirs()
        target.resolve("agent_version.json").writeText(content)
    }
}
tasks.named("preBuild") { dependsOn(writeAgentVersion) }

android {
    namespace = "pw.bonjour.mdm"
    compileSdk = 34

    defaultConfig {
        applicationId = "pw.bonjour.mdm"
        minSdk = 24
        targetSdk = 34
        versionCode = agentVersionCode
        versionName = agentVersionName
        buildConfigField("String", "DEFAULT_SERVER_URL", "\"https://app.bonjour.pw\"")
    }

    // Ключ подписи приходит из окружения (в CI — из секретов репозитория).
    // Подпись обязана быть стабильной: агент, вставший владельцем устройства,
    // не удаляется, и APK с другой подписью на него уже не встанет — обновить
    // телефон можно будет только сбросом.
    signingConfigs {
        create("release") {
            val keystorePath = System.getenv("MDM_KEYSTORE_PATH")
            if (!keystorePath.isNullOrBlank()) {
                storeFile = file(keystorePath)
                storeType = "PKCS12"
                storePassword = System.getenv("MDM_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("MDM_KEY_ALIAS") ?: "mdm"
                keyPassword = System.getenv("MDM_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    sourceSets["main"].assets.srcDir(agentAssetsDir)

    buildFeatures {
        buildConfig = true
        viewBinding = false
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
    implementation("androidx.work:work-runtime-ktx:2.9.1")
}
