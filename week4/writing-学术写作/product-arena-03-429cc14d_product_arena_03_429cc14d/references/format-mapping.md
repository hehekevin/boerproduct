# 格式字段映射表与输出模板

本文件提供文献条目在常见来源格式与三种目标格式之间的逐字段映射规则，Agent 在阶段 5 按表执行，不做自由发挥。

## 一、来源格式字段标准名对照

| 语义 | BibTeX | RIS | CNKI/中文导出 | EndNote XML |
|---|---|---|---|---|
| 作者 | author | AU | 作者 | authors |
| 年份 | year | PY | 年 | year |
| 题名 | title | TI | 题名 | titles/title |
| 期刊名 | journal | JO/T2 | 刊名 | periodical/title |
| 卷 | volume | VL | 卷 | volume |
| 期 | number | IS | 期(辑) | issue |
| 页码 | pages | SP+EP | 页码 | pages |
| DOI | doi | DO | DOI | ids/doi |
| 文献类型 | @article 等 | TY | 文献类型 | ref-type |
| 出版社 | publisher | PB | 出版社 | publisher |
| 出版地 | address | CY | 出版地 | pub-location |
| 摘要 | abstract | AB | 摘要 | abstract |
| 关键词 | keywords | KW | 关键词 | keywords |

类型码对照：RIS TY 17=期刊论文，10=图书，4=会议论文，3=学位论文；BibTeX @article/@book/@inproceedings/@phdthesis/@techreport；GB/T 7714 标识 J/M/C/D/R/N/P/S/DB/OL 等。

## 二、映射到 GB/T 7714-2015（顺序编码制）

通用输出模板（含类型标识与 DOI）：
- 期刊：作者. 题名[J]. 刊名, 年, 卷(期): 页码. DOI: xxx.
- 会议论文：作者. 题名[C]//会议录名. 出版地: 出版社, 年: 页码.
- 图书：作者. 书名[M]. 版本. 出版地: 出版社, 年: 页码.
- 学位论文：作者. 题名[D]. 城市: 学校, 年.
- 预印本：作者. 题名[EB/OL]. (发布日期)[引用日期]. URL 或 arXiv 标识.
- 在线资源：作者. 题名[EB/OL]. (发布日期)[引用日期]. URL.

字段规则：
1. 作者 3 人以内全列，超过 3 人列前 3 人后加"等"或"et al"（英文条目用 et al）。
2. 姓名规则：英文姓前名后缩写（Wang X Y）；中文条目用全名，多作者以逗号分隔。
3. 电子文献必须有 [EB/OL] 及引用日期；有 DOI 的期刊论文优先加 DOI。
4. 页码用半字线连接（123-130），中文条目用中文标点句号结尾，英文条目同规则但刊名保持原名大小写。
5. 预印本转正式版后类型标识从 [EB/OL] 改为 [J] 或 [C]，并写明卷期页。

## 三、映射到 APA 7（著者-出版年制）

通用输出模板：
- 期刊：Author, A. B., & Author, C. D. (Year). Title of article. Journal Name, Volume(Issue), pages. https://doi.org/xxx
- 图书：Author, A. B. (Year). Title of book (Edition). Publisher.
- 章节：Author, A. B. (Year). Chapter title. In E. Editor (Ed.), Book title (pp. 1-10). Publisher.
- 预印本：Author, A. B. (Year). Title. Repository Name. https://doi.org/xxx（或 arXiv URL）

字段规则：
1. 正文引用形式：(Wang & Li, 2020) 或 (Wang et al., 2020，3 人及以上)；上标编号制与 APA 不可混用，发现混用必须统一并在 change_records 留痕。
2. 作者姓全拼、名缩写、逗号与 & 连接；21 条以上作者列前 19 条加省略号再列最后一条。
3. DOI 一律写成 https://doi.org/ 前缀形式；无 DOI 的期刊论文不补 URL。
4. 题名句首大写其余小写（英文），期刊名逐词首字母大写。
5. 中文条目：中文题名后用方括号附英文翻译（若材料有），否则保留中文并遵循同样的标点结构。

## 四、映射到 BibTeX

1. 类型选择：期刊 @article、会议 @inproceedings、图书 @book、学位论文 @phdthesis、报告 @techreport、预印本 @article 加 journal = {arXiv preprint arXiv:xxxx} 或 @misc 加 eprint/archivePrefix。
2. 键名规则：第一作者姓小写 + 年份 + 题名首实词（wang2020citation），重名时加序号字母。
3. 字段保留：author, title, journal/booktitle, year, volume, number, pages, doi, publisher, address；pages 用双半线（123--130）。
4. LaTeX 特殊字符转义：& 写 \&，% 写 \%；中文条目无需转义但键名仍用拼音或英文。
5. 保留来源文件中原有的 doi 与 url 字段，不丢弃。

## 五、常见转换陷阱

1. RIS 的 SP/EP 拆分页码要合并为范围；单页条目 EP 缺失时只写 SP。
2. CNKI 导出的"卷(辑)"字段常混入期号，需拆分。
3. EndNote 导出的作者字段可能是一整串未分段，需按 and/分号智能切分后再套规则。
4. 中英混排标点：GB/T 7714 中文条目用全角句号"。"结尾常见，但规范推荐半角"."；按目标期刊惯例，不确定时在 uncertainty 说明。
5. 预印本与正式版合并后：年份取正式版发表年，题名取正式版，预印本标识符在 change_records 中留档。
6. DOI 一律保留原始大小写；不得为凑格式而改写 DOI 字符串。
