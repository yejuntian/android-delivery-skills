// Journey Harness 顶层插件声明
// 注意: AGP 版本必须 >= 9.0.0 才支持 Journeys testSuites。
// 这里的 AGP 版本只作用于"壳项目"本身,不影响被测的老项目。
plugins {
    id("com.android.application") version "9.0.0" apply false
    id("org.jetbrains.kotlin.android") version "2.0.0" apply false
}
