# 数据字典（SYNTHETIC 示例）

- sample: 样品编号（主键）。
- group: 处理组，分类变量，取值 A / B；两组独立样本，非配对设计。
- age: 龄期，数值，单位 天(d)。
- strength: 抗压强度，数值，单位 MPa；缺失以空字符串表示，不得当作 0，不得填补。
- 分析口径：strength 为结果变量；group 为分组因素；age 为连续协变量。