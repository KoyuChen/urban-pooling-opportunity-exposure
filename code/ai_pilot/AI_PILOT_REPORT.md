# 城市共乘隐私粗化 AI Pilot：结果、主规格与 Go/No-Go

**日期：** 2026-08-25

**当前主规格：** 22-feature no-geography-equality weak-MIL。

**诊断规格：** 原 28-feature weak-MIL，仅用于展示地理同一性特征造成的循环性。

**研究边界：** 完全 human-experiment-free；只使用公开行政数据、公开 ACS、离线合成真值与约束优化。

**允许使用的概念：** compatibility homophily、opportunity exposure、mobility silo。
**禁止声称：** 观察到真实 co-rider、个体收入、偏好性 homophily、持续社会影响或 echo chamber。

## 结论先行

**方法 pilot 已跑通，主模型已经通过已知真值合成 gate；Chicago 实证仍未过关。**
在锁定参数且不使用 holdout 调参的端到端实验中，22-feature
no-geography-equality weak-MIL 相对透明规则将 held-out node Brier 从
0.06048 降至 **0.00595（改善 90.2%）**。候选图召回全部 80 条隐藏真边；
在 160 个 matched endpoint 上，主模型的真边 MRR 为 **0.941**、Top-1 为
**90.0%**、Top-3 为 **98.1%**。

主模型得到的同收入 bin 区间在两档预先指定的 score-retention 下均覆盖真值
0.5625：

- `\(\rho=.90\)`：**[0.2875, 0.7625]**，相对未裁剪区间缩窄 34.5%；
- `\(\rho=.95\)`：**[0.3875, 0.6875]**，缩窄 58.6%。

隐藏真实 packing 的得分为主模型最优 packing 的 0.99650，因此在两档
`\(\rho\)` 下都满足 score floor。这个结果支持“以区间传播结构不确定性”的方法
路线，但不是 Chicago 乘客的实证发现。

原 28-feature 模型的 node Brier 更低（0.00513），却必须降为
**diagnostic-only**。循环性审计发现，在用于 bounds 的 560 条 held-out
matched-node 候选边中，`pickup_tract_same` 和 `dropoff_tract_same` 都与
`same_income_bin` 完全一致（560/560）；两个 community-area equality 指示则
恒为 1。原模型的 95% 区间 [0.6125, 0.7750] 因而机械性偏窄并排除真值。它只能
作为一个有价值的 negative diagnostic，不能作为主科学规格。

当前环境仍无法取得 City of Chicago 的完整日候选池。现有 1/256 `trip_id`
前缀样本几乎必然漏掉另一条组内订单，只能做 schema/mechanics check。
**最终判断：方法研发 GO；KDD AI4Sciences 的 Chicago 实证承诺 HOLD，等待完整日
数据与独立 holdout。**

## 1. 实际做出的 AI

公开表提供每个 trip 的 `shared_trip_match` 和 `trips_pooled`，却删除 pooled
group ID。Pilot 把这个缺失对象表示为潜在图：

```text
公开 trip 节点
  → 时间 / OD / 方向 / 行程约束生成稀疏候选边
  → noisy-OR 多实例弱监督（只有 node match 标签）
  → 每条候选边的兼容性分数
  → exact-cover set-packing
  → SES 同组率与收入差异的最小值 / 最大值
```

这不是普通的 `shared_trip_match` 分类器。AI 的科学用途是：在隐私粗化删除
group ID 后，把不可直接观察的 opportunity-exposure estimand 转化为可审计的
候选集合、结构约束与模型敏感性区间，而不是输出一张被当作事实的最高分配对图。

### 主规格与诊断规格

| 规格 | 弱监督特征 | 用途 |
|---|---|---|
| **22-feature no-geography-equality weak-MIL** | 连续时间、起终点距离、方向、行程时长/里程相容性及其非线性项；不含同 area/tract 指示 | **Primary / production specification** |
| 28-feature full weak-MIL | 上述 22 项，加四个同 area/tract 指示与 `same_area_both`、`same_tract_both` | **Diagnostic-only：循环性反例** |
| Transparent rule | 固定的公开兼容性打分，仅校准截距与尺度 | Comparator；不作为同收入 bounds 的优选科学规格 |

原 transparent rule 仍含预设的同 area/tract 加分项，因此其 score-retention
区间也只作 diagnostic comparator；只有 node Brier 与 ranking 可作为不变基线。

主模型明确删除以下六项：

```text
pickup_area_same
dropoff_area_same
pickup_tract_same
dropoff_tract_same
same_area_both
same_tract_both
```

候选图仍可使用公开时间和坐标距离来定义物理上可能的 opportunity set；这与把
tract equality 直接放进“同收入 bin”打分不是一回事。`shared_trip_match` 只作
node-level 训练目标；`trips_pooled`、fare、total、ACS income、隐藏 pair ID 和
任何 endpoint label 都不进入 edge feature。二人服务链的“一节点一边”一致性由
后续二元 set-packing 强制执行。

## 2. 为什么必须删除地理同一性特征

隐藏真值只在训练完成后用于 audit，但合成生成器把 pickup tract 构造为 corridor
代码加 income bin，并把 destination bin 设为相同变量的确定性变换。因此，在
held-out matched-node bound graph 上：

| 特征 | 特征为 1 | 与 `same_income_bin` 的关系 |
|---|---:|---:|
| `pickup_community_area_same` | 560/560 | 恒为 1，无 pair-level 区分力 |
| `dropoff_community_area_same` | 560/560 | 恒为 1，无 pair-level 区分力 |
| `pickup_tract_same` | 136/560 | 与同收入边完全一致，agreement 560/560 |
| `dropoff_tract_same` | 136/560 | 与同收入边完全一致，agreement 560/560 |

所以，28-feature 模型用 tract equality 约束同收入区间时存在实质循环性。更窄的
区间不是更强的科学识别，而是 target-aligned feature map 的机械结果。

22-feature 消融消除了这条直接通路，但**没有消除所有 geography–SES 相关性**：
锁定生成器还用 income-specific coordinate offsets 生成连续坐标，故 pickup 和
dropoff 距离仍可能代理 SES。主模型的 score-retention 区间必须称为
model-dependent sensitivity regions；未裁剪候选图 [0.050, 0.775] 是 score-free
参照。未来还需在 SES 与几何位置正交或置换的生成机制上重复验证。

## 3. 锁定的端到端已知真值实验

`integration/DESIGN_LOCK.json` 在第一次 holdout 运行前固定：两天、每天 80 个
隐藏真 pair 和 80 个 unmatched authorized trip、Chicago 风格坐标、15 分钟
时间粗化；第一天训练，第二天一次性评估。隐藏 pair ID 与收入 bin 单独保存，
从未进入候选生成或模型拟合。去地理同一性消融保持原数据、split、候选配置、
正则化和优化器不变，并逐行验证候选图完全相同：480 个节点、2,640 条候选边，
其中 held-out 1,320 条；bounds 使用的 matched-node 子图有 560 条边。

### 3.1 Node 与隐藏真边验证

| 指标 | 透明规则 | 28-feature full MIL（诊断） | **22-feature no-equality MIL（主）** |
|---|---:|---:|---:|
| Held-out node Brier ↓ | 0.060481 | **0.005131** | **0.005947** |
| 相对规则 Brier 改善 | — | 91.5% | **90.2%** |
| Held-out log loss ↓ | 0.254430 | 0.042059 | **0.047319** |
| Held-out ECE ↓ | 0.047010 | 0.039107 | **0.043804** |
| ROC AUC | 0.960 | 1.000 | **1.000** |
| Average precision | 0.985 | 1.000 | **1.000** |
| 真边 MRR ↑ | 0.7815 | 0.7753 | **0.9405** |
| 真边 Top-1 ↑ | 67.5% | 64.4% | **90.0%** |
| 真边 Top-3 ↑ | 85.6% | 90.0% | **98.1%** |

候选图对 held-out 隐藏真边的召回为 **80/80 = 100%**；排序指标以 160 个
matched endpoint 为单位，并以真边已进入候选图为条件。主模型的 node Brier
略逊于 28-feature 诊断模型，却大幅改善 pair ranking；这说明 full model 的
额外 equality features 主要帮助拟合 node label，并未提供可信的 pair identity。

### 3.2 Set-packing bounds

Holdout 隐藏同收入 bin 配对率为 0.5625：

| 候选集合限制 | 同收入 bin 区间 | 宽度 | 相对未裁剪缩小 | 覆盖真值 | 真实 packing 达到 score floor |
|---|---:|---:|---:|---:|---:|
| 未裁剪候选图 | [0.0500, 0.7750] | 0.7250 | — | 是 | 不适用 |
| Rule `\(\rho=.90\)` | [0.3375, 0.7750] | 0.4375 | 39.7% | 是 | 是 |
| Rule `\(\rho=.95\)` | [0.4375, 0.7500] | 0.3125 | 56.9% | 是 | 否 |
| Full MIL `\(\rho=.90\)`（诊断） | [0.5250, 0.7750] | 0.2500 | 65.5% | 是 | 是 |
| Full MIL `\(\rho=.95\)`（诊断） | [0.6125, 0.7750] | 0.1625 | 77.6% | **否** | **否** |
| **No-equality MIL `\(\rho=.90\)`（主）** | **[0.2875, 0.7625]** | **0.4750** | **34.5%** | **是** | **是** |
| **No-equality MIL `\(\rho=.95\)`（主）** | **[0.3875, 0.6875]** | **0.3000** | **58.6%** | **是** | **是** |

主模型的隐藏真实 packing score ratio 为 **0.9964999**，所以两档 score floor
都保留真实 packing。删除循环特征后 bounds 变宽是预期的诚实代价；它同时修复
了 full MIL 在 `\(\rho=.95\)` 下不覆盖真值的问题。`\(\rho\)`-retention 区间不是
频率学置信区间，也不能在真实数据上根据想要的结论反向选择阈值。

## 4. 求解器的独立覆盖检查

另一个不依赖弱监督训练的 implementation validation 使用 20 个随机种子、
每次 30 个已知真 pair。随着公开时间从 1 分钟粗化到 30 分钟，候选边/真边比
从 1.04 升至 2.11，未裁剪同 SES bin 界宽从 0.003 升至 0.150。所有设置中：

- 真边候选召回：100%；
- 未裁剪 bounds 覆盖：100%；
- 95% 兼容性分数限制下覆盖：100%；
- 15 分钟时界宽 0.073 → 0.020，缩小 72.7%；
- 30 分钟时界宽 0.150 → 0.027，缩小 82.2%。

这是求解与 coverage 逻辑的单元/仿真检查，不是对真实 Chicago 匹配器的验证。

## 5. 真实 Chicago mechanics check

现有前缀样本包含 3,048 个 authorized trip。候选生成后只有 151 条边、246 个
节点有至少一条候选边，支持率仅 8.1%。使用最后 14 天作 holdout：

- 854 个 authorized test node；
- 只有 93 个 candidate-supported test node；
- rule Brier 0.15525；
- 当时运行的 **28-feature diagnostic model** Brier 为 0.15777，比规则差 1.6%；
- 在全部 854 个 test node 上两者近乎相同。

这既不是主 22-feature 模型的真实验证，也不能解释为完整市场中的失败：前缀
抽样先机械性破坏了潜在组结构。它的唯一结论是代码能处理真实 schema。完整日
no-equality primary model、真实 pair ranking 与真实 SES opportunity bounds
全部仍是 **unresolved**；公开数据本身也不提供真实 pair ID，因而后两者只能用
外部验证或区间敏感性处理。

## 6. 更新后的 Go/No-Go

| 门槛 | 22-feature 主规格结果 | 状态 |
|---|---|---|
| Held-out node Brier 至少改善 10% | 合成相对规则改善 90.2% | **PASS（仅合成）** |
| 候选图保留至少 95% 真边 | 80/80 = 100% | **PASS（仅合成）** |
| 隐藏真边排序可用 | MRR 0.941；Top-1 90.0%；Top-3 98.1% | **PASS（仅合成）** |
| 界宽至少缩小 25% | `\(\rho=.90\)` 缩小 34.5%；`\(\rho=.95\)` 缩小 58.6% | **PASS（仅合成）** |
| 区间覆盖已知真值 | 两档主规格均覆盖 | **PASS（仅合成）** |
| 真实 packing 达到 score floor | score ratio 0.9965；两档均达到 | **PASS（仅合成）** |
| exact geography-equality feature audit | 六项全部从主模型删除 | **PASS** |
| 连续距离仍代理 SES 的敏感性 | 尚需正交/置换 DGP | **OPEN** |
| 完整日真实候选池 | API 被当前环境阻断 | **BLOCKED** |
| 完整日主模型 held-out 预测 | 未运行 | **NOT YET** |
| 真实 SES opportunity bounds | 未运行 | **NOT YET** |
| Chicago 政策因果结果 | 两日 pilot 不足以识别 | **NOT YET** |

总判断保持为：**方法研发 GO；真实 Chicago 科学结论 HOLD。** 28-feature 模型
不再参与主规格 Go/No-Go，只保留为循环性诊断。

## 7. 与 AI 和创新度的关系

如果只做 node match prediction，项目的 AI 创新很低。当前更可信的贡献组合是：

1. 隐私观测算子删除 group ID 后的 latent structural inference；
2. 无 edge label 的 weak node-label edge hazard；
3. exact-cover set-packing，排除相互冲突的服务链；
4. 不输出单一猜测图，而把结构不确定性传播到 SES opportunity bounds；
5. 显式做 target-aligned geography feature audit，并把失败的 28-feature 模型
   保留为 diagnostic negative result；
6. 最终将 bounds 传播到 Chicago 政策 event-study，而不是回归一个 imputed graph。

据当前 pilot，**方法组合创新度约 7.5/10；真实科学证据成熟度约 5/10。**
no-equality 消融提高了内部可信度，但没有替代完整日数据、外部校准或政策识别。

## 8. 下一步必须按这个顺序

1. 在可访问 `data.cityofchicago.org` 的环境运行完整日抓取器，核对服务器
   `count(*)`、SHA-256、重复 ID、地理缺失和 pooling 编码。
2. 至少取多个非节假日训练日和独立 holdout 日；不要用单个 pre/post 日承载
   论文结果。
3. **正式主模型只使用 22-feature no-equality feature map。** 28-feature full
   model 和原透明规则只作 diagnostic comparator。
4. ACS income 只在 edge scoring 完成后连接，用作 neighborhood-level outcome
   proxy；任何 ACS income、income bin 或 tract-equality 指示都不得进入主 scorer。
5. 新增 SES 与几何位置正交、coordinate-offset 关闭和 SES permutation 三种
   negative-control DGP，确认主区间不是由连续距离机械决定。
6. 主分析报告未裁剪、`\(\rho=.90\)` 与 `\(\rho=.95\)` 全部区间，并对
   15/30/45 分钟、degree cap 16/32/64 和 OD 半径做预注册式敏感性。
7. 主分析限定 `shared_trip_match=true & trips_pooled=2`，排除日界附近服务链；
   3 人以上 hyperedge 作为第二阶段扩展。
8. 若完整日 held-out Brier 未改善 10%，或主模型不能稳定缩界并保持合成覆盖，
   停止 AI4Sciences 路线，改成透明规则的 urban computing / partial-ID 论文。

## 9. 复现命令

从仓库中的 `code/ai_pilot` 目录运行。所有示例把新输出写入 `/tmp`，不会覆盖
仓库内锁定结果。

### 28-feature diagnostic-only benchmark

```bash
python integration/run_integration_benchmark.py \
  --output-dir /tmp/urban_pooling_full_mil_diagnostic
```

### 22-feature no-geography-equality primary benchmark

该命令复用锁定 synthetic files、split 与 candidate graph，并在拟合后核验候选图
逐行一致：

```bash
python integration/ablations/no_geography_equality_20260825/run_ablation.py \
  --output-dir /tmp/urban_pooling_no_equality_primary
```

### Revised publication figure

```bash
python integration/ablations/no_geography_equality_20260825/make_revised_benchmark_figure.py \
  --output /tmp/benchmark_summary_revised.png
```

## 10. 当前允许写进摘要的版本

> We develop weakly supervised structured inference for privacy-coarsened
> ride-pooling records, replacing a single imputed co-rider graph with
> compatibility-constrained bounds on neighborhood-level opportunity exposure.
> A geography-equality ablation is designated as the primary specification;
> target-aligned tract indicators are retained only as a diagnostic of
> model-induced overconfidence.

目前不能写：

> We recover who rode together and show that AI ride pooling creates urban
> echo chambers.

前者是已实现但仍仅由 synthetic known-truth experiment 验证的方法方向；后者超出
公开数据的可识别范围。
