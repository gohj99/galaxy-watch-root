# 维护、构建与多型号适配

本文面向维护者。安装步骤见 [root 教程](ROOT_zh-CN.md)。当前硬件成功记录仅对应 SM-L315F / L315FXXS3BZF4，本文不将其他型号或新的自动构建标为实测。

核对日期：2026-11-15。

## 1. 构建输入和发布内容

一次构建需要：

- 三星对应版本的公共内核源码；
- 对应型号/地区的 DTS，以及该系统版本需要的增量源码；
- 已验证的内核配置、工具链和构建变量；
- 固定到提交 SHA 的 BakaSU 源码；
- 已验证的 boot 模板和它的 SHA-256；
- 对应设备已验证的 AVB 签名私钥，通过 `AVB_PRIVATE_KEY_B64` 注入。

构建的目标是一个已签名 `boot.img`。**每次构建不需要完整原厂固件，也不需要重新下载 AP。** 仍须匹配设备正在运行的系统和 vendor 模块，不能把“不下载完整固件”理解成“不需要考虑固件兼容性”。

发布规则：每个型号/版本的 Release 只附加签名 boot，不附加 AP/BL/CP/CSC、vbmeta、APK、密钥或报告。哈希、源码出处、BakaSU 提交、系统版本和实测状态写在 Release 正文；构建报告留在 Actions artifacts。GitHub 自动生成的源码归档是平台功能，不是本项目另外上传的刷机附件。

使用 GPL 等许可证下的内核源码发布二进制时，应同时履行相关源码和许可义务。不要只留下可能失效的原厂下载链接；保存可复现该二进制的对应源码、补丁、配置、许可证和构建说明，并在正文给出获取位置。具体以相关组件的许可证为准。

## 2. 源码包怎样组合

三星 OSRC：[搜索 SM-L315](https://opensource.samsung.com/uploadSearch?searchValue=SM-L315)。下载前按网站要求确认协议；本仓库的发现脚本不代为同意，也不绕过访问限制。

SM-L315F BZF4 本地成功构建使用的是：

1. `SM-L305U_Opensource.zip`：公共内核，内部有 `L305USQU3BZB4_Kernel.tar.gz`。
2. `SM-L315F_EUR_Opensource_dts.zip`：本型号 DTS，内部有 `L315FXXU3BZB4_kernel.tar.gz`。
3. 文件名包含 `L315FXXS3BZF4` 的公共更新 ZIP，内部有 `L305USQS3BZF4_kernel.tar.gz`。

第三个 ZIP 的完整名称记录在 [`devices/sm-l315f/device.json`](../devices/sm-l315f/device.json)。文件名中的公共型号是 L305U，并不说明所有使用者都要刷 L305U boot；必须以包内说明、共享源码关系和实际目标配置为准。

公共包是完整源码，DTS 和更新包可能只是部分文件。几百 KB 的包通常不能单独作为完整内核，但可以是完整构建中必要的一层输入。应按这一组包的说明依次合并到正确目录，检查同名文件覆盖顺序，再确认结果。

**当前 `fetch_source.py` 还需要对实际包结构完成集成验证。** 它按可识别的内核根目录收集文件；只有部分 DTS 或补丁目录的包，不能仅凭脚本退出码判断已完整覆盖。首次公开构建前，需与本地已成功的合并树逐项比对，补齐处理及回归测试。

本地准备时可先列清单，找到各内层归档：

```bash
unzip -l downloads/SM-L305U_Opensource.zip
unzip -l downloads/SM-L315F_EUR_Opensource_dts.zip
# 对更新 ZIP 同样先列清单，再按随包说明定位和合并。
tar -tzf downloads/L305USQU3BZB4_Kernel.tar.gz | head -n 30
tar -tzf downloads/L315FXXU3BZB4_kernel.tar.gz | head -n 30
tar -tzf downloads/L305USQS3BZF4_kernel.tar.gz | head -n 30
```

这些是检查命令，不是通用于所有三星包的解压合并脚本。不要把三层不同目录结构不经检查就覆盖到一起。

## 3. boot 模板为什么保留

`Image` 是内核，不是完整 Android boot 镜像。已知所有参数时，可以用工具生成镜像头和 AVB 元数据；本项目选择保留已成功镜像中的三星布局与尾部，减少未经验证的变量。

当前 `scripts/build_boot.py` 只接受：

- Android boot header v4；
- 内核长度非零；
- boot 内 ramdisk 大小为 0；
- GKI boot signature 大小为 0；
- 存在可识别的 AVB footer；
- 替换内核后，三星 `SEANDROIDENFORCE` 标记仍满足当前脚本的对齐检查。

这与本例的分区安排相符，不代表 Watch 4、5、6、8 都是此布局。`init_boot`、`vendor_boot` 和 `boot` 是不同分区，不能交换。[AOSP 布局说明](https://source.android.com/docs/core/architecture/partitions/generic-boot)、[boot 头定义](https://android.googlesource.com/platform/system/tools/mkbootimg/+/refs/heads/main/include/bootimg/bootimg.h)。

模板可从匹配的原厂 AP 提取一次，或在有权限时从匹配设备备份；本项目已有成功模板，也可以直接用该型号已签名成功 boot 作为模板。以后只替换内核并重新签名，不必每次依赖完整固件。

模板应放在不可变的下载位置，配置 URL 和完整 SHA-256。可以指向该型号首次发布的、已确认成功的签名 boot；无须另外发布 AP 或“模板 ZIP”。更换模板、系统大版本或启动布局后，重新验证，不自动沿用兼容性结论。

本例历史成功 boot 的 SHA-256：

```text
153400e7c782a71836a63d4c5bb9ab14ead163fedf2036546e170bbb8bd7c3f0
```

当前脚本用内核 SHA-256 作为 AVB salt 以固定这一项输入。历史成功文件使用的签名参数可能不同，所以当前脚本重构建的镜像即使静态检查通过，也不能称为上述同一文件或已经实测的镜像。

## 4. 本地编译顺序

推荐在 Linux / WSL 的 Linux 文件系统中编译，避免把整个内核构建目录放在 Windows 挂载盘。以下命令从本仓库根目录执行；路径是仓库内的工作目录约定。

先根据源码包说明准备并核对：

```text
work/src/kernel/       已正确合并的完整三星源码树
work/toolchain/        配置中固定版本的 Android clang 工具链
work/base-boot.img     已验证的 boot 模板
```

不要直接执行包含未知脚本的第三方压缩包。这里的源码准备包含目录层次与覆盖关系的人工核对，尚不能用未验证的下载合并脚本替代。

安装构建依赖：

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  bc bison build-essential cpio dwarves flex gcc-aarch64-linux-gnu \
  gcc-arm-linux-gnueabi libelf-dev libssl-dev lz4 rsync unzip xz-utils \
  git curl python3 openssl
```

从 `device.json` 取出并核对工具链 URL、SHA-256、BakaSU 提交和构建变量。下载工具链时固定版本并核对哈希，不用宿主机的任意 clang 代替。当前配置是 `clang-r487747c`。

当前 SM-L315F 的准备和编译示例：

```bash
set -euo pipefail
export WORK="$PWD/work"
export PATH="$WORK/toolchain/bin:$PATH"
export ARCH=arm64 LLVM=1 LLVM_IAS=1
export CROSS_COMPILE=aarch64-linux-gnu-
export CROSS_COMPILE_COMPAT=arm-linux-gnueabi-
export BRANCH=android14-6.1 KMI_GENERATION=11
export TARGET_BUILD_VARIANT=user TARGET_SOC=s5e5535
export TARGET_PRODUCT=fresh7ulxx
export KERNEL_RELEASE_SUFFIX=-android14-11

python3 - <<'PY'
import json
from pathlib import Path
cfg = json.loads(Path('devices/sm-l315f/device.json').read_text())
Path('work/overrides.json').write_text(json.dumps(cfg['build']['overrides']))
PY

python3 scripts/prepare_kernel.py \
  --source "$WORK/src/kernel" \
  --config devices/sm-l315f/kernel.config \
  --certificate devices/sm-l315f/stock-gki.pem \
  --output "$WORK/out" \
  --manifest "$WORK/kernel-manifest.json" \
  --overrides "$WORK/overrides.json" \
  --bakasu-commit 548d1dda060ca198823d8808804d01f5209ef4a9

bash scripts/build_kernel.sh \
  "$WORK/src/kernel" "$WORK/out" "$WORK/toolchain" 4

cat "$WORK/out/kernelrelease"
sha256sum "$WORK/out/arch/arm64/boot/Image"
```

上述示例只针对当前配置。源码和配置的变化会影响生成结果；需要查看最终 `.config` 和编译日志，而不是只看脚本是否生成了 Image。原厂模块的符号版本、依赖、配置和签名信任也必须核对。

本地已成功内核的 Image SHA-256 记录为：

```text
3584c23d0f733e30fe7629eb29914001d548871b2121a0445c470680ee575fac
```

这个值用来辨认历史 Image，不承诺不同环境自动重现相同字节。

## 5. AVB 密钥和签名

### GitHub Actions secret

用户只下载 boot，不需要维护者私钥。维护者应使用这组设备已经验证可用的签名密钥；新生成一把任意密钥不自动获得相同启动结果。

GitHub 仓库中建立 Actions secret：

```text
AVB_PRIVATE_KEY_B64
```

内容是**整个私有 PEM 文件字节的单行 base64**。不是 PEM 正文去掉头尾，不是公钥，也不是私钥路径。base64 是编码，不是加密。

例如已安装并认证 GitHub CLI 后，在自己的 PowerShell 中执行以下示例；替换私钥路径和 `OWNER/REPO`，不要把真实 base64 写入命令文本或提交到仓库：

```powershell
$keyPath = (Resolve-Path 'C:\keys\watch-avb.pem').Path
$env:AVB_PRIVATE_KEY_B64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($keyPath))
try {
  $env:AVB_PRIVATE_KEY_B64 | gh secret set AVB_PRIVATE_KEY_B64 --repo OWNER/REPO
} finally {
  Remove-Item Env:\AVB_PRIVATE_KEY_B64 -ErrorAction SilentlyContinue
}
```

不要把含私钥的变量输出到终端、日志或截图。也可以在 GitHub 设置中手动添加 secret；不要放在公开的 Repository Variables 中。关于 Actions secret 的管理见 [GitHub 官方说明](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions)。

workflow 用环境变量读取 secret，再在临时工作目录解码成 PEM 供 avbtool 使用。不得把临时 PEM 纳入 cache、artifact 或 Release；不要为签名步骤开启 shell 跟踪输出。私钥应另行安全备份，GitHub secret 不能作为唯一备份。

### 本地签名

在你自己的 Linux 构建环境中，通过安全方式注入相同环境变量；不要把私钥实际值写进脚本。以下命令只用于已经核对的模板和 Image：

```bash
set -euo pipefail
: "${AVB_PRIVATE_KEY_B64:?Set the base64 private PEM in the environment first}"
umask 077
key_file=$(mktemp)
trap 'rm -f "$key_file"' EXIT
printf '%s' "$AVB_PRIVATE_KEY_B64" | base64 --decode > "$key_file"

python3 scripts/build_boot.py \
  --base "$WORK/base-boot.img" \
  --kernel "$WORK/out/arch/arm64/boot/Image" \
  --avbtool scripts/avbtool.py \
  --key "$key_file" \
  --output "$WORK/boot.img" \
  --manifest "$WORK/boot-manifest.json" \
  --partition-size 67108864

python3 scripts/avbtool.py verify_image \
  --image "$WORK/boot.img" --key "$key_file"
sha256sum "$WORK/boot.img"
```

`verify_image` 通过说明镜像与给定密钥在该校验范围内一致，不说明三星启动链会接受它。新产物需要按主教程重打包并在对应设备上验证。本项目不制作自定义 vbmeta。

## 6. 三种证书不要混淆

| 材料 | 作用 | 是否随仓库公开 |
| --- | --- | --- |
| AVB 私钥 | 为 boot 添加 AVB 签名 | 绝不公开，只通过 secret/受控本地环境使用 |
| 原厂 GKI 公共证书 `stock-gki.pem` | 当前配置中用于保留对相应原厂签名模块的信任 | 可以公开；它不是私钥 |
| BakaSU Manager APK 签名证书 | 内核侧辨认受信任 Manager 的相关输入 | 公共指纹可以记录；私钥不属于本项目 |

原厂模块证书匹配不能单独解决模块 ABI 问题；Manager APK 能安装也不能单独说明其获得了内核信任。本例 ARM32 用户空间还要求兼容的 Manager 和组件。需要同时核对，不能互相代替。

## 7. 当前 workflow 做到了什么

文件：[`.github/workflows/nightly.yml`](../.github/workflows/nightly.yml)。

当前实现包括定时发现入口、手动参数、按设备配置下载/编译、使用 `AVB_PRIVATE_KEY_B64` 签名和仅上传签名 boot 的 Release 步骤。**尚未完成 GitHub Actions 端到端成功运行验证。**

| 项目 | 当前实际状态 |
| --- | --- |
| 定时表达式 | 每天 UTC 02:17，即新加坡/北京时间 10:17；实际启动时间可能延迟 |
| 定时型号 | 默认只有 `sm-l315f`，不是 Watch 4～8 的构建矩阵 |
| 三星发现 | 解析搜索表并选取首个匹配项；首行和 upload ID 不能当作固件版本时间顺序 |
| 新条目处理 | 首个匹配 upload ID 与固定配置不同会暂停自动构建，等待人工核对 |
| 下载协议 | 不自动代替用户同意三星下载条款；访问失败不会产生该次自动发布 |
| 源码下载 URL | 当前配置为空，需要维护者补齐有效且有权使用的不可变输入 |
| boot 模板 URL | 当前配置为空，需要设置；SHA-256 已记录历史成功文件 |
| BakaSU 版本 | 固定提交，不会自动追踪“最新版” |
| 源码合并 | 需要完成实际公共包/DTS/增量覆盖的集成核对 |
| 原厂模块 ABI 核对 | 尚未集成到公开 workflow 的发布门禁 |
| 产物硬件验证 | Actions 本身无法在目标手表上完成，需人工或独立测试设备 |
| 发布标识 | 当前以 Image 哈希前缀构成 tag；不足以独立表达模板、密钥和系统版本变化 |

调度细节见 [GitHub 官方 schedule 文档](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。此仓库还是构建框架，不是“每天抓到任何新固件就能安全发布通用 root boot”的成品服务。

本次整理中修正了 workflow 中重复 `env` 键，并让内核准备步骤能找到下载的 clang。它们是局部修正，不代表其他构建步骤已在 GitHub 验证通过。

### 首次启用前

1. 将真实仓库地址、许可证与来源信息补全，先提交可审阅的源码和文档。
2. 为当前型号设置不可变 boot 模板 URL，保留正确 SHA-256。
3. 按三星条款取得并核对源码，设置下载 URL，记录归档哈希。当前下载脚本记录输入哈希，但没有完整实现预期源码哈希门禁，应补齐后再无人值守发布。
4. 完成源码覆盖和配置的对照验证，核对模块 ABI；先在本地复现构建。
5. 配置签名 secret，通过 `workflow_dispatch` 验证一次完整构建和发布路径。注意现有流程一旦运行到 Release 步骤，会尝试直接创建公开 Release，不会先等人工实机确认。
6. 在真正无人值守前加入发布门禁：区分已批准的配置与候选更新，只有已验证输入允许自动公开。首次适配、新内核大版本、模板或密钥变更需要重新实机验证。

目前这些前置条件未全部完成，因此不应仅填上 URL 和私钥就把当前流程当成生产发布服务。

## 8. 每日检查与新版本发布的建议流程

要实现长期稳定的每日任务，建议将“发现”“构建候选”“公开发布”分开：

1. **发现**：每天读取三星条目及其版本说明，保存与已批准输入的差异。不要以 ZIP 文件大小、表格位置或 upload ID 大小推断版本新旧。
2. **确定输入**：解析完整源码/DTS/增量的对应关系，核对设备型号、系统构建号和归档哈希；遇到网站验证或需要重新同意协议时留待维护者处理，不猜 URL。
3. **选择 BakaSU**：可监测上游更新，但构建时解析并固定到完整提交 SHA。新增提交先作为候选；不要把上游默认分支的每次变化直接作为用户可刷的“稳定版本”。
4. **候选构建**：固定工具链、配置、源码层次和模板，生成 Image，检查内核 release、模块符号/ABI、Manager 兼容、分区大小、boot 布局和 AVB。报告留在 Actions。
5. **硬件确认**：按型号和系统验证无线刷入、启动、root、模块加载、常用硬件与恢复原厂。新型号没有实机记录时保持未验证状态。
6. **发布**：只附加该型号签名 boot。正文记录全部输入和结果，不把“构建通过”改写成“实测可用”。

发布去重应覆盖完整输入：型号、适配系统、源码归档哈希、BakaSU 提交、内核配置、工具链、模板哈希、签名公钥标识和包装脚本版本。不要只用 Image 哈希决定是否无需发布；同一 Image 换模板或签名后，最终 boot 也会变化。

如果源码包或模板下载链接会过期，应先解决合规且可靠的输入保存方式，再开启每日发布。原厂源码更新和用户设备 OTA 的时间也未必一致，Release 必须写清适用的完整系统版本。

## 9. Watch 4 / 5 / 6 / 7 / 8 的适配范围

| 系列 | 仓库当前状态 |
| --- | --- |
| Watch 4，包括不同尺寸和 Classic | 未建独立配置、未实测 |
| Watch 5，包括 Pro | 未建独立配置、未实测 |
| Watch 6，包括 Classic | 未建独立配置、未实测 |
| Watch 7 | 只有 SM-L315F BZF4 有本地成功记录 |
| Watch 8 及其其他款式 | 未建独立配置、未实测 |

Watch FE、Ultra 等名称也不应自动归入上述某代配置。相同 SoC 或同一系列名称不能证明 boot、DTS、模块和启动链相同。

新增配置之前，至少收集：准确型号/地区/连接制式、系统构建号、内核版本与配置、用户空间 ABI、源码清单、启动镜像头和分区大小、原厂模块及其兼容要求、可行的解锁与恢复路径。然后决定能否复用当前脚本，还是需要新的 boot 布局处理。

现有设备目录约定是：

```text
devices/<device-id>/device.json
devices/<device-id>/kernel.config
devices/<device-id>/stock-gki.pem
```

证书条目依设备实际需要设置，不能盲用 Watch 7 的证书和配置。`workflow_dispatch` 接受设备目录名，只表示能够选择配置，不等于新设备已经受支持。多型号定时矩阵和每型号发布状态还需要单独实现与验证。

## 10. Release 正文模板

以下是人工填写模板，不是现有 workflow 已自动生成的所有字段：

```markdown
型号：SM-XXXXX（连接制式、尺寸、地区如有必要一并写明）
适用系统：完整构建号
验证状态：未实机验证 / 已实机验证（列明设备与日期）

附件：唯一的已签名 boot .img
boot 字节数：...
boot SHA-256：...

Samsung OSRC 条目与版本：...
公共源码、DTS、增量归档及各自 SHA-256：...
对应完整源码、补丁、配置、许可证与构建说明：...
BakaSU 完整提交 SHA：...
工具链与内核配置标识：...
boot 模板 SHA-256：...
签名公钥标识：...（不含私钥）
Manager 版本、ABI、官方获取位置及 APK SHA-256：...
已测试项目与已知问题：...
安装文档与恢复方式：docs/ROOT_zh-CN.md
```

不要将 AP 或 APK 添进附件作为快捷方式；按项目约定，它们由用户在本地准备。正文需要足够信息让用户判断“这个 boot 能不能用于我的系统”。

## 11. 工具自检

AP 重打包工具与合成测试可独立运行，不需要手表、固件或私钥：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install lz4
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试覆盖 RBS MD5 范围、其他成员内容和元数据、boot 解压一致性，以及损坏输入、未知格式、重复/缺少 boot、已有输出和缺少 AVB 标记等拒绝条件。合成 boot 不是可启动镜像；测试通过不构成实机验证。

2026-11-15 的本地校验记录：7 项自动测试通过；另使用本例真实原厂 AP（约 4.24 GB）与历史成功签名 boot 做了一次完整重打包。输出保留 12 个成员，除 `boot.img.lz4` 外的内容与成员元数据保持一致，boot 解压后 SHA-256 为前述 `153400e7...`，RBS/MD5 校验通过。新工具生成的 AP 只做了文件级验证，没有再次在手表上刷入。

真实 AP 的调用示例和结果检查见[安装教程第 6 节](ROOT_zh-CN.md#6-准备签名-boot重打包完整-ap)。工具只写本地输出，不会触发 NetOdin 或发布 Release。
