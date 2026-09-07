plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "pw.bonjour.mdm"
    compileSdk = 34

    defaultConfig {
        applicationId = "pw.bonjour.mdm"
        minSdk = 24
        targetSdk = 34
        versionCode = 4
        versionName = "0.2.1"
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
