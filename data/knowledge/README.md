# 梦卡知识库

更新：2026-09-02。生产主路线已调整为“自建现代简体中文知识卡”。此目录同时保留下载原文、离线清洗结果和本地开发索引，但它们不是已通过版权与内容审核的生产 RAG 知识库。

## 当前生产主路线

- [`自建知识库/知识卡规范.md`](自建知识库/知识卡规范.md)：定义文化依据、现代研究、梦卡原创三层内容结构，以及来源、权利、审校和生产闸门。
- [`自建知识库/首批50个梦象目录.md`](自建知识库/首批50个梦象目录.md)：首批 50 个高频梦象选题，只包含目录和检索边界，不包含最终解梦正文。
- [`自建知识库/首批5张知识卡依据清单.md`](自建知识库/首批5张知识卡依据清单.md)：记录被追赶、迷路、水域、已故亲友和牙齿脱落的首轮研究依据、可支持/不可支持的表达、研究局限和权利状态。
- [`自建知识库/样稿/`](自建知识库/样稿/)：50 张现代简体中文人工样稿，当前均为 `draft` 和 `original_pending_review`，不得直接进入生产。
- [`自建知识库/第二批10张知识卡计划.md`](自建知识库/第二批10张知识卡计划.md)：第二批的 10 个选题、组合边界和检索验收样例。
- [`自建知识库/第二批10张知识卡依据清单.md`](自建知识库/第二批10张知识卡依据清单.md)：记录第二批能用于内容分类、健康边界和不能用于固定解释的依据。
- [`自建知识库/第三批10张知识卡计划.md`](自建知识库/第三批10张知识卡计划.md)：第三批的 10 个补充选题、组合边界和检索验收样例。当前只有制作计划。
- [`自建知识库/第三批10张知识卡依据清单.md`](自建知识库/第三批10张知识卡依据清单.md)：第三批的分类依据、限制和内容安全边界。尚未写卡片正文。
- [`自建知识库/第四批10张知识卡计划.md`](自建知识库/第四批10张知识卡计划.md)：第四批的 10 个选题与安全边界。当前只有制作计划。
- [`自建知识库/第四批10张知识卡依据清单.md`](自建知识库/第四批10张知识卡依据清单.md)：第四批的首轮依据与高敏感主题边界。尚未写卡片正文。
- [`自建知识库/processed/cards.jsonl`](自建知识库/processed/cards.jsonl)：由 50 张 Markdown 样稿离线编译的机器可读知识卡。当前 50 条记录的 `retrieval_enabled` 和 `production_eligible` 均为 `false`，只供开发验证。
- [`自建知识库/evaluation/local-retrieval-report.json`](自建知识库/evaluation/local-retrieval-report.json)：65 组人工编写的合成查询全部通过本地短语检索，其中包含单卡、多卡、无匹配兜底和单字误命中反例；本轮模型调用为 0。
- 当前自建库状态为 `shadow_observation`。首批 50 张均已完成草稿、本地编译和合成检索验证，尚未进入用户输出；正式内容审校、权利签字和生产入库仍未完成。
- 65/65 只证明当前 50 类、当前人工样本的确定性关键词规则符合预期，不代表完整 RAG 的语义召回率、真实用户覆盖率或生成完成率。为避免“水果”误命中“水域”、“海外”误命中“海”，当前检索主动忽略单个汉字线索；未命中时明确走兜底，不让模型自行补造知识卡。
- 影子模式只读取用户确认后的结构化梦象与澄清答案，不复制梦境原文或结构化查询。会话存续期间可按会话与修订查看当前结果；用户删除会话后，仅保留匿名统计事件，内容只有随机统计编号、兜底状态、命中卡片、分数、匹配词和时间，不再保留会话编号。它不改变任何 API 业务响应，异常时自动放行原流程。
- 两本英文书和两份中文古籍扫描件降为内部研究/对照候选，不再作为自建库的默认生产正文来源。是否使用其中任何原文，仍需单独通过版本、权利、质量与内容审核。

本地复现命令不会调用云端模型：

```bash
.venv/bin/python backend/scripts/prepare_original_knowledge.py
PYTHONPATH=backend .venv/bin/pytest -q backend/tests/test_original_knowledge.py
PYTHONPATH=backend .venv/bin/python backend/scripts/evaluate_original_knowledge.py
# 查看真实影子流量的聚合命中数据，不输出梦境或梦象文字
PYTHONPATH=backend .venv/bin/python backend/scripts/report_original_knowledge_shadow.py
```

商用权利证据与审批闸门统一记录在 [`docs/知识库商用权利台账.md`](../../docs/知识库商用权利台账.md)。当前两本英文资料的建议状态为 `evidence_ready_for_legal_review`，表示具备提交审核的证据，不表示已经获准商用；所有 manifest 与片段继续保持 `commercial_approval=false`。

## 已下载

| 资料 | 本地位置 | 格式与规模 | 文件大小 | 当前状态 |
| --- | --- | ---: | ---: | --- |
| 《梦林玄解三十四卷首一卷》上海图书馆来源扫描件 | `解梦素材/menglin-xuanjie-shanghai/source.pdf` | PDF，1213 页 | 82,390,908 字节 | 候选；待核定刻本、完整性和 OCR |
| 《梦占逸旨》1939 年商务印书馆版扫描件 | `解梦素材/mengzhan-yizhi-1939/source.pdf` | PDF，77 页 | 3,454,955 字节 | 已完成目视页范围核验；待 OCR 小样、版本附加内容与商用审核 |
| *The Interpretation of Dreams* | `解梦素材/freud-interpretation-of-dreams-en/source.txt` | UTF-8 TXT | 见同目录 manifest | 已清洗并进入本地候选索引；权利证据已整理，待人工/法律审核 |
| *Ten Thousand Dreams Interpreted* | `解梦素材/miller-ten-thousand-dreams-en/source.txt` | UTF-8 TXT | 见同目录 manifest | 已清洗并进入本地候选索引；权利证据已整理，待人工/法律审核 |

每份 PDF 同目录的 `manifest-*.json` 保存下载时间、文件 SHA-256、Commons 文件 SHA-1、字节数、文件说明页地址、说明页修订号和许可证元数据快照。文件与来源 SHA-1、大小一致；pdfinfo 实测页数与目录一致，不等于逐页确认全书无缺。

## 来源和使用条件

- [《梦林玄解》文件说明页](https://commons.wikimedia.org/wiki/File:Shanghai_夢林玄解三十四卷首一卷.pdf)：Commons 元数据标记 Public domain / PD-scan (PD-old)，来源标记 Shanghai Library；元数据没有机器可读作者。不能据其他网页把整部汇编简单归为邵雍个人作品，编纂与刻本信息待查卷首。
- [《梦占逸旨》文件说明页](https://commons.wikimedia.org/wiki/File:NLC511-023031404015388-27665_夢占逸旨.pdf)：Commons 标记 Public domain / PD-scan (PD-China)，著录 1939 年商务印书馆版，来源标记 National Library of China。文件页作者栏为王云五，但 PDF 第5页正文署陈士元纂。该差异需要区分古籍作者与近代丛书编者，不能自动忽略近代序言、校注等附加内容的独立权利。
- **来源网站的公版标记不是项目完成商用法律审核的证明。** 原古籍、公版扫描、近代整理/序言、现代译文与网站整理文字要分别判断；上线地域也影响判断。当前两份素材 `commercial_approval=false`，不进入生产白名单。
- 下载仅用于版本核验与入库准备，保留原始扫描不修改。未抓取付费译注、现代商业解梦书、论坛资源或来源不明网盘。
- [维基文库《梦林玄解》](https://zh.wikisource.org/wiki/夢林玄解)明确标注未完成，仅有序和卷首入口；不作为完整可用书库。网站整理文字另有署名/相同方式共享条款，不能和古籍原文权利混为一谈。
- Commons 文件说明文字与结构化数据的许可分别见页面底部，本地元数据保留出处。不要将这些说明文字作为古籍正文检索。

## 抽样检查

- 使用 PDF 技能只渲染了两张样页：梦林 PDF 第3页、梦占 PDF 第5页。未执行全书 OCR。
- 梦林样页为竖排双页扫描，左右阅读次序、版心和边缘残损必须在 OCR 后校对。
- 梦占样页为竖排小字，清晰度有限，正文与小字注释不能混排；显示“卷之一内篇目录”和“陈士元纂”。
- 当前无扫描 PDF 的逐页完整性结论、无 OCR 准确率结论；两本 PDF 没有向量化。两本英文 TXT 已做 Embedding 开发索引，但尚未做 Rerank 或真实解读。
- 《梦占逸旨》已完成首轮页范围核验，记录见 [`解梦素材/mengzhan-yizhi-1939/page-range-audit.md`](解梦素材/mengzhan-yizhi-1939/page-range-audit.md)。第一批建议 OCR 小样是 PDF 第13–26页的卷二、卷三正文；其中第13、21页的目录列必须排除。封面、1939出版信息、自序、目录、空白/原书缺页与其余页码均未进入本轮 OCR 范围。
- 《梦占逸旨》PDF 第13–26页已完成本地 OCR 小样。macOS Vision 与 RapidOCR 都未达到可入库质量：竖排列序、异体字、版心和目录干扰明显，因此未生成简体文本、未切分、未向量化。原稿与人工抽查结论见 [`ocr-sample/README.md`](解梦素材/mengzhan-yizhi-1939/ocr-sample/README.md)。

## 英文文本清洗与切分

已运行 `.venv/bin/python backend/scripts/prepare_text_knowledge.py`，原始 `source.txt` 未修改：

- *The Interpretation of Dreams*：保留正文第 I–VII 章，排除 Gutenberg 包装、文学索引和转录说明；生成 540 个片段，长度 446–2599 字符，无空片段和重复片段。
- *Ten Thousand Dreams Interpreted*：按 2256 个 A–Z 梦象词条切分为 2265 个片段；其中 236 个仅含 “See …” 的交叉引用被保留但标记 `retrieval_enabled=false`，不进入后续检索。
- 每本书的 `processed/clean.txt` 是只做空白规范化的正文，`processed/chunks.jsonl` 保存书名、作者、译者、章节/词条、英文原文、原文件行号、来源 URL、原文件 SHA-256、质量标记和权利状态。
- `processed/report.json` 保存片段统计与异常计数，`processed/sample-validation.json` 对首、四分位、中位、四分之三和末尾片段同时验证清洗正文精确匹配与原文件行号范围匹配。
- 所有记录仍为 `candidate_not_commercially_approved`、`verified=false`；清洗切分过程的模型调用次数为 0。

## 本地 Embedding 索引

- `data/knowledge/dream_sources.sqlite3` 使用阿里云百炼 `text-embedding-v4`、512 维向量，当前共 2,569 个可检索片段；索引文件约 11 MB，被 `.gitignore` 排除。
- 首次完整构建实际计数 387,753 tokens；五条中文验收查询额外使用 37 tokens，英文对照查询使用 46 tokens。
- 索引保留书名、作者、译者、章节/词条、英文原文、原文行号、来源 URL、源文件 SHA-256、权利状态、模型和维度。每 10 条落盘，中断后可按内容哈希续跑，不会静默覆盖已变更原文。
- 中文直接跨语言检索的“坠落”、“水中行走”命中合理，“旧房子”命中童年记忆相关段落；“鹿”和“被追赶”出现语义漂移。对照英文查询能命中 `Deer`、`Forest`、`Fall`、`Water`，证明下一步应先用大模型提取梦象并生成英文检索词，再做关键词+向量混合召回与 Rerank。
- 已实现受控检索链：通义千问只读取用户确认后的结构化梦象，生成字面英文查询与关键词；关键词+多查询向量混合召回 20 条，再由阿里云百炼 `qwen3-rerank` 输出 5 条。不重复发送原始梦境，该链路不做解读或预测。
- 五组真实验收中：“森林和鹿”前五依次包含 Deer、Forest、Stag、Moon、Woods；“水中行走”首位 Water；“旧房子”首位是弗洛伊德早年生活印象段落。“被陌生人追赶”在 Miller 没有独立同名词条，检索返回 Anxiety、Escape 和弗洛伊德的具体追跑场景，不伪造书中不存在的条目。
- 本轮五组完整链路验收的 Embedding 计数 140 tokens，Rerank 计数 40,561 tokens，另有 5 次查询扩展大模型调用。可用 `PYTHONPATH=backend .venv/bin/python backend/scripts/evaluate_retrieval.py` 复现，该命令会产生云端费用。
- 复现命令：`PYTHONPATH=backend .venv/bin/python backend/scripts/build_knowledge_index.py build`；中文对照验收：同一脚本的 `evaluate` 命令。这两个命令会发生付费模型调用。

## 下一步入库门槛

1. 确认用书与具体版本；排除未经确认的近代附加文字，建立允许使用的页范围。
2. 先挑10–20页做竖排 OCR 试验，按右至左列序及双页次序人工校对；不一次满负载跑1290页。
3. 保留原文、OCR原稿和校对稿三个层次。每条记录包含书名、版本、卷/篇/条目、PDF页码、源文件哈希、校对状态。
4. 按完整条目切分，不把吉凶条件句拆散；简繁规范化另存检索字段，不覆盖引用原文。
5. 当前 SQLite 向量库仅用于候选素材开发验收。只有通过版本/权利/质量检查的片段才能进入生产白名单；还需增加梦象英文查询扩展、混合召回和 Rerank。
6. 古籍中的吉凶、疾病、寿命等记述仅能作为历史文化材料，不直接转换为对用户的预测或诊断。没有匹配依据时明确说明无依据，不用模型记忆补书。

## 复现下载

在项目根目录执行 `.venv/bin/python backend/scripts/download_knowledge_sources.py` 可复核两份 PDF，执行 `.venv/bin/python backend/scripts/download_text_knowledge_sources.py` 可复核两份英文 TXT。
脚本已存在时只校验，不覆盖。不会安装 OCR、启动服务器、上传用户梦境、调用模型或建立向量库。
