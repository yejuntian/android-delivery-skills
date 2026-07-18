// harness-app: 仅作为 Journey 运行载体,本身不含业务代码。
// 被测应用通过环境变量 JOURNEYS_CUSTOM_APP_ID 指向(老项目的 applicationId)。
// AGP >= 9.0.0 才支持 testSuites { create("journeysTest") }。
plugins {
    id("com.android.application")
}

// 构建输出默认放到 Skill 目录外，避免 Android Studio 或脚本运行后触发 Skill 体积限制。
// 脚本会显式传入同名环境变量；手动打开壳时使用用户缓存目录作为安全默认值。
val journeyBuildRoot = System.getenv("ANDROID_DELIVERY_JOURNEY_BUILD_ROOT")
    ?: file("${System.getProperty("user.home")}/.cache/android-delivery-skills/journey-build/${rootProject.projectDir.absolutePath.hashCode().toUInt().toString(16)}/harness-app").absolutePath
layout.buildDirectory.set(file(journeyBuildRoot))

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
}

// 不要手写 Journey testSuites。使用当前 Android Studio 的
// New > Journey Test 生成与 Studio Labs 版本匹配的 DSL、依赖和运行配置。
