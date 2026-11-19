# 任务（SYNTHETIC 示例，非正式案例）

对 seed.sql  restored 的只读数据库回答：
1. 每个 group_name 有多少样品？（GROUP BY 计数）
2. 龄期 age >= 7 天的样品，按 group_name 的平均 strength 是多少？（参数化 JOIN，? 占位符）
3. 依据字典解释字段含义与连接路径，说明一对多关系是否导致行数膨胀。
4. 导出可核对的结果表（CSV+JSON），保留查询日志（sql/params/row_count/耗时），只读不改库。