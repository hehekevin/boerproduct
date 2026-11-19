# 译文核验清单

## A. 完整性

1. 段号连续：正文 P 序列、图注 F、表格 T、公式 E、参考文献 R 均无缺号。
2. SRC 与 TGT 单元数量相等，一一对应。
3. 跨页跨栏合并段使用区间定位，合并理由与句子边界一致。
4. 参考文献从第一条到最后一条全部保留，未译的原文照抄并标记。

## B. 术语一致性

5. 每个 locked 术语在全部出现段落使用唯一译名。
6. 术语表 variant 列登记的禁用变体未出现在译文中。
7. 缩写首次出现给出中文全称加英文全称与缩写，此后用法一致。
8. pending 术语在译文中保留英文并在括号内说明，且登记到 uncertainty。

## C. 关系保真

9. 否定词（not, no, never, without, fail to）在译文中保留，无反向翻译。
10. 限定条件（only, at least, at most, up to, approximately, roughly, nearly）逐词保留。
11. 因果与让步连接词（because, therefore, however, although, despite）与原文逻辑一致。
12. 数字、小数、百分数、区间与单位与原文完全一致，禁止四舍五入或换算。
13. 公式占位符原样回填，未改写符号、下标与编号。
14. 文献引用标记（如 [12], (Smith et al., 2020)）原样保留，编号未错位。
15. 图表编号（Figure 3, Table 2）保留原编号，译文图表引用未指错对象。

## D. 指代与可读性

16. it, they, this, these 指代不明处补出对象并加 [指代: xxx] 标注。
17. 长句拆分未改变句序逻辑，未合并或拆分段落。

## E. 可核验

18. 每段有 NOTE 说明译法依据，可指回原文定位。
19. [!UNCLEAR] 标记均有原因说明，且同步登记到 result.json 的 uncertainty。
20. [!UNTRANSLATED] 段落已列入 partial 原因与未完成清单。

## F. 输出与状态

21. result.json 含 output_contract 全部字段与 case_id，可被 json 解析。
22. status 与实际完成度一致，禁止把 partial 写成 success。
23. verification.md 与最终译文一致，未通过项已修复或已登记。
24. change_log 完整记录分段数、术语锁定数、各批翻译与核验修复轮次。

## 人工确认清单（写入 verification.md 末尾）

- 需人工复核的句子清单（含 [!UNCLEAR] 全部位置与原因）。
- pending 术语及建议译名。
- OCR 低置信行清单（如适用）。
- 图片公式与图片表格位置清单（如适用）。
