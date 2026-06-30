# 主题缺口分析 (Phase 1)

**问题**：能否借 ui-ux-pro-max（84 styles / 192 palette product-types）扩充现有 23 套主题？
**方法**：把 skill 的 *视觉风格*（剔除纯 web 布局 pattern：Hero-Centric / Conversion-Optimized /
Data-Dense Dashboard / Bento / Social-Proof … 这些是页面结构不是审美）逐条对照 23 套主题的设计 DNA，
找**真缺口**（未被覆盖 + 在全屏视频里能渲染好 + 与 NOLAN 内容选题相关）。

> NOLAN 主题 ≠ 调色板。一套主题 = `tokens.css` 约 30 个 token（色阶 + 中英字体配对 + padding 密度 +
> 圆角性格 + rule 风格 + hero 数字 + 阴影 + **唯一一个签名装饰层**）+ `theme.json` 元数据。
> 所以 skill 的 16 色 web 调色板只是一套主题的 ~10%，且是最容易的 10%。它只能当**色彩种子**，
> 不能直接当新主题。

## 覆盖结论：23 套已经吃掉了 skill 风格谱的大部分

| skill 风格 | NOLAN 现有覆盖 |
|---|---|
| Minimalism / Swiss / Swiss 2.0 | `swiss-ikb` `monochrome-print` `dune` |
| Bauhaus | `bauhaus-bold` |
| Brutalism / Neubrutalism | `bauhaus-bold` `creative-voltage`（部分） |
| Cyberpunk / Retro-Futurism | `neon-cyber` `creative-voltage` |
| Dark Mode OLED / Modern Dark Cinema | `midnight-press` |
| Flat Design | `electric-studio` `warm-keynote` |
| Editorial Grid / Magazine | `newsroom` `paper-press` `vintage-editorial` |
| E-Ink / Paper / Vintage Analog | `monochrome-print` `kraft-paper`（部分） |
| Organic Biophilic / Nature Distilled | `forest-ink` `dune`（部分） |
| Exaggerated Minimalism / Kinetic Type | `bold-signal` + 现有 KineticHeadline block |

## 真缺口（去重后）+ 候选打分

打分维度：真缺口性 / 与 NOLAN 内容相关性 / 全屏视频可渲染性（h.264 友好）/ 与 23 套的区分度。

| 排名 | 候选 id | 来源风格 | 缺口理由（23 套均无） | 内容相关性 | 渲染风险 | 色彩种子(skill) |
|---|---|---|---|---|---|---|
| **1** | `aurora-mesh` (dark) | Aurora UI / Gradient Mesh / AI-Native | 无一套是**满画布柔和多色渐变网格**；neon-cyber 是近黑+锐利霓虹描边线，dark-botanical 是暗底+局部暖光晕——都不是弥散全场的彩色 mesh | **高**：AI / LLM 评测、生成式艺术、web3、现代 SaaS 发布、未来科技（你的主力选题） | **低**（纯 CSS 渐变）——但测**渐变 banding** 压缩风险 | NFT/Web3 `#8B5CF6/#FBBF24/#0F0F23`、Generative Art `#EC4899` |
| **2** | `liquid-glass` (dark) | Glassmorphism / Liquid Glass / Spatial | 无一套是磨砂玻璃面板；这是 skill 重点推的现代感 | 中高：现代 SaaS / AI 产品 / 高端科技 | **高**（backdrop-blur 压缩易糊 + 每帧慢）——纯渲染风险测试件 | SaaS `#2563EB`、Spatial |
| 3 ✅ | `neubrutalism` (light) | Neubrutalism | 粗黑边 + 硬实色偏移阴影 + 撞色平涂；creative-voltage/bauhaus 相邻但非纯正 | 中：大胆产品 / 设计 / 开发者工具 / 独立创作 | **极低**（硬边平色，压缩极友好） | Arcade `#DC2626/#22C55E`、Vibrant → 实际用品红 `#f5197a` |
| 4 | `hud-fui` (dark) | HUD / Sci-Fi FUI | 科幻仪表盘细发光线 + 准星刻度；blueprint/terminal/neon 相邻，区分度偏低 | 中：数据 / AI / 航天 / 安全 | 中 | Cybersecurity / Space Tech |

**排除**：Claymorphism（受众与 pastel-dream 重叠 + 软阴影风险 + 与你 AI/explainer 主力关系弱）；
Vaporwave / Y2K / Memphis / Gen-Z Chaos（小众，且部分被 sunset-zine / creative-voltage 覆盖）；
3D/Hyperrealism / Spatial / Tactile / Voice-First / Interactive-Cursor（依赖 WebGL / 交互，非线性视频范畴）。

## 去重测试（Phase 1 验收）

- **每个候选 vs 23 套**：上表「缺口理由」列逐一证明未覆盖。✅
- **候选彼此区分**：aurora=弥散柔渐变；liquid-glass=磨砂玻璃板；neubrutalism=硬边撞色；hud=细发光线刻度。四者签名装饰互不重叠。✅
- **#1 vs 最近邻**：`aurora-mesh` vs `neon-cyber`（锐利霓虹线 on 近黑 + 网格）/ `dark-botanical`（暖色局部光晕 + 编辑奢华）——色温、扩散度、签名层均不同。✅

## 建议

- **Phase 2 先造 `aurora-mesh`**：真缺口里**价值最高**（贴合你 AI/科技/生成式主力选题）且**渲染安全**，
  同时它的渐变 banding 是真实的视频压缩风险点——既出一套**可用**主题，又验证「skill 色种子 → 完整 DNA →
  渲染 → 入选打分器」这条流水线。
- `liquid-glass` 作为**纯渲染风险**的后续测试件（backdrop-blur 是否在全屏 h.264 下发糊/掉帧）。
- 不要批量把调色板灌成新主题——会变成无 DNA 的换色版，且与现有色彩空间重叠。**按缺口逐套手工造 DNA**。

## Phase 2 结果（已落地）

`aurora-mesh`（#1 候选）已端到端建好：`themes/aurora-mesh/{tokens.css,theme.json}` +
`selector.json` 条目。验收：
- **入选打分器**：`select_theme.py "AI LLM model launch..."` / `"web3 NFT generative art..."`
  两个 brief 下 `aurora-mesh` 均排 #1（可解释信号），24 套全部有 selector 条目无告警。
- **真实渲染**：用 Windows node 跑 `still.mjs`（WSL node 的 esbuild 是 win32 binary，跑不了——
  见 NOLAN runtime gotchas），用 `hook_gen.json`（纯文字 HeroStatement/ListReveal）换主题渲 4 帧。
  招牌极光网格弥散正常、与 neon-cyber/dark-botanical 区分清晰；近白正文与电光紫 accent 文字均高对比可读。
- **Banding（已测 + 已修）**：渲了 6s mp4（h264 默认 8-bit），用 ffmpeg 抽帧验证：
  1:1 正常观看渐变干净；但 6× 提亮暗部后能看到轻微 8-bit 阶梯 banding（平台二压 / 高亮显示器会放大）。
  **修法已落地**：在 `--surface-pattern` 顶层加了一层极淡 SVG fractalNoise 抖动（desaturate + alpha 0.12），
  重渲后同样 6× 提亮——阶梯 banding 消失（变成细密均匀颗粒），而 1:1 观看颗粒不可见、观感不变。

## Phase 2.2 结果（第二套 gap 主题，已落地）

`neubrutalism`（#3 候选，最便宜 + 渲染最安全）已端到端建好。验收：
- **入选打分器**：bold / indie / dev-tool / design brief 下排 #1（28 分，远超 bauhaus-bold 11）。
- **真实渲染**：hero / cards / table / bar 四块——纯白 + 点阵 + 3px 厚黑边 + 品红（fills/bars/高亮，无 glow）
  + 粗 Space Grotesk，全 accent 驱动。浅色 + 平涂 = **零 banding 风险，无需抖动**。
- **与 bauhaus-bold 区分**（最近邻）：白底 vs 暗 shell 上米白、品红 vs 原色蓝、8px 圆角 vs 0 直角、
  点阵 vs 无装饰、无舞台黑框 vs 4px 黑框、bouncy vs 利落。

**剩下的 gap**：`liquid-glass`（纯渲染风险测试件）、`hud-fui`（与 blueprint/neon 区分度偏低，优先级最低）。
