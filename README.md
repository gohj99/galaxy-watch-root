# Galaxy Watch BakaSU boot builder

**中文文档：[完整 root 教程](docs/ROOT_zh-CN.md) · [构建、签名、Actions 与多型号适配](docs/MAINTAINERS_zh-CN.md)**

当前实测：**Galaxy Watch 7 SM-L315F / L315FXXS3BZF4**，通过 **NetOdin 无线下载模式，完整 AP 只替换 boot** 成功获取 BakaSU root。Watch 4 / 5 / 6 / 8 是适配目标，尚未受支持。完整 AP 可能清除数据。

This repository contains a build framework for Samsung Galaxy Watch kernels. Its intended flow checks Samsung Open Source entries, merges the common kernel and model DTS/update archives, applies a pinned BakaSU commit, compiles `Image`, replaces the kernel payload in a known-good boot template, signs the result with your AVB key, and publishes exactly one Release asset: the signed boot image. Build manifests stay in the Actions artifact. **The public GitHub Actions flow is not yet verified end to end**; source merging, module ABI checks, and publication gates still require integration work described in the maintainer guide.

The pipeline does not build or publish an Odin AP/BL/CP/CSC package. It also does not claim that a mathematically valid local AVB signature is accepted by Samsung's boot chain. The watch must be unlocked, the boot template must match the device family, and the image must be tested on hardware.

## Important input boundary

Samsung Open Source downloads are source releases, not flashable AP packages. Kernel `Image` output is not a complete `boot.img`. Boot headers and AVB metadata can be generated from known parameters, but source availability alone does not establish a Samsung-compatible boot layout. This implementation uses a known-good boot template for each validated configuration. The `SM-L315F` entry records the SHA-256 of the hardware-tested image:

```text
153400e7c782a71836a63d4c5bb9ab14ead163fedf2036546e170bbb8bd7c3f0
```

Keep that template outside Git history and expose the verified signed boot through its model-specific Release asset or another immutable HTTPS URL. The private AVB key must be stored only as the `AVB_PRIVATE_KEY_B64` Actions secret.

The template does not have to come from a complete firmware package. It can be extracted once from the matching AP archive, or dumped from the matching device's `boot` partition while the device is already rooted. Reusing a template is reasonable only while its boot header, kernel KMI, Samsung tail, partition size, and boot-chain behavior remain compatible. A synthetic `mkbootimg` image needs independent layout and hardware validation. Once the template is available, builds do not need a full firmware package; the tested NetOdin installation path separately uses a matching full AP locally.

The Samsung site asks the downloader to accept a legal agreement. `scripts/discover_samsung.py` only reads the search table and never submits that agreement. After accepting the terms yourself, put the resulting archive URLs in the device configuration or pass them to `workflow_dispatch`.

## Current SM-L315F configuration

`devices/sm-l315f/device.json` is based on the working Watch 7 build in the parent workspace:

- Samsung source search: `SM-L315`
- Kernel: `6.1.134-android14-11`, `s5e5535`, `fresh7ulxx`
- BakaSU: commit `548d1dda060ca198823d8808804d01f5209ef4a9`
- Public stock GKI certificate: `devices/sm-l315f/stock-gki.pem`
- Reproducible kernel configuration: `devices/sm-l315f/kernel.config`

Source archive URLs and the boot template URL are intentionally empty. This prevents a scheduled job from compiling or publishing before inputs are configured. The scheduled check also stops when Samsung's first matching upload ID differs from the pinned configuration. Search-table order and upload ID are not firmware version chronology; inspect the actual version and compatibility before changing inputs.

## First setup

Read the [maintainer prerequisites](docs/MAINTAINERS_zh-CN.md#7-当前-workflow-做到了什么) before enabling publication. These are configuration steps, not a claim that the framework is production ready:

1. Make the known-good signed boot available at an immutable URL (for example, its verified model-specific Release asset), and set `devices/sm-l315f/device.json:base_boot.url` to that URL. Keep the recorded SHA-256 unchanged for that exact file.
2. Accept Samsung's source download terms in a browser and add the common kernel, model DTS, and update archive URLs to `source_archives`. The discovery script records matching uploads; it does not establish their version order, submit the agreement, or invent download URLs.
3. Create the repository secret `AVB_PRIVATE_KEY_B64` from the base64-encoded contents of your AVB private PEM. Never commit `sign/gw7-avb-rsa4096.pem` or any other private key.
4. Run **Discover and build watch boot images** with `workflow_dispatch`. A successful run creates a tag such as `galaxy-watch7-SM-L315F-<Image-hash>` and uploads exactly one Release asset: the signed boot image. Build manifests remain only in the Actions artifact.

The scheduled job is configured for daily UTC 02:17 (10:17 in Singapore/China), with `sm-l315f` as the only scheduled device. It first records the Samsung search result as an artifact. It requires configured source/template inputs, the signing secret, and accepted discovery state. It does not automatically adopt every new source release or the latest BakaSU commit. The current release step publishes directly if reached, so add and verify publication gates before unattended use.

## Adding Watch 4/5/6/8

Create `devices/<id>/device.json`, `kernel.config`, and the appropriate public module certificate where required. Set the exact Samsung source archives, boot-template hash and URL, kernel target variables, and BakaSU configuration overrides. The current boot packer supports only its checked header-v4, zero-ramdisk, zero-GKI-signature layout; other generations may need different packaging. The workflow accepts a device name through `workflow_dispatch`; this does not establish compatibility, hardware validation, or a multi-device daily matrix.

## Local checks

The boot-only packaging step can be tested without a compiler:

```bash
python3 scripts/build_boot.py \
  --base /path/to/boot-template.img \
  --kernel /path/to/Image \
  --avbtool scripts/avbtool.py \
  --key /path/to/gw7-avb-rsa4096.pem \
  --output out/boot.img \
  --manifest out/boot-manifest.json
```

The build records source hashes, BakaSU commit, kernel hash, boot-template hash, AVB algorithm, and output hash. These are provenance checks; they do not replace a real boot and root test on each supported watch.

For local AP repacking, `scripts/repack_ap.py` replaces only `boot.img.lz4`, preserves stock vbmeta and all other members, and verifies the supported Samsung RBS checksum. It never flashes a device or uploads an AP. See the [installation guide](docs/ROOT_zh-CN.md#6-准备签名-boot重打包完整-ap) for the full command and data-wipe warning.

The independent repacker tests need Python 3.11+ and `lz4`:

```bash
python -m pip install lz4
python -m unittest discover -s tests -v
```

