# 数据字典（SYNTHETIC 示例）

- samples.sample_id: 样品主键（INTEGER）。
- samples.group_name: 分组，分类文本，A / B（编码型字段，不可当数值聚合）。
- samples.age: 龄期，数值，单位 天(d)。
- measurements.id: 测量主键。
- measurements.sample_id: 外键 → samples.sample_id（一对多：一个样品可有多条测量）。
- measurements.strength: 抗压强度，数值，单位 MPa；缺失为 NULL，AVG 自动忽略 NULL。
- 连接路径：samples JOIN measurements ON samples.sample_id = measurements.sample_id。
  注意一对多会膨胀行数；按样品粒度聚合时需先聚合测量或去重。