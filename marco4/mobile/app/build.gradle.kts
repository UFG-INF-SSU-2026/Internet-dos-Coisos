plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "br.ufg.coisos"
    compileSdk = 37

    defaultConfig {
        applicationId = "br.ufg.coisos.cuidador"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "4.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Para a entrega basta o APK debug (Build > Build APK(s)).
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures { compose = true }
    testOptions {
        unitTests.all { it.testLogging { events("passed", "failed") } }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.09.00")
    implementation(composeBom)
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.11.1")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.11.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")
    debugImplementation("androidx.compose.ui:ui-tooling")

    // Testes de unidade na JVM (./gradlew testDebugUnitTest). O org.json do
    // android.jar é só um esboço fora do aparelho, então os testes usam o real.
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20250517")
}
