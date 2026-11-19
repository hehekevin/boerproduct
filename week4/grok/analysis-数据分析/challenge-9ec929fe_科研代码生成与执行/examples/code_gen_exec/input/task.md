# 任务规格（SYNTHETIC 示例，非正式案例）

编写并执行一段分析代码：
1. 读取 data.csv（路径经 ANALYSIS_DATA 环境变量提供，dataset_id = d）。
2. 按字典口径计算 strength 的均值：缺失（空字符串）排除，不得当作 0；记录行数与有效数值个数。
3. 将结果写入工作目录 results.json（键：n, n_numeric, mean_strength），并打印一行 JSON。
4. 验证：mean_strength 应等于 35.0（容差 1e-6）；数据集行数 n_rows_d 应等于 6。
5. 保留执行日志（命令、退出码、stdout/stderr、耗时、python 版本）。