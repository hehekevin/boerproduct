# Methods 与 Experiments 章节结构模板

使用说明：按本模板顺序成稿。每个区块给出写作内容、惯例句式与要素清单。占位符用尖括号表示，数值一律取自事实底稿，缺口写 `[TODO]`。

## 2.X Data（数据与数据集）

写作内容：数据集名称与版本、来源与获取方式、规模（样本数、类别数、字段）、预处理步骤（清洗、归一化、分词、增广等，含参数）、划分比例与随机方式、训练/验证/测试各子集用途。

惯例句式（过去时、被动为主）：
- Experiments were conducted on <数据集名> version <版本>, which contains <规模>.
- The dataset was split into training, validation, and test sets with a ratio of <比例> using <随机方式>.
- All samples were preprocessed by <步骤> with <参数>.

要素自查：名称、版本、规模、来源、预处理及参数、划分比例、随机方式、子集用途，逐项给出或标 TODO。

## 2.Y Model and Method（模型与方法）

写作内容：方法整体思路（一两句）、模型结构与关键组件、符号定义、核心公式及每个符号的含义与单位、关键设计选择及理由（材料中有依据才写）。

惯例句式：
- We denote <符号> as <含义>.
- The model consists of <组件>，each of which <功能>.
- <公式>，where <符号> denotes <含义> and <符号> is measured in <单位>.

要素自查：每个符号首次出现即定义；公式中符号与正文一致；单位写清；无未定义记号。

## 2.Z Experimental Procedure（实验流程）

写作内容：训练、验证、测试三段分开描述。每步写清输入、操作、输出与判断条件（如早停条件、模型选择标准）。多步流程按执行顺序逐步写，不把多步压成一句。

惯例句式：
- The model was trained for <N> epochs with batch size <B> using the <优化器> optimizer with an initial learning rate of <lr>.
- Training was stopped early if the validation loss did not improve for <k> consecutive epochs.
- The checkpoint with the highest validation <指标> was selected for testing.

要素自查：训练超参齐全（优化器、学习率及调度、batch size、epoch 数、正则化）；验证与模型选择标准明确；测试流程独立成段；无条件串台（训练条件不混入评测段）。

## 2.W Experimental Setup（实验设置）

写作内容：硬件（GPU 型号与数量、CPU、内存）、软件环境（操作系统、框架及版本、关键依赖及版本、CUDA 版本）、随机种子、重复次数、单次运行耗时（材料有则写）。

惯例句式：
- All experiments were run on <数量> x <GPU 型号> GPUs.
- We used <框架> version <版本> with CUDA <版本>.
- Each configuration was repeated <N> times with random seeds <种子列表>.

要素自查：对照 reproducibility-checklist.md 逐项核验。

## 2.V Evaluation Metrics（评估指标与统计方式）

写作内容：每个指标的名称、计算定义（公式或文字，含平均方式）、使用工具或实现来源、统计检验方法（检验类型、显著性水平、多重比较处理）、重复次数与报告形式（均值加减标准差等）。

惯例句式：
- Performance was measured by <指标>，defined as <定义>.
- Results are reported as the mean and standard deviation over <N> runs.
- Statistical significance was assessed using <检验> at the <水平> level, with <多重比较处理>.

要素自查：指标无歧义定义；比较结论有统计支撑或明确说明未做检验。

## 2.U Baselines and Comparisons（对照实验）

写作内容：每个基线的名称、来源（论文或代码库）、版本或实现来源、是否使用官方实现、对照条件是否同预算（同等训练数据、同等参数量、同等算力或调参预算）、复现设置与原报告设置的差异。

惯例句式：
- We compared against <基线>，using the official implementation released at <来源>.
- All methods were trained with the same <预算条件> to ensure a fair comparison.

要素自查：每个基线有版本或实现来源；同预算条件写明；差异如实交代。

## 2.T Reproducibility（复现信息）

写作内容：代码与配置的获取方式（仓库、提交号或附件）、环境复现方式（环境文件、容器镜像）、运行命令（训练与评测各一条）、数据获取方式、随机种子列表。

要素自查：对照 reproducibility-checklist.md。材料中无法提供的项显式标 TODO。

## 2.S Limitations（限制条件）

写作内容：具体失效场景与适用范围，每条限制对应可观察的条件与后果。

惯例句式：
- The method assumes <假设>；when <条件>，it may <失效表现>.
- Our evaluation is limited to <范围>；results on <未覆盖场景> may differ.

禁止写空话（如 结果可能因环境而异）。每条限制须指向具体场景；材料无据的限制不写，或标 TODO 请作者确认。

## 成稿格式约定

- 方法与实验流程：一般过去时加被动语态为主；普遍事实与结论可用现在时。
- 数值一律带单位，单位与事实底稿一致。
- 缺口处保留 `[TODO: 缺什么]` 与 `[待确认: 向谁确认]` 标注，交稿前由作者决定是否清除。
- 全篇符号、术语、指标名与符号表、事实底稿保持一致。
