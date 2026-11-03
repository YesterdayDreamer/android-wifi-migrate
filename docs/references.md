# 来源、相关项目与许可证边界

本项目从 YesterdayDreamer 的个人换机流程整理而来。相关操作见作者的[知乎回答](https://www.zhihu.com/question/1944038655040664256/answer/1960818896966778919)。备份提取本身不是本项目新发明的方法。

## 方法出处

- Joey Miller，2024-01-03：[How to backup Android WiFi keys (without root)](https://joeeey.com/blog/backup-android-wifi-keys-without-root/)。介绍 ADB 备份、解密以及设置数据路径。
- [lclevy/ab_decrypt](https://github.com/lclevy/ab_decrypt)。作者历史流程使用的解密工具，上游声明 GPLv3。本发布仓库不打包该工具、Git 历史或从它改造的源文件。
- AOSP [PasswordUtils](https://android.googlesource.com/platform/frameworks/base/+/28fe597aaf0395ad423868ad75d8ea502d121608/services/backup/java/com/android/server/backup/utils/PasswordUtils.java) 与 [PerformAdbRestoreTask](https://android.googlesource.com/platform/frameworks/base/+/a01d80b97e416b5e30913122b56270d5b3a93749/services/backup/java/com/android/server/backup/restore/PerformAdbRestoreTask.java)。当前容器读取器按其公开格式独立实现，包括 Java 有符号 byte 转 char 的密钥校验语义。上游代码为 Apache-2.0；本项目未复制上游 Java 源文件。
- [AOSP WifiConfiguration](https://android.googlesource.com/platform/packages/modules/Wifi/+/a554f2225ae6b52a9132aed29926632f0f093f60/framework/java/android/net/wifi/WifiConfiguration.java)：安全类型定义。
- [AOSP WifiShellCommand](https://android.googlesource.com/platform/packages/modules/Wifi/+/refs/heads/main/service/java/com/android/server/wifi/WifiShellCommand.java)：保存命令、参数和回调输出的协议参考。具体设备可能删改命令。
- [ZXing WiFi 解析器](https://github.com/zxing/zxing/blob/master/core/src/main/java/com/google/zxing/client/result/WifiResultParser.java)：二维码载荷字段参考；独立解码测试使用 zxing-cpp，而不是仅比较生成函数的字符串。

## 可选方案

- [WiFi Password Manager](https://github.com/Khh-vu/wifi-password-manager)：Android 11+，支持 Shizuku 或 Root，可导入/导出网络。本项目对其 `ssid/security/password/hidden` 等字段提供实验性格式适配，不附带 APK，也不代表与上游关联或获得兼容认证。格式参考为 2026-11-01 检查的 [WifiNetwork 模型](https://github.com/Khh-vu/wifi-password-manager/blob/main/app/src/main/kotlin/io/github/wifi_password_manager/domain/model/WifiNetwork.kt) 和[配置转换](https://github.com/Khh-vu/wifi-password-manager/blob/main/app/src/main/kotlin/io/github/wifi_password_manager/utils/WifiNetwork.kt)。
- [WiFiList](https://github.com/zacharee/WiFiList)：借助 Shizuku 读取已保存密码，重点是查看。
- [Shizuku 官方说明](https://shizuku.rikka.app/guide/setup/)：免 Root 启动方式与厂商限制。
- [Android 保存网络指南](https://developer.android.com/develop/connectivity/wifi/wifi-save-network-passpoint-config)与 [ACTION_WIFI_ADD_NETWORKS](https://developer.android.com/reference/android/provider/Settings#ACTION_WIFI_ADD_NETWORKS)：每批最多五条、由系统确认的保存接口。本项目还没有对应 APK。
- [Android 12 ADB backup 限制](https://developer.android.com/about/versions/12/behavior-changes-12#adb-backup-restrictions)：不能用旧教程保证当前固件仍可备份。
- [Microsoft netsh wlan](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/netsh-wlan)：Windows 原生 XML 导出参考。

## 发布内容

本项目新编写的源码采用 MIT 许可证。运行依赖通过包管理器安装，不把第三方依赖源码、二进制、ADB 或 APK 混入发布 ZIP。依赖及其许可证以各上游包为准：qrcode（BSD）、pypng（MIT）、PyCryptodome（上游许可）。

测试和示例凭据均为人为构造。个人真实备份只用于本地回归验证，不进入测试夹具、Git 历史或发布包。
