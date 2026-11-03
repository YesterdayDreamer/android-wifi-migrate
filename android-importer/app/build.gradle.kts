plugins { id("com.android.application") version "8.7.3" }
android {
    namespace = "io.github.wifimigrate.importer"
    compileSdk = 35
    defaultConfig {
        applicationId = "io.github.wifimigrate.importer"
        minSdk = 30
        targetSdk = 35
        versionCode = 3
        versionName = "0.3.0"
    }
}
