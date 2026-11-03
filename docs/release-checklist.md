# 发布目录与数据边界

日常运行产生的 `runs/`、私有输入、虚拟环境和历史备份不属于源码仓库。`.gitignore` 只是防误操作，发布包另有独立白名单。

## 生成源码包

```bash
python scripts/package_release.py --out ../wifi-migrate-source.zip
```

打包器只收录已知代码、文档、测试、工作流和明确列出的虚构示例。遇到无法解释的额外源码文件会停止；运行数据目录直接排除。ZIP 不含 `.git`，也不会自动上传到任何服务。

## 建立自己的 GitHub 仓库前

1. 在独立的发布目录操作，不要在含手机历史备份的父目录运行 `git add .`。
2. 查看 `git status --short` 和 `git diff --cached`，核对只有源码与虚构示例。
3. 不加入真实 `.adb`、TAR、配置 `.data`、CSV/JSON、二维码、离线扫码页、截图、日志或个人路径配置。
4. 不导入作者旧 `ab_decrypt` 仓库的 Git 历史或 remote。本仓库应该拥有独立历史。
5. 在 README 和兼容表中保留“电脑验证/模拟测试/作者历史经验/真机验证”的区分。

本地创建发布目录和 ZIP 不等于已发布。需要用户自己指定 GitHub 账户、仓库与上传操作后，再进行联网发布。

## 0.3.0 Beta

- Repository name: `android-wifi-migrate`
- Description: Cross-brand Android Wi-Fi migration from your Windows PC. Import, organize, convert, and transfer saved Wi-Fi networks using multiple methods.
- Topics: `android`, `wifi`, `wifi-migration`, `windows`, `shizuku`, `adb`, `qr-code`, `wifi-backup`
- Suggested tag: `v0.3.0-beta`. Mark the release as a pre-release.
- Attach the reviewed source ZIP and checksum. The experimental Android helper APK and its checksum are separate assets.

Suggested release text:

> WiFi Migrate 0.3.0 Beta is a Windows companion for reviewing, converting, and transferring Android Wi-Fi backups. If WiFi Password Manager works on both phones, start with its native backup and restore workflow. This release adds a Windows workflow for mixed sources, conflict review, selective export, QR and PDF output, and source-file archiving. The Android helper and direct ADB writes remain experimental. See the compatibility table for what has been tested on devices.
