# 术语表模板与建立规则

用途：术语表是全篇一致性回扫的唯一依据。case.json 提供术语表时以其为基线增量补充；未提供时从零建立。格式为 Markdown 表格，亦可导出为 JSON 数组供回扫阶段程序化比对。

## 表结构

| 序号 | 概念（中文） | 统一英文写法 | 缩写与全称 | 首次出现位置 | 原文同义变体 | 处理动作 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 深度学习 | deep learning | DL, deep learning（首次展开） | Introduction, 第1段第1句 | DL（第2段先于全称出现） | 首次出现调整为 deep learning (DL)，后文统一为 DL |
| 2 | 卷积神经网络 | convolutional neural network | CNN | Introduction, 第2段 | ConvNet | 统一为 CNN |
| 3 | 精确率 | precision | 无 | Experiments, 第1段 | accuracy（误用） | 依上下文判定为 precision，原 accuracy 处逐处核对语义后统一 |

## 建立规则

1. 抽取范围：领域核心术语（出现两次以上）、方法名、数据集名、指标名、模型名。单次出现的普通名词不进表。
2. 缩写条目必须登记全称与缩写的绑定关系，并标注首次出现位置。首现格式统一为 full term (ABBR)，后文一律用缩写。
3. 同义变体登记原文中实际出现过的所有写法，处理动作列写明统一方向与理由。判定依据是领域惯例与原文上下文，不做无依据的改写。
4. 大小写与连字符按领域惯例统一，例如 e-mail 与 email 二选一后全篇一致。
5. 中英双语对齐：中文稿润色时增加双语对齐列，保证同一概念中英文译法一一对应，不出现一词多译。
6. 冲突处置：case.json 术语表与原文实际用法冲突时，统计原文频次，采用高频写法，冲突条目写入 manual_review_items。

## JSON 导出格式（供回扫比对）

```json
[
  {
    "term_zh": "深度学习",
    "canonical_en": "deep learning",
    "abbr": "DL",
    "full_form": "deep learning",
    "first_occurrence": "Introduction, para 1, sentence 1",
    "variants_found": ["DL"],
    "action": "expand at first occurrence; use DL afterwards"
  }
]
```
