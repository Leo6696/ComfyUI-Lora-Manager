# ComfyUI LoRA Manager Enhanced / 增强版

> A community enhancement fork focused on metadata recovery, safe Civitai filename restoration, and dependable management of large local model libraries.
>
> 面向大型本地模型库的社区增强分支，重点解决元数据恢复、Civitai 作者文件名安全还原，以及批量管理过程缺少反馈的问题。

[中文说明](#中文说明) · [English](#english) · [完整增量记录](CUSTOM_CHANGES.md)

## 原项目与署名 / Upstream and credits

本项目是 [willmiao/ComfyUI-Lora-Manager](https://github.com/willmiao/ComfyUI-Lora-Manager) 的增强分支。LoRA Manager 原有的浏览、下载、配方、Checkpoint 管理、工作流集成等能力均来自原项目；请前往以下链接查看原版的完整功能、教程、Wiki、发行版和作者信息：

This repository is an enhancement fork of [willmiao/ComfyUI-Lora-Manager](https://github.com/willmiao/ComfyUI-Lora-Manager). Browsing, downloading, recipes, checkpoint management, workflow integration, and the other core LoRA Manager features come from the upstream project. Refer to the links below for the full original feature set, tutorials, releases, and author information.

- [原项目 / Original project](https://github.com/willmiao/ComfyUI-Lora-Manager)
- [原版 README / Upstream README](https://github.com/willmiao/ComfyUI-Lora-Manager#readme)
- [Wiki](https://github.com/willmiao/ComfyUI-Lora-Manager/wiki)
- [Releases](https://github.com/willmiao/ComfyUI-Lora-Manager/releases)

本 README 只介绍此 fork 相对原版增加或修改的内容。

This README documents only the additions and behavioral changes provided by this fork.

---

## 中文说明

### 这个增强版解决什么问题

当本地有大量 LoRA、Checkpoint 和 Embedding 时，原版的一些边缘行为会变成明显痛点：Civitai 查询失败一次后持续跳过、手动改名或移动后缓存与 sidecar 失联、批量操作等待时间长却看不到具体进度，以及缺少可信的批量文件名整理方式。

这个分支针对这些问题增加了以下能力。

### 1. 可恢复、可重试的 Civitai 元数据刷新

- 新增“重试跳过项”，只重新处理此前标记为未找到的模型，不必重扫整个模型库。
- 强制重试会绕过旧的 `not found` 负缓存，失败一次不会永久跳过。
- sidecar 缺失时复用缓存 SHA；必要时重新计算 SHA，再尝试恢复模型身份。
- Hugging Face 来源的模型只要 SHA 能被 Civitai 识别，也可以补齐 Civitai 元数据。
- 修复响应缺少 `sha256` 字段时直接报错的问题。
- 核心元数据先落盘，再处理可选预览资源；预览 CDN 故障不会丢掉已经查到的元数据。
- 预览阶段采用 15 秒总时限，失败后跳过预览并继续，不再因为失效视频链接等待数分钟。

### 2. 基于精确 SHA 的安全智能改名

适用于 LoRA、Checkpoint 和 Embedding。

- 优先恢复 Civitai 当前页面显示的作者上传文件名，而不是根据模型标题或精度标签自行拼名字。
- 必须先通过 SHA256 精确确认文件身份，避免不同精度、架构或量化版本串名。
- 同一 SHA 对应多个上传名时，根据当前文件名的关键词覆盖度选择候选。
- 检查 `I2V/T2V`、`FP8/BF16/FP16`、`Q4/Q6/Q8`、rank 等技术关键词冲突。
- `lora.safetensors` 等无描述性的通用上传名不会覆盖现有名称。
- 目标文件已存在、候选不唯一或批次内重名时不会覆盖文件。
- 支持全库、多选和单模型入口；执行前显示改名预览。
- 模型、预览和 `.metadata.json` sidecar 一起迁移，并支持撤销本批次改名。

### 3. 外部改名或移动后的自动修复

- 扫描时通过唯一 SHA 识别被手动改名或移动的模型。
- 将旧缓存记录重新关联到新路径，减少重复下载和重复查询。
- 安全合并同 SHA 的孤立 sidecar，尽量保留标签、备注、收藏、触发词和 Civitai 身份。
- 目标 sidecar 属于不同 SHA 时拒绝合并，避免污染另一个模型。

### 4. 更清楚的批量操作进度

- 内置“移动到文件夹”显示当前项目、已完成数和总数。
- 智能改名显示 `已完成/总数 · 已用时间`，不再只有不确定状态的转圈动画。
- 智能改名查询最多使用 3 路受控并发，并合并重复请求、短期缓存查询结果。
- 任务进度带独立 ID，多页面同时操作不会互相覆盖。

### 5. 多存储目录区分

- 侧栏平铺模式显示“存储 / 模型类别”，例如 `AI2 / diffusion_models: Krea 2`。
- 树形模式使用“存储 → 模型类别 → 目录”结构，支持 Windows 盘符、WSL 挂载以及 `/ai`、`/ai2`、`/ai3` 服务器存储。
- 主模型目录即使通过软链接访问，也会解析为实际存储标签；相同目录名不会跨根目录合并。
- 旧版本保存的目录选择会根据原相对路径和模型根目录自动迁移。

### 安装

新安装：

```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/Leo6696/ComfyUI-Lora-Manager.git comfyui-lora-manager
cd comfyui-lora-manager
python -m pip install -r requirements.txt
```

仓库默认分支 `main` 就是增强版，不需要额外执行 `git switch`。安装后重启 ComfyUI，通过菜单打开 LoRA Manager，或访问：

```text
http://localhost:8188/loras
```

更新：

```bash
cd /path/to/ComfyUI/custom_nodes/comfyui-lora-manager
git pull --ff-only origin main
```

如需使用 Civitai 查询和下载，请在 LoRA Manager 设置中填写自己的 Civitai API Key。

### 使用前注意

- 智能改名默认先生成预览，不会直接修改文件；建议确认计划后再应用。
- 已有工作流可能引用旧文件名，改名后相应节点可能需要重新选择模型。
- 不覆盖已存在的目标文件，不修改 ComfyUI 核心文件。
- 保持与原版数据库、metadata sidecar 和主要页面结构兼容。
- 更完整的规则、接口与验证记录见 [CUSTOM_CHANGES.md](CUSTOM_CHANGES.md)。

---

## English

### What this fork improves

Large LoRA, checkpoint, and embedding libraries expose a few painful edge cases: a transient Civitai miss can remain permanently skipped, manual moves can detach cached metadata from the actual file, long bulk operations provide too little feedback, and restoring original upload filenames safely is difficult.

This fork adds the following behavior on top of the upstream project.

### 1. Recoverable Civitai metadata refresh

- Retry only models previously skipped as not found without rescanning the whole library.
- Bypass stale negative cache entries during an explicit retry.
- Reuse a cached SHA, or recalculate it when needed, to rebuild missing sidecars and model identity.
- Enrich Hugging Face models with Civitai metadata whenever their SHA is recognized.
- Handle metadata responses that omit the `sha256` field.
- Persist core metadata before optional preview downloads.
- Cap the complete preview stage at 15 seconds; a broken image or video CDN no longer blocks a successful metadata refresh for several minutes.

### 2. SHA-verified smart rename

Available for LoRAs, checkpoints, and embeddings.

- Prefer the exact filename currently published by the Civitai author instead of inventing a name from model labels.
- Require exact SHA256 identity before suggesting a rename.
- Resolve multiple filenames for one SHA using keyword coverage from the current local name.
- Reject technical contradictions involving `I2V/T2V`, `FP8/BF16/FP16`, `Q4/Q6/Q8`, rank, and similar qualifiers.
- Ignore generic upload names such as `lora.safetensors`.
- Never overwrite an occupied target or apply an ambiguous/colliding plan.
- Provide library-wide, selected-item, and per-card actions with a preview-first flow.
- Move the model, preview, and `.metadata.json` sidecar together, with batch undo support.

### 3. Automatic repair after external moves or renames

- Recognize externally moved or renamed models by unique SHA during scanning.
- Relink the previous cache identity to the new path.
- Merge orphaned sidecar metadata only when SHA identity is compatible.
- Preserve tags, notes, favorites, trigger words, and Civitai identity where possible.

### 4. Actionable progress for bulk operations

- Show current item, completed count, and total count during folder moves.
- Show `completed/total · elapsed time` during smart rename jobs.
- Use up to three controlled lookup workers, request coalescing, and short-lived result caches.
- Scope WebSocket progress by job ID so concurrent pages do not overwrite each other.

### 5. Storage-aware folder navigation

- Show the storage and model category in list view, for example `AI2 / diffusion_models: Krea 2`.
- Use a “storage → model category → folder” tree for Windows drives, WSL mounts, and server roots such as `/ai`, `/ai2`, and `/ai3`.
- Resolve symlinked primary model roots to their actual storage label while preserving the original path for model operations.
- Keep identical relative folder names from separate roots distinct and migrate saved selections by relative path and root.

### 6. Storage-aware download and move targets

- Download, move, and recipe-import selectors list ComfyUI-registered roots as `AI / loras`, `AI2 / loras`, and `AI3 / loras` instead of ambiguous raw paths.
- Selecting a root always keeps the exact registered path for file operations; storage labels are display-only.
- The chosen target is remembered separately for download and move operations.
- With automatic organization enabled, the plugin creates its subfolder beneath the selected root; it no longer silently sends the file to another default disk.

### Installation

Fresh installation:

```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/Leo6696/ComfyUI-Lora-Manager.git comfyui-lora-manager
cd comfyui-lora-manager
python -m pip install -r requirements.txt
```

The repository's default `main` branch contains the enhanced version, so no extra `git switch` is required. Restart ComfyUI, then open LoRA Manager from the menu or visit:

```text
http://localhost:8188/loras
```

Update later with:

```bash
cd /path/to/ComfyUI/custom_nodes/comfyui-lora-manager
git pull --ff-only origin main
```

Configure your own Civitai API key in LoRA Manager settings if you use Civitai metadata or download features.

### Safety and compatibility

- Smart rename is preview-first; review the plan before applying it.
- Existing workflows may still reference old filenames and can require model reselection after a rename.
- Occupied targets are never overwritten, and ComfyUI core files are not modified.
- Existing LoRA Manager databases, metadata sidecars, and primary page structure remain compatible.
- See [CUSTOM_CHANGES.md](CUSTOM_CHANGES.md) for detailed matching rules, APIs, compatibility notes, and validation results.

## Validation

The enhancement set has been validated with the backend, native frontend, Vue widget, syntax, metadata recovery, rename collision, undo, external move repair, and real failed-preview scenarios. See [CUSTOM_CHANGES.md](CUSTOM_CHANGES.md) for the recorded results.
