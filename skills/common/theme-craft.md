---
id: common.theme-craft
name: Theme craft
kind: craft
purpose: Create/enrich themes — token philosophy, banding, font-loader constraints, the enrich/validate workflow.
status: active
version: 1
documents:
  module: themes/selector.json
handoffs:
  - { process: flow, stage: plan, gate: A }
uses: []
evals: []
---
> Extracted from the web-video-presentation skill into `skills/common/` (shared craft). The methodology is substrate-agnostic; where it references the legacy web-page idiom (`narrations.ts` / Vite), the flow-engine equivalent is `flow.spec.json` + Remotion blocks.

# 主题创作 / 富化 / 扩充 指南 (Playbook)

面向 **创建新主题 / 富化元数据 / 缺口扩充** 这三类任务的实操手册。
配套：[`THEMES.md`](../../themes/THEMES.md)（token 契约 + 内置主题清单）、
[`THEME-GAP-ANALYSIS.md`](../../themes/THEME-GAP-ANALYSIS.md)（缺口分析方法 + 已建/待建候选）。

> 核心原则：**一套主题 = 一套独立设计 DNA，不是换色版**。约 30 个 token +
> **唯一一个签名装饰**（grid / 扫描线 / 纸纹 / 点阵 / 渐变网格 / 偏移阴影…，叠三个会打架）。

---

## A. 创建一套新主题（end-to-end）

### 1. 先确认这是真缺口（别造换色版）
- 对照现有 25 套的 DNA + ui-ux-pro-max 风格谱，证明**未被覆盖**（见 gap-analysis 方法）。
- 与**最近邻主题**逐项区分（色温 / 形状 / 签名 / 字体 / 动效至少差 3 项）。例：
  `aurora-mesh` vs `neon-cyber`/`dark-botanical`；`neubrutalism` vs `bauhaus-bold`。
- 只有调色板（16 web 色）**不够**——它只是一套主题的 ~10%，且是最容易的 10%。可当**色种子**，
  但全屏视频要重新调（更高对比、更少中间灰、accent 要扛得住 h.264）。

### 2. 建文件 `themes/<id>/`
两个文件，**无需注册代码**（`stage.mjs` 按 `theme` 字段拷 `tokens.css` → `_active-theme.css`）：

**`tokens.css`** —— 约 30 个 token，分组（照抄现有主题的结构，逐项改）：
- **palette**：`--shell / --surface / --surface-2/3 / --text / --text-2 / --text-mute / --text-faint /
  --rule / --accent / --accent-soft / --accent-glow`
- **fonts**：`--font-display-cn / --font-display-en / --font-body / --font-mono / --font-features`
  - ⚠️ **只能用 `_lab_chapter/src/index.tsx` 里已 `loadFont` 的字体**，否则渲染时回落系统字体。
    当前已加载：Archivo Black · Space Grotesk · JetBrains Mono · Instrument Serif · Manrope ·
    IBM Plex Mono · IBM Plex Sans。要用别的，**先去 index.tsx 加 `loadFont`**。
  - CJK 用 `"Noto Sans SC"` 系列做 fallback（与现有主题一致）。
- **motion**：`--dur-quick/base/slow/cinematic` + 可选 `--motion-intensity`（calm 0.6 ↔ expressive 1.3）。
- **design identity（签名旋钮）**：`--bw-1`（卡片边宽，默认 1px，粗野风调 3px）、`--r-card`
  （`var(--r-flat|sm|md|xl)` 或硬编码）、`--r-stage`、`--rule-w` + `--rule-style`、`--hero-num-*`、
  `--stage-pad-x/y`、`--card-shadow`、`--shadow-stage`、`--stage-border`。
- **decoration（唯一签名）**：`--surface-pattern` + `--surface-pattern-size/blend/opacity`
  （画在 `.stage-frame::after`，单一 `mix-blend-mode`）、可选 `--surface-vignette`。

**`theme.json`** —— 元数据：
`id` / `name` / `nameZh` / `description` / `descriptionZh` /
`mood`（数组，**必须含 `light` 或 `dark`**，validator 会查它和 selector.tone 一致）/
`bestFor`（**中文**用例数组）/ `preview`（`shell/surface/text/accent` 四个 `#rrggbb`）。
> `fonts` 和 `avoidFor` **不要手写**——由 `enrich_themes.py` 派生（见 C 节）。

### 3. accent 是唯一颜色来源
`--accent` 驱动 fills / progress bars / hero 数字 / 高亮行 / **chart 全套色阶**（heatmap/bar 通过
`color-mix(accent, surface)` 自动派生 ramp，无需 per-chart 硬编码）。所以换主题 = 换 accent，
所有组件自动一致。**浅色主题**：accent 要在白底上**作为强调文字仍可读**（正文用 `--text`）。

### 4. 进 `selector.json`
加一条（这是缺英文匹配面的补层）：
```json
"<id>": { "tone": "light|dark", "energy": "calm|medium|high", "formality": "casual|neutral|formal",
  "tags": ["英文 topic 词…"], "avoid": ["内容类型反模式…"] }
```
`tags` 是英文 topic 匹配面（`bestFor` 是中文，briefs 可能英文，两边都匹配）。`avoid` = 不该用它的内容。

### 5. 派生 + 校验
```bash
python scripts/enrich_themes.py     # 写 fonts + avoidFor 进 theme.json（幂等）
python scripts/validate_themes.py   # 必须 OK：文件齐全 / preview 合法 / 有 selector 条目 / tone↔mood 一致 / 富化最新
```

### 6. 真实渲染验收（**别只看 still 的好坏，要看组件**）
- ⚠️ **必须用 Windows node**：`/mnt/c/Program Files/nodejs/node.exe`
  （WSL node 的 esbuild 是 win32 binary，跑不了；见 NOLAN runtime gotchas）。
- 用**组件丰富**的 job 换主题渲 still，别只渲 HeroStatement（那基本只看背景）：
  - `one-map`（ArchetypeCards / WebVsBoxes / Timeline / ListReveal，**无图**）
  - `tailtrading`（StatCount hero 数字 / DataTable）
  - `transformer`（BarChart）、`tailtrading2`（Heatmap）
```bash
cd render-service/_lab_chapter
python3 -c "import json;d=json.load(open('jobs/one-map.json'));d['theme']='<id>';d['captions']=False;json.dump(d,open('_t.json','w'))"
python3 -c "import json;json.dump([{'frame':1388,'out':'cards.png'}],open('_s.json','w'))"
"/mnt/c/Program Files/nodejs/node.exe" still.mjs _t.json _s.json output/<id>_check
rm -f _t.json _s.json
```
  逐张看：正文 / accent 文字**可读性**、签名是否成立、是否和最近邻**区分清晰**。

### 7. Banding（**只有深色 + 平滑渐变主题需要**）
- 浅色 / 平涂（如 neubrutalism）：零风险，跳过。
- 深色平滑渐变（如 aurora-mesh）：渲一段 mp4，用 ffmpeg 抽帧 + **6× 提亮暗部**看阶梯：
```bash
FF=../node_modules/@ffmpeg-installer/win32-x64/ffmpeg.exe
"$FF" -y -ss 3 -i out.mp4 -vf "curves=all='0/0 0.05/0.45 0.1/0.72 0.18/1 1/1'" -frames:v 1 lift.png
```
  若有阶梯 banding：在 `--surface-pattern` **顶层**加一层极淡 SVG fractalNoise 抖动
  （desaturate + alpha ~0.12），重渲再验（1:1 不可见、6× 提亮阶梯消失）。参考 aurora-mesh 的写法。

### 8. 收尾
- `THEMES.md`：深/浅色表加一行；更新「N 套主题」计数（两处）。
- `IMPLEMENTATION_STATUS.md`：加一条（changed / 用法 / benefit）。
- 清理临时 job / sample 文件；`output/` 是 gitignore 的。

---

## B. 缺口扩充（决定造哪一套）
方法见 [`THEME-GAP-ANALYSIS.md`](../../themes/THEME-GAP-ANALYSIS.md)。要点：
- 剔除 ui-ux-pro-max 里的**纯 web 布局 pattern**（Hero-Centric / Dashboard / Conversion… 不是审美）。
- 候选打分维度：**真缺口性 × 内容相关性 × 全屏视频可渲染性（h.264 友好）× 与现有 25 套区分度**。
- 排序示例：`aurora-mesh`（价值最高+安全）> `neubrutalism`（最便宜+零 banding）>
  `liquid-glass`（纯渲染风险测试件）> `hud-fui`（与 blueprint/neon 区分度低，优先级最低）。
- **不要批量把调色板灌成新主题** —— 会变成无 DNA 换色版且与现有色彩空间重叠。按缺口逐套手工造。

---

## C. 富化现有主题（metadata）
- `enrich_themes.py` 给每套 `theme.json` 派生 `fonts`（从 `tokens.css` 解析主字体）+ `avoidFor`
  （从 `selector.json` 提升）。**幂等**，加/改主题或改字体/avoid 后重跑。
- 加了新派生字段要改 schema 时：改 `enrich_themes.py` 的 `FONT_KEYS` / 逻辑 + `validate_themes.py` 的检查。
- **已主动不做**：per-theme chart-pairing hints —— 与「数据形状→chart 类型」选择器重叠且偏推测（YAGNI）。

---

## 语言约定（沿用，别全改英文）
按层分，**别在同一文件里半中半英**：
| 层 | 语言 |
|---|---|
| 代码 / id / key / enum / `tags` / `mood` | **英文** |
| 产品成对字段 `name`+`nameZh` / `description`+`descriptionZh` | **双语** |
| 受众自由文本 `bestFor` / 叙述脚本 | **中文**（视频受众是中文；匹配靠英文 `tags`） |
| 引擎工程文档（`IMPLEMENTATION_STATUS` / 代码注释） | **英文** |
| 本 skill 的 agent 文档（`the (retired) web-presentation SKILL` / `references/*`，含本文件） | **中文**，逐文件一致 |
