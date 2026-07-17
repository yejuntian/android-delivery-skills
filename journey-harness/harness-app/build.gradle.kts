// harness-app: 仅作为 Journey 运行载体,本身不含业务代码。
// 被测应用通过环境变量 JOURNEYS_CUSTOM_APP_ID 指向(老项目的 applicationId)。
// AGP >= 9.0.0 才支持 testSuites { create("journeysTest") }。
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.harness.journey"
    compileSdk = 36

    defaultConfig {
        // 壳项目自己的包名,与被测应用无关。运行时由 JOURNEYS_CUSTOM_APP_ID 重定向。
        applicationId = "com.harness.journey"
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    // 关键:Journeys 测试套件。AGP 9.0+ 专有 DSL。
    testSuites {
        create("journeysTest") {
            // 指向壳项目自己的 debug variant(必须有,仅用于套件编译)
            targetVariants += listOf("debug")
        }
    }
}

dependencies {
    // Journeys 运行时依赖由 AGP testSuites 自动注入,这里保持空。
}
