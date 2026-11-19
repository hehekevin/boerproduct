# 数据字典（SYNTHETIC 示例）

- sample: 样品编号（主键）。
- cement: 水泥用量，数值，单位 kg/m^3。
- strength: 抗压强度，数值，单位 MPa；缺失以空字符串表示，计算均值时排除，不得当作 0，不得填补。
- 口径：mean_strength = 有效 strength 的算术平均；n = 总行数；n_numeric = 有效数值个数。