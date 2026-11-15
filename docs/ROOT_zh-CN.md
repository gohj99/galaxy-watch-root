# Galaxy Watch 使用 BakaSU 获取 root

本文记录本项目已经成功的方案：在匹配的三星内核中加入 BakaSU，生成并签名 `boot.img`，在完整原厂 AP 包里只替换 `boot.img.lz4`，最后通过 **NetOdin 无线下载模式**刷入。

**当前实测范围只有 Galaxy Watch 7 SM-L315F、系统版本 L315FXXS3BZF4。** Watch 4、5、6、8 是后续适配目标，不是已支持列表。不同尺寸、蓝牙/LTE、地区和运营商版本也不能默认通刷。本文核对日期为 2026-11-15。

本项目的 GitHub Release 只附加各型号的**已签名 boot 镜像**。完整 AP、BL、CP、CSC、vbmeta、Manager APK 和构建报告都不作为 Release 附件发布。用户在本地准备 AP 并重打包。

## 1. 先确认自己适合哪条路线

| 你的设备和目的 | 当前建议 |
| --- | --- |
| SM-L315F，正在运行 L315FXXS3BZF4，能正常解锁 Bootloader | 可以按本文核对实测配置，再安装对应 boot |
| SM-L315F，但系统不是 BZF4 | 先完成对应版本的内核、模块和启动验证；不要把 BZF4 成功当成跨版本保证 |
| Watch 4 / 5 / 6 / 8，或其他 Watch 7 型号 | 先看[维护与适配说明](MAINTAINERS_zh-CN.md)，不能使用本页的 SM-L315F boot |
| 只想下载 boot 安装 | 阅读本文第 2～9 节，不需要编译内核，也不需要 AVB 私钥 |
| 想自己构建、维护 GitHub Actions 或增加型号 | 先阅读本文，再看[维护与适配说明](MAINTAINERS_zh-CN.md) |

### “不依赖固件构建”具体是什么意思

需要区分三个阶段：

1. **编译内核**：使用三星公开源码、对应 DTS、配置和工具链，编译出 `Image`。不用每次下载完整原厂固件。
2. **制作 boot**：本项目把 `Image` 放入已验证的 boot 模板，保留三星布局和尾部，再用维护者的 AVB 密钥签名。后续构建只需这个模板，不需要完整 AP。
3. **按本文实测方式刷入**：NetOdin 加载的是完整 AP，用户需要在本地准备匹配的原厂 AP，再替换里面的 boot。这是刷入载体的要求，与 Actions 编译的输入分开。

从已知参数生成 boot 头和 AVB 元数据在技术上可行；不能据此断言三星开源包一定足够生成某只表可启动的完整镜像。本项目目前使用已验证模板，也没有实测“只包含 boot 的 tar”刷入路径。[AOSP 的 boot 布局说明见参考资料 4、5](#12-参考资料)。

## 2. 已实测配置

以下是维护者提供的成功记录与本地镜像核对结果，不代表三星或 BakaSU 官方为本项目背书。

| 项目 | 实测值 |
| --- | --- |
| 手表 | Galaxy Watch 7，`SM-L315F` |
| 产品标识 | `fresh7ul`；编译目标 `fresh7ulxx`，SoC `s5e5535` |
| 系统版本 | `L315FXXS3BZF4` |
| 系统构建标识 | `BP2A.250325.020.L315FXXS3BZF4` |
| Android / API | Android 16 / API 36 |
| 内核 | `6.1.134-android14-11`，ARM64 |
| 用户空间 ABI | `armeabi-v7a,armeabi`，ARM32 |
| BakaSU 提交 | `548d1dda060ca198823d8808804d01f5209ef4a9` |
| 配套 Manager | `v4.2.0-rc3-548d1dda`，版本码 `35259`，`armeabi-v7a` |
| boot 大小 | `67,108,864` 字节，即 64 MiB |
| boot 布局 | Android boot header v4，boot 内 ramdisk 大小为 0 |
| boot AVB 算法 | `SHA256_RSA4096` |
| 刷入路径 | NetOdin，无线下载模式，完整 AP 只替换 `boot.img.lz4` |
| vbmeta | AP 内保留原厂版本，没有替换成自制 vbmeta |
| root 验证 | `uid=0(root)`，上下文 `u:r:ksu:s0`；SELinux 为 `Enforcing` |

实测成功 boot 的 SHA-256：

```text
153400e7c782a71836a63d4c5bb9ab14ead163fedf2036546e170bbb8bd7c3f0
```

实测配套 APK 文件名与 SHA-256：

```text
BakaSU_v4.2.0-rc3_35259-armeabi-v7a-release.apk
b00d662314e287502b8d9f28550ad1b9b7c60db601e84b0c62cf048258b24c9d
```

这些哈希用于辨认这一组历史实测文件。以后发布的新 boot 或 Manager 应使用其发布说明中的新哈希；不能继续套用上面的值。相同源码重新签名后，boot 的哈希也可能因 AVB salt 等参数变化而不同，重构建文件不自动继承实测结论。

## 3. 动手前准备

### 数据、解锁和恢复

- 先备份手表与手机中的重要数据、应用设置、健康数据和需要重新配置的 eSIM 信息。备份范围以各应用实际支持为准。
- **解锁 Bootloader 会清除用户数据。本文使用的完整 AP 还包含 `userdata.img.lz4` 和 `misc.bin.lz4`，刷入也按可能清空数据准备。** 只替换 boot 不代表只写 boot 分区；CSC 留空也不能保证保留数据。
- 三星 Knox 官方说明，root 等非官方修改可能触发不可逆的 Knox Warranty Bit；刷回原厂系统不能将已触发的硬件位复原。支付、企业安全和其他服务的影响须按具体型号、地区和软件版本确认。[参考资料 3](#12-参考资料)
- 在首次刷入前，把匹配的完整原厂包、原厂 AP、所需恢复工具和本页教程保存在电脑上，并确认自己能进入无线 Download 模式。不要等系统起不来后才找恢复文件。
- 自定义 boot 应用于已解锁且允许此类镜像的设备。遇到运营商限制、OEM 解锁不可用或安全状态拒绝时，先停止；本项目不提供漏洞解锁或绕过这些限制的方法。

### 电脑端工具

| 工具或文件 | 用途 |
| --- | --- |
| Windows 电脑、稳定的无线连接 | 本文的 NetOdin 主流程 |
| Android SDK Platform-Tools | `adb` 配对、安装 Manager、验证 root；从 Android 官方获取 |
| 与设备无线下载协议相容的 NetOdin | 传输 AP；本次实测未记录具体 NetOdin 版本号 |
| Python 3.11 或更新版本 | 运行本仓库的 AP 重打包工具 |
| Python `lz4` 包 | 把签名 boot 压缩为 `boot.img.lz4` |
| 本仓库源码 | 包含 `scripts/repack_ap.py` |
| 对应型号、系统版本的签名 boot | 从本项目实际发布的对应条目获取，核对发布说明 |
| 与当前系统匹配的完整原厂固件包 | 提取 AP；同时保留 BL/CP/CSC 供恢复使用 |
| 兼容用户空间 ABI 与内核信任设置的 BakaSU Manager | 安装管理界面及用户空间组件 |

NetOdin 是社区流传工具，本项目不分发其可执行文件，也没有已核验的唯一官方下载渠道。使用你能确认来源的版本，不为运行陌生程序而关闭安全软件。NetOdin 无线下载和正常开机后的无线 ADB 是两种连接，不能互相替代。

建议在本地磁盘准备至少十几 GB 空间。实例 AP 约 4.24 GB，原文件和重打包文件需要同时保留；FAT32 单文件限制不适合这一大小。下方工具使用同卷硬链接发布已校验文件，Windows 建议在 NTFS 上运行。

## 4. 核对型号和系统，连接 ADB

先在手表“设置 → 关于手表 → 软件信息”等位置记录型号、系统版本和构建号。不同 One UI Watch 版本的菜单名称会变化。

需要无线 ADB 时，在软件信息页连续点击软件版本等开发者入口，打开开发者选项，再启用 ADB 调试和无线调试。按 Android 官方 Wear OS 调试说明完成配对。[参考资料 1、2](#12-参考资料)

新版本无线调试通常分别显示**配对端口**和**调试连接端口**。先把电脑和手表接到同一网络，用实际显示的地址替换以下占位符：

```powershell
adb pair WATCH_IP:PAIR_PORT
adb connect WATCH_IP:DEBUG_PORT
adb devices -l
```

在手表上确认配对或授权。旧版本可能没有 `adb pair` 流程，应按实际系统的调试界面操作；不要固定假设端口一定是 5555。有多个 ADB 设备时，为后续命令加上 `-s 实际设备序列号`。

在正常系统中读取信息：

```powershell
adb shell getprop ro.product.model
adb shell getprop ro.build.version.incremental
adb shell getprop ro.build.fingerprint
adb shell uname -r
adb shell getprop ro.product.cpu.abilist
```

本例应能对应 `SM-L315F`、`L315FXXS3BZF4` 和前述 ABI。内核名称含 `android14`，不代表用户空间一定是 Android 14；本例用户空间实际为 Android 16。

**内核是 ARM64，不代表 Manager 必须选 ARM64。** 这里的用户空间只有 ARM32 ABI，要使用已经确认兼容的 `armeabi-v7a` Manager。其他手表请读取自身 ABI。

## 5. 解锁 Bootloader

已经解锁的设备先确认状态，无须重复解锁。第一次解锁时：

1. 在开发者选项中找到并启用 OEM 解锁；若选项缺失、受管理或受运营商限制，先停止。
2. 进入手表的重启/启动模式菜单。部分三星手表的常见入口是同时长按 Home 和 Back，出现 `Rebooting...` 后松开，并连续短按 Home 打开启动菜单；短按选择、长按执行。**按键时机、解锁入口和确认键会因型号及 One UI 版本变化，这不是本项目逐键实测的 Watch 4～8 通用步骤。**
3. 根据屏幕中的 `Download`、`Unlock Bootloader` 或相应解锁提示进入确认页面；有些版本需在该页面按提示长按按键进入解锁。
4. 只在屏幕明确提示 Bootloader 解锁和数据清除时确认。没有出现明确提示时，不凭猜测按键，也不选择其他维护操作。
5. 等待清除数据和重启，重新完成系统设置；再次检查 OEM 解锁/Bootloader 状态，必要时重新开启无线调试。

常见菜单操作可参考 [WearOS 工具箱作者的三星手表说明](https://help.wearosbox.com/faq/device/samsung.html)。该页面不是全代际验证记录。本文作者实测确认了 NetOdin 无线刷入结果，但没有保留下完整的解锁按键录像。

AOSP 的解锁文档说明了解锁时的数据清除和物理确认要求；其中的 `fastboot flashing unlock` **不是本文给三星手表使用的命令**。[参考资料 6](#12-参考资料)

## 6. 准备签名 boot，重打包完整 AP

### 6.1 取得正确文件

安装前应有三组互相匹配的文件：

1. 你的手表当前系统，以及为恢复准备的完整原厂包。
2. 对应型号和该系统版本的 BakaSU 签名 boot。
3. 与该内核配套的 Manager。

三星 [Open Source Release Center](https://opensource.samsung.com/uploadSearch?searchValue=SM-L315) 提供的是开源发布资料。不要把下载到的 `*_Opensource*.zip` 直接交给 NetOdin：**源码压缩包不是原厂 AP 刷机包**。

本例使用的原厂 AP 文件名为：

```text
AP_L315FXXS3BZF4_QB111284685_REV00_user_low_ship_MULTI_CERT_meta_WATCH_OS16.tar.md5
```

准备它的原始副本，并另存对应原厂 BL/CP/CSC。注意型号、地区、版本和 Bootloader 防回滚限制；不要为了匹配本例强行降级或混用其他型号文件。若 Release 没写清楚适配的系统版本或实测状态，先让维护者补齐信息。

将下载的签名 boot 保存为工作目录中的 `boot.img`。**这只是本地文件改名，不能重新压缩、截断或更改镜像内容。** 在 PowerShell 核对：

```powershell
(Get-Item .\boot.img).Length
(Get-FileHash .\boot.img -Algorithm SHA256).Hash.ToLower()
```

使用本例历史实测文件时，大小为 `67108864` 字节，SHA-256 为第 2 节的 `153400e7...` 完整值。使用后续 Release 时，以那个 Release 的说明为准。

### 6.2 使用仓库工具重打包

以下命令在**本仓库根目录**运行。示例约定：原厂 AP 在 `stock` 子目录，签名镜像在 `boot.img`；请先放好文件。AP 原文件不要改名覆盖成输出文件。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install lz4

.\.venv\Scripts\python.exe scripts\repack_ap.py `
  --ap ".\stock\AP_L315FXXS3BZF4_QB111284685_REV00_user_low_ship_MULTI_CERT_meta_WATCH_OS16.tar.md5" `
  --boot ".\boot.img" `
  --output ".\out\AP_BakaSU_L315FXXS3BZF4.tar.md5" `
  --report ".\out\ap-repack-report.json"
```

上面 PowerShell 的反引号必须是行末最后一个字符。也可以把命令合成一行。Linux / WSL 用户可创建普通 Python 虚拟环境后，用同一个脚本和相应路径运行。

这个工具只做本地 AP 包装：

- 输入 boot 必须已签名；工具仅检查 Android / AVB 标记，**不会替你签名，也不会认证 AVB 密钥是否受设备信任**。
- 只替换唯一的 `boot.img.lz4`，使用与本例一致的 LZ4 帧参数。
- 保留其他 AP 成员的顺序、文件内容和成员元数据，包括原厂 vbmeta、init_boot、vendor_boot、userdata 和 misc。
- 重新生成三星 RBS 尾部；Odin MD5 覆盖 tar 内容与前三行 RBS 元数据，不包含最后的校验行。
- 再次读取输出，核对成员、boot 解压后哈希和 MD5；发现未知尾部格式、缺少 boot、重复成员或已有输出文件便报错。
- 不会连接手表或自动刷入，不会生成保留数据的精简 AP。

工具只实现已识别的三星 RBS AP 格式，不能据此推断兼容所有年代的三星固件。遇到 `Unsupported AP footer` 应分析实际格式；不要删除 `.md5` 后缀强行绕过校验。

成功时报告应包含：

```json
{
  "passed": true,
  "replacement": "boot.img.lz4",
  "other_member_payloads_and_metadata_preserved": true,
  "lz4_roundtrip_verified": true,
  "footer": { "md5_verified": true }
}
```

这是报告中的部分字段；完整报告还包括 boot 和输出 AP 的哈希。**全部校验通过仅说明重打包一致，不等于手表能启动。**

不要用普通 ZIP 压缩替代 tar，不要直接拼接旧 MD5 尾部，也不要只计算 tar 的 MD5。保留原厂 AP 供恢复；本地 AP 和报告不上传本项目 Release。

### 6.3 关于 vbmeta

本项目已确认成功的路径是：**只替换 AP 中的 boot，保留原厂 vbmeta。** 维护者此前测试的自制 vbmeta 不可用，因此本文不提供关闭验证、刷空 vbmeta 或改写 BL 内 vbmeta 的步骤。

这不代表任意设备都会接受本地签名 boot。是否能够启动仍与解锁状态、镜像布局、当前启动链及固件有关。遇到验证拒绝时，先恢复对应原厂文件，不照抄其他设备的 vbmeta 方案。

## 7. 用 NetOdin 无线刷入

### 7.1 进入无线 Download 模式并建立网络

1. 先确认电量充足、备份可用，电脑不会休眠。把原厂文件和重打包后的 AP 都准备好。
2. 从手表启动菜单进入 `Download (wireless)` 或系统实际提供的无线下载入口。常见启动菜单入口见第 5 节；**普通 Download、Recovery 和 Download (wireless) 不能混为一谈**。
3. 观察下载界面的无线模式、SSID、地址或连接提示。某些版本可按屏幕说明切换 AP/STA 模式；部分版本使用双击 Back 切换。不要把某一款表的手势当作通用标准。
4. 若手表工作在 AP 模式，让电脑连接手表显示的 Wi-Fi。Windows 提示“无 Internet”不代表这条刷机链路无效；要保持连接。若设备使用 STA 模式，则按该版本的说明让电脑与手表处于可互通的网络。
5. 启动 NetOdin，等它显示已发现并连接到手表。以手表下载界面和 NetOdin 的实际连接状态为准，不使用无线 ADB 地址代替下载模式地址。

无线入口和模式切换的逐键路径尚未形成 SM-L315F BZF4 的完整录像记录。本文确认的是维护者使用该无线模式成功刷入，不声称每个上述菜单分支都在 Watch 7 上逐项测试。找不到入口时，应先查对应型号与当前 One UI 的说明；不要继续猜测刷入。

### 7.2 选择完整 AP

在 NetOdin 中：

1. AP 槽选择第 6 节输出的 `AP_BakaSU_L315FXXS3BZF4.tar.md5`。
2. 等待文件加载和校验完成，确认日志未报 MD5 或包格式错误。
3. 再核对手表型号、系统版本和所选文件。普通 root 安装不需要因本教程而修改 BL/CP/CSC；需要完整恢复时，按第 10 节使用匹配原厂包。
4. 不勾选 `Re-Partition`、`NAND Erase` 等会改变分区或擦除布局的选项，不装载来路不明的 PIT。
5. 准备好接受完整 AP 可能清除数据后，开始刷入；等待工具结束并显示成功，再等待手表重启。

**实测确认的是 AP 槽加载完整 AP、只更换包内 boot；未逐项记录当时其他槽位与选项。本文不把“仅填 AP 槽”“数据保留”或“单 boot tar”写为已实测结论。**

传输过程中保持网络和供电，不切换热点、不休眠电脑。工具报告成功代表传输/写入流程通过，仍需开机后验证内核和 root。若卡在启动画面或报验证错误，转第 10 节恢复，不反复刷不同型号的镜像。

## 8. 安装 Manager，验证 root

### 8.1 获取配套 Manager

从 [BakaSU 官方仓库](https://github.com/Baka-SU/BakaSU)及其构建渠道获取与内核兼容的 Manager。本文实测版本的原始构建记录是 [Actions run 42723315215](https://github.com/Baka-SU/BakaSU/actions/runs/42723315215)，使用前述 `armeabi-v7a` APK。Actions 构建附件可能过期；该链接是来源记录，不保证永久可下载。

如旧附件过期，请维护者提供仍可取得、经过匹配验证的上游来源和哈希。不能任意换成一个同名 APK。APK 的 ABI、版本、签名与内核的 Manager 信任设置都可能影响使用；第三方重签名 APK 不能假定受信任。

实测 APK 的签名证书 SHA-256 记录如下，供具备 Android 构建工具的读者进一步核对：

```text
d3469712b6214462764a1d8d3e5cbe1d6819a0b629791b9f4101867821f1df64
```

它是 **Manager APK 的签名证书指纹**，不是 boot 的 AVB 公钥，也不是原厂内核模块证书。

### 8.2 安装并授权

手表开机并完成设置后，重新连接无线 ADB。刷入或重置后，地址、端口和配对记录可能改变，按第 4 节重新检查。

在 APK 所在目录运行：

```powershell
Get-FileHash .\BakaSU_v4.2.0-rc3_35259-armeabi-v7a-release.apk -Algorithm SHA256
adb install -r .\BakaSU_v4.2.0-rc3_35259-armeabi-v7a-release.apk
```

在手表上打开 BakaSU Manager，查看内核识别和工作状态。然后尝试：

```powershell
adb shell su -c id
```

如提示未授权，在 Manager 中允许可信的 `Shell` / `com.android.shell` 使用超级用户，再重试。不要把权限授予所有应用。期望输出包含：

```text
uid=0(root) gid=0(root)
```

继续核对：

```powershell
adb shell uname -r
adb shell getenforce
adb shell su -c id
```

本例成功记录中 SELinux 仍是 `Enforcing`。本文不要求改为 Permissive。`uname -r` 相同本身不能证明 root 成功，核心证据是 Manager 识别正常、授权生效，以及 `su -c id` 确实返回 root。

建议在不安装额外模块的状态下先测试重启、蓝牙、Wi-Fi、触控、充电、传感器、手机连接和你常用的功能，再逐个增加模块。保留原厂恢复文件和当前成功版本。

## 9. 更新系统、内核和 Manager

### 系统 OTA 或升级

不要假定 OTA 能在修改 boot 后正常安装，也不要把旧 boot 直接刷到升级后的系统。先备份并准备新系统的恢复文件。需要恢复原厂才能更新时，按匹配版本恢复后再更新；升级后，等待对应版本完成适配再重新 root。

本项目暂不提供三星手表上的 KernelSU 手机通用 OTA 操作，也没有验证“OTA 后自动保留 root”。完整 AP 的方式可能清除数据，不适合宣称为日常无损更新。

### BakaSU / Manager 更新

“上游更新”不等于“本手表已验证”。当前实测提交被固定为第 2 节的 SHA，不能把仓库分支最新状态当成本文实测版本。更新内核侧 BakaSU 时，同时检查 ARM32 兼容、Manager 信任关系和模块 ABI，再完成实机启动与 root 测试。

如果只更新 Manager，也先保留旧 APK，确认新版本 ABI、签名和兼容要求。出现安装冲突或 root 失效时，先核对，不随意卸载重装或更换重签名版本。

## 10. 恢复原厂与故障处理

### 恢复原则

能进入无线 Download 模式时，可以使用先前保存的匹配原厂包，按该固件要求用 NetOdin 恢复。原厂 AP 会带回原厂 boot；完整恢复时可能还需要同套 BL/CP/CSC。准确选择同型号、同地区且允许刷入的版本，不跨 Bootloader 防回滚等级强降级。

恢复可能清空数据。刷回原厂并不能复原已经触发的 Knox 硬件位。**不要在自定义 boot 仍存在或无法确认完整原厂状态时重新锁定 Bootloader。** 没有可靠的本型号重锁验证时，让设备保持已解锁状态并先核对恢复情况。

若 Download 和 Recovery 都无法进入，本文没有可保证有效的软件救援步骤；停止反复尝试，考虑对应设备的维修渠道。AP 重打包工具只能处理文件，不能修复损坏的下载模式或硬件。

### 常见问题

| 现象 | 先检查什么 |
| --- | --- |
| 开源网站下载了几十万字节的 ZIP | 可能只是 DTS 或增量更新；查看文件清单与 README，不能拿它当完整内核或 AP |
| `adb pair` 成功，但 `adb connect` 失败 | 配对端口与连接端口是否混用，手表实际 IP 是否变化，是否同一网络 |
| NetOdin 无法发现设备 | 是否进入无线 Download；电脑是否连接下载模式的网络；手表网络模式、路由隔离和防火墙提示是否正确 |
| AP 报 MD5 错误 | 是否使用完整输出文件；是否被网盘或归档工具改写；重新运行重打包并查看报告，不关闭校验硬刷 |
| `Unsupported AP footer` | 当前 AP 不是工具已支持的 RBS 格式，需要适配，不能直接删尾部 |
| 启动时报签名/验证错误 | Bootloader 是否确实解锁，boot 是否来自对应型号和版本，签名与模板是否匹配；优先恢复原厂 |
| 卡在开机画面、重启循环 | 内核、DTS、模块 ABI、模板或系统版本不匹配均有可能；进入无线 Download 恢复原厂 AP |
| Wi-Fi、蓝牙、传感器等异常 | 核对运行内核与原厂 vendor 模块的兼容性；“能开机”不等于适配完成 |
| APK 提示 `NO_MATCHING_ABIS` | 读取 `ro.product.cpu.abilist`；本例应选 `armeabi-v7a`，不要只看 ARM64 内核 |
| APK 提示签名不一致、安装冲突 | 核对既有 Manager 与下载 APK 的签名，不强行覆盖来源不明的版本 |
| Manager 显示不支持或未安装 | 确认刷入了正确 boot、内核包含对应 BakaSU、Manager 版本/ABI/签名匹配 |
| `su` 被拒绝 | 检查 Manager 对 Shell 的授权与内核工作状态，不用全局放权代替排查 |
| OTA 失败或 root 消失 | 更新可能检查或替换 boot；回到匹配的原厂/新版本适配流程，勿重复套用旧 boot |

## 11. 报告结果时请提供这些信息

提交 Issue 时提供型号、地区、完整系统版本、`uname -r`、用户空间 ABI、所用 boot 的 SHA-256、Manager 版本与来源、是否解锁、实际 NetOdin 操作以及故障发生在哪一步。贴日志前去掉序列号、账号、IP、公网地址等个人信息。

验证报告应区分：

- 文件校验通过；
- NetOdin 写入完成；
- 能进入系统；
- Manager 工作且 `su -c id` 返回 root；
- 常用硬件和功能测试通过。

这些阶段不能互相代替。只有文件构建成功的型号，应标为“构建产物，尚未实机验证”，不能标为“已支持”。

## 12. 参考资料

1. [Android 官方：在 Wear OS 设备上调试](https://developer.android.com/training/wearables/get-started/debugging)
2. [Android 官方：SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)
3. [Samsung Knox 官方：root、Knox 与 Warranty Bit](https://docs.samsungknox.com/admin/knox-platform-for-enterprise/faqs/faq-115013562087/)
4. [AOSP：Generic boot partition](https://source.android.com/docs/core/architecture/partitions/generic-boot)
5. [AOSP：boot 镜像头定义](https://android.googlesource.com/platform/system/tools/mkbootimg/+/refs/heads/main/include/bootimg/bootimg.h)
6. [AOSP：Bootloader 锁定与解锁](https://source.android.com/docs/core/architecture/bootloader/locking_unlocking)
7. [三星 OSRC：搜索 SM-L315](https://opensource.samsung.com/uploadSearch?searchValue=SM-L315)
8. [BakaSU 官方源码](https://github.com/Baka-SU/BakaSU)、[官方安装说明](https://bakasu.org/zh-Hans/guide/install)
9. [BakaSU ARM32 用户空间兼容相关 PR #612](https://github.com/Baka-SU/BakaSU/pull/612)
10. [社区作者说明：WearOS 工具箱的三星手表指南](https://help.wearosbox.com/faq/device/samsung.html)；用于查阅常见菜单，不能代替本型号实测。

公开资料与本文实测范围不一致时，以明确的型号、系统版本和验证记录为准；新版本需要重新核对。
