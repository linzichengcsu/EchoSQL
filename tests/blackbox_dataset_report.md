# EchoSQL(MiniDB) 黑盒测试数据集报告

> 生成方式：`python tests/test_blackbox.py --report <path>`（或调用 `blackbox_dataset.write_dataset_report`）。

## 规模统计

| 指标 | 数值 |
| --- | --- |
| 总用例数 | 239 |
| 边界用例数 | 67 |
| 边界占比 | 28.03% |
| 要求：总用例 >= 200 | 满足 |
| 要求：边界占比 >= 5% | 满足 |

## 分层分布

| 层 | 用例数 |
| --- | --- |
| cli | 13 |
| engine | 210 |
| web | 16 |

## 类别分布

| 类别 | 用例数 |
| --- | --- |
| CLI | 13 |
| NULL | 12 |
| Web | 16 |
| 删除 | 16 |
| 名称大小写 | 12 |
| 建表 | 12 |
| 插入 | 30 |
| 查询 | 46 |
| 目录持久化 | 12 |
| 脚本批处理 | 10 |
| 表达式 | 18 |
| 词法字面量 | 22 |
| 边界 | 20 |

## 边界用例清单（67 条）

| 编号 | 类别 | 标题 |
| --- | --- | --- |
| BB-B008 | 插入 | FLOAT 字面量赋值 INT 列被物理截断为整数（当前行为） |
| BB-B014 | 插入 | 字符串内换行符原样保留 |
| BB-B023 | 插入 | 负数字面量不受文法支持，被语法拒绝 |
| BB-B024 | 插入 | INT 32 位上限值可插入并回读 |
| BB-B025 | 插入 | INT 超过 32 位上限被引擎拒绝（RowTooLarge） |
| BB-B026 | 插入 | 超大 INT 字面量被引擎拒绝而非崩溃 |
| BB-C005 | 查询 | 空表 SELECT 保留列头、行集为空 |
| BB-C007 | 查询 | 等值比较命中临界值（=3） |
| BB-C008 | 查询 | 不等于（<>）排除临界值 |
| BB-C009 | 查询 | != 与 <> 等价 |
| BB-C010 | 查询 | 小于（<）不含临界值 |
| BB-C011 | 查询 | 小于等于（<=）含临界值 |
| BB-C012 | 查询 | 大于（>）不含临界值 |
| BB-C013 | 查询 | 大于等于（>=）含临界值 |
| BB-C019 | 查询 | AND 优先级高于 OR（a=1 OR b=1 AND c=1） |
| BB-C020 | 查询 | 括号改变结合：(a=1 OR b=1) AND c=1 |
| BB-C021 | 查询 | NOT 优先级高于 AND |
| BB-C022 | 查询 | 括号内 NOT：NOT (a=1 AND b=0) |
| BB-C030 | 查询 | FLOAT 列包含临界值的大于等于比较 |
| BB-C035 | 查询 | 字符串小于等于含临界值 |
| BB-D005 | 删除 | 空表 DELETE 影响 0 行且不报错 |
| BB-E004 | NULL | NULL 行不匹配不等值条件（unknown） |
| BB-E006 | NULL | 与 NULL 字面量比较结果恒为 unknown |
| BB-E008 | NULL | OR 遇 TRUE 短路保留 NULL 行 |
| BB-F006 | 名称大小写 | 60 字符长表名/列名可建可查 |
| BB-F010 | 名称大小写 | 非 ASCII（中文）标识符当前实现允许建表并查询 |
| BB-F011 | 名称大小写 | 字符串比较区分大小写（'alice' ≠ 'Alice'） |
| BB-G004 | 词法字面量 | 未闭合字符串报词法错误 |
| BB-G005 | 词法字面量 | 未闭合块注释报词法错误 |
| BB-G006 | 词法字面量 | 数字后紧跟字母为非法数字 |
| BB-G007 | 词法字面量 | 浮点后再现小数点非法（1.2.3） |
| BB-G008 | 词法字面量 | 浮点形式 .5.6 非法 |
| BB-G009 | 词法字面量 | 浮点形式 1..2 非法 |
| BB-G016 | 词法字面量 | 纯注释输入视为空输入返回 None |
| BB-G020 | 词法字面量 | 负浮点字面量不受支持 |
| BB-G021 | 词法字面量 | 科学计数法 1e3 报词法错误 |
| BB-H005 | 表达式 | 40 层括号嵌套不崩溃且求值正确 |
| BB-H016 | 表达式 | 120 项 OR 长链全不命中返回空集 |
| BB-I003 | 脚本批处理 | execute_script 末尾缺分号宽容执行 |
| BB-I009 | 脚本批处理 | 脚本中任一语句词法错误则整体不执行 |
| BB-K001 | 边界 | 空字符串输入返回 None |
| BB-K002 | 边界 | 纯空白输入返回 None |
| BB-K003 | 边界 | 孤立分号输入返回 None |
| BB-K004 | 边界 | 单 VARCHAR 列 4000 字符可存可回读 |
| BB-K005 | 边界 | 单 VARCHAR 列 4080 字符恰可容纳 |
| BB-K006 | 边界 | 单 VARCHAR 列 4090 字符超页被拒绝 |
| BB-K007 | 边界 | 双 VARCHAR 大列组合行仍可容纳 |
| BB-K008 | 边界 | 300 行跨多页插入后全部可查回 |
| BB-K009 | 边界 | 60 层括号嵌套 WHERE 不崩溃 |
| BB-K010 | 边界 | 单次脚本执行 200 条 INSERT |
| BB-K011 | 边界 | 一次建 25 张表并全部登记 |
| BB-K012 | 边界 | 5000 字符字符串超行容量被拒绝 |
| BB-K013 | 边界 | 100 字符标识符可建可查 |
| BB-K014 | 边界 | 单列单行表从空到首行 |
| BB-K015 | 边界 | \r\n 与制表符混合分隔的 SQL 正常执行 |
| BB-K016 | 边界 | 大数值浮点 123456.789 往返一致 |
| BB-K017 | 边界 | 空表带 WHERE 查询返回空集不报错 |
| BB-K018 | 边界 | 对已清空表重复 DELETE 安全返回 0 |
| BB-K019 | 边界 | 四类列型整行往返一致 |
| BB-K020 | 边界 | 640 字长中文串入库回读一致 |
| BB-L004 | CLI | 批处理中 INT 溢出打印 RowTooLarge |
| BB-L006 | CLI | REPL 词法错误打印不崩溃 |
| BB-L009 | CLI | FIFO 策略 + 容量 1 的批处理可运行 |
| BB-M006 | Web | API 空表查询返回列头与空行 |
| BB-M009 | Web | API INT 溢出返回 400 而非 500 |
| BB-M010 | Web | API 空 SQL 返回 EMPTY |
| BB-M012 | Web | API 非 JSON 请求体按空 SQL 处理 |

## 全部用例清单（239 条）

| 编号 | 层 | 类别 | 边界 | 标题 | 需求追溯 |
| --- | --- | --- | --- | --- | --- |
| BB-A001 | engine | 建表 | - | 三类列混合建表成功 | FR-3.5 / TC-E2E-01 |
| BB-A002 | engine | 建表 | - | 单列建表成功 | FR-3.5 |
| BB-A003 | engine | 建表 | - | 四类列型（INT/FLOAT/VARCHAR/CHAR）建表成功 | grammar.md §2 |
| BB-A004 | engine | 建表 | - | 重复建同名表报 TableAlreadyExists | TC-E2E-01 |
| BB-A005 | engine | 建表 | - | 保留字作表名被语法拒绝 | grammar.md §2 |
| BB-A006 | engine | 建表 | - | 保留字作列名被语法拒绝 | grammar.md §2 |
| BB-A007 | engine | 建表 | - | 重复列名建表（文法未定义拒绝，当前允许） | grammar.md §2 |
| BB-A008 | engine | 建表 | - | 未知列类型 DATE 被语法拒绝 | grammar.md §2 |
| BB-A009 | engine | 建表 | - | 空列清单 CREATE TABLE t() 被语法拒绝 | grammar.md §2 |
| BB-A010 | engine | 建表 | - | 缺少右括号建表被语法拒绝 | grammar.md §2 |
| BB-A011 | engine | 建表 | - | 数字开头表名触发非法数字词法错误 | grammar.md §1.2 |
| BB-A012 | engine | 建表 | - | 单次输入两条建表语句均生效，返回最后一条结果 | FR-3.5 |
| BB-B001 | engine | 插入 | - | 整行插入三列并查询回读 | FR-3.5 |
| BB-B002 | engine | 插入 | - | 显式列清单（全列）插入 | grammar.md §2 |
| BB-B003 | engine | 插入 | - | 列清单乱序：值按清单列序映射 | grammar.md §2 |
| BB-B004 | engine | 插入 | - | 部分列插入：缺失列默认 NULL | FR-3.5 |
| BB-B005 | engine | 插入 | - | 全 NULL 字面量插入 | grammar.md §4.1 |
| BB-B006 | engine | 插入 | - | NULL 写入 INT 列可回读为 NULL | grammar.md §4.1 |
| BB-B007 | engine | 插入 | - | INT 字面量赋值 FLOAT 列转为浮点 | grammar.md §4.2 |
| BB-B008 | engine | 插入 | 是 | FLOAT 字面量赋值 INT 列被物理截断为整数（当前行为） | grammar.md §4.2 |
| BB-B009 | engine | 插入 | - | 三种浮点字面量形式入库回读 | grammar.md §1.2.5 |
| BB-B010 | engine | 插入 | - | 空字符串可插入并回读 | grammar.md §1.2.6 |
| BB-B011 | engine | 插入 | - | 转义单引号（'' 表示 '）入库回读 | grammar.md §1.2.6 |
| BB-B012 | engine | 插入 | - | 字符串内分号不被当作语句分隔符 | grammar.md §1.2.6 |
| BB-B013 | engine | 插入 | - | 中文字符串入库回读（UTF-8） | grammar.md §1.1 |
| BB-B014 | engine | 插入 | 是 | 字符串内换行符原样保留 | grammar.md §1.2.6 |
| BB-B015 | engine | 插入 | - | 无主键约束：重复行允许插入 | FR-3.5 |
| BB-B016 | engine | 插入 | - | 值数量少于列数报 ColumnCountMismatch | grammar.md §4.2 |
| BB-B017 | engine | 插入 | - | 值数量多于列数报 ColumnCountMismatch | grammar.md §4.2 |
| BB-B018 | engine | 插入 | - | 列清单引用不存在列报 UnknownColumn | grammar.md §4.2 |
| BB-B019 | engine | 插入 | - | 字符串写入 INT 列报 TypeMismatch | grammar.md §4.2 |
| BB-B020 | engine | 插入 | - | INT 字面量写入 VARCHAR 列报 TypeMismatch | grammar.md §4.2 |
| BB-B021 | engine | 插入 | - | FLOAT 字面量写入 VARCHAR 列报 TypeMismatch | grammar.md §4.2 |
| BB-B022 | engine | 插入 | - | 向未建表插入报 UnknownTable | grammar.md §4.2 |
| BB-B023 | engine | 插入 | 是 | 负数字面量不受文法支持，被语法拒绝 | grammar.md §2（已知限制） |
| BB-B024 | engine | 插入 | 是 | INT 32 位上限值可插入并回读 | grammar.md §4.1 |
| BB-B025 | engine | 插入 | 是 | INT 超过 32 位上限被引擎拒绝（RowTooLarge） | 缺陷#1 / test_boundary |
| BB-B026 | engine | 插入 | 是 | 超大 INT 字面量被引擎拒绝而非崩溃 | 缺陷#1 / test_boundary |
| BB-B027 | engine | 插入 | - | 前导零整数 007 按 7 存储 | grammar.md §1.2.5 |
| BB-B028 | engine | 插入 | - | CHAR 列可存字符串并回读 | grammar.md §2 |
| BB-B029 | engine | 插入 | - | NULL 写入 FLOAT 列回读为 NULL | grammar.md §4.1 |
| BB-B030 | engine | 插入 | - | 脚本连续插入三行后计数正确 | FR-3.5 |
| BB-C001 | engine | 查询 | - | SELECT * 返回全列与全部行 | FR-3.1 |
| BB-C002 | engine | 查询 | - | 按列清单投影 | FR-3.1 |
| BB-C003 | engine | 查询 | - | 投影列序按书写顺序输出 | FR-3.1 |
| BB-C004 | engine | 查询 | - | 单列投影 | FR-3.1 |
| BB-C005 | engine | 查询 | 是 | 空表 SELECT 保留列头、行集为空 | FR-3.1 / 边界 |
| BB-C006 | engine | 查询 | - | 空表带 WHERE 查询返回空集 | FR-3.1 |
| BB-C007 | engine | 查询 | 是 | 等值比较命中临界值（=3） | grammar.md §3 |
| BB-C008 | engine | 查询 | 是 | 不等于（<>）排除临界值 | grammar.md §3 |
| BB-C009 | engine | 查询 | 是 | != 与 <> 等价 | grammar.md §3 |
| BB-C010 | engine | 查询 | 是 | 小于（<）不含临界值 | grammar.md §3 |
| BB-C011 | engine | 查询 | 是 | 小于等于（<=）含临界值 | grammar.md §3 |
| BB-C012 | engine | 查询 | 是 | 大于（>）不含临界值 | grammar.md §3 |
| BB-C013 | engine | 查询 | 是 | 大于等于（>=）含临界值 | grammar.md §3 |
| BB-C014 | engine | 查询 | - | WHERE 无匹配行返回空集 | FR-3.1 |
| BB-C015 | engine | 查询 | - | 字符串等值过滤 | FR-3.1 |
| BB-C016 | engine | 查询 | - | 数值比较过滤（age > 18） | TC-E2E-03 |
| BB-C017 | engine | 查询 | - | AND 组合条件 | grammar.md §3 |
| BB-C018 | engine | 查询 | - | OR 组合条件覆盖全部行 | grammar.md §3 |
| BB-C019 | engine | 查询 | 是 | AND 优先级高于 OR（a=1 OR b=1 AND c=1） | grammar.md §3 |
| BB-C020 | engine | 查询 | 是 | 括号改变结合：(a=1 OR b=1) AND c=1 | grammar.md §3 |
| BB-C021 | engine | 查询 | 是 | NOT 优先级高于 AND | grammar.md §3 |
| BB-C022 | engine | 查询 | 是 | 括号内 NOT：NOT (a=1 AND b=0) | grammar.md §3 |
| BB-C023 | engine | 查询 | - | 双重否定 NOT NOT 等价于原条件 | grammar.md §3 |
| BB-C024 | engine | 查询 | - | 算术表达式谓词 a + b > 6 | grammar.md §3 |
| BB-C025 | engine | 查询 | - | 算术表达式谓词 a - b < 0 | grammar.md §3 |
| BB-C026 | engine | 查询 | - | 算术等值：a + 1 = 4 | grammar.md §3 |
| BB-C027 | engine | 查询 | - | INT 列与 FLOAT 列数值可互比（a = x） | grammar.md §4.2 |
| BB-C028 | engine | 查询 | - | INT 列与 FLOAT 字面量比较（id = 3.0） | grammar.md §4.2 |
| BB-C029 | engine | 查询 | - | FLOAT 列精确等值比较 | grammar.md §4.2 |
| BB-C030 | engine | 查询 | 是 | FLOAT 列包含临界值的大于等于比较 | grammar.md §4.2 |
| BB-C031 | engine | 查询 | - | 常量谓词 TRUE 保留全部行 | grammar.md §3 |
| BB-C032 | engine | 查询 | - | 常量谓词 FALSE 返回空集 | grammar.md §3 |
| BB-C033 | engine | 查询 | - | 常量比较 1 = 1 恒真 | grammar.md §3 |
| BB-C034 | engine | 查询 | - | 字符串字典序小于比较（name < 'gamma'） | grammar.md §3 |
| BB-C035 | engine | 查询 | 是 | 字符串小于等于含临界值 | grammar.md §3 |
| BB-C036 | engine | 查询 | - | 转义单引号字符串精确匹配 | grammar.md §1.2.6 |
| BB-C037 | engine | 查询 | - | 中文字符串等值匹配 | grammar.md §1.1 |
| BB-C038 | engine | 查询 | - | LIKE 模糊匹配不受支持，语法拒绝 | grammar.md §7（未实现） |
| BB-C039 | engine | 查询 | - | IS NULL 语法不受支持，语法拒绝 | grammar.md §7（未实现） |
| BB-C040 | engine | 查询 | - | 投影不存在的列报 UnknownColumn | grammar.md §4.2 |
| BB-C041 | engine | 查询 | - | WHERE 引用不存在的列报 UnknownColumn | grammar.md §4.2 |
| BB-C042 | engine | 查询 | - | 查询未建表报 UnknownTable | grammar.md §4.2 |
| BB-C043 | engine | 查询 | - | 行内块注释不干扰查询 | grammar.md §1.2.2 |
| BB-C044 | engine | 查询 | - | 关键字任意大小写等价 | grammar.md §1.1 |
| BB-C045 | engine | 查询 | - | 投影表达式不受文法支持（SELECT 列表仅列名） | grammar.md §7（未实现） |
| BB-C046 | engine | 查询 | - | 括号嵌套组合：id=1 OR (id=2 AND id=3) | grammar.md §3 |
| BB-D001 | engine | 删除 | - | 按主键删除单行，删除后不可见 | TC-E2E-04 |
| BB-D002 | engine | 删除 | - | 范围条件删除多行（id <= 2） | FR-3.5 |
| BB-D003 | engine | 删除 | - | 无条件 DELETE 删除全部行 | FR-3.5 |
| BB-D004 | engine | 删除 | - | 无匹配条件的 DELETE 影响 0 行 | FR-3.5 |
| BB-D005 | engine | 删除 | 是 | 空表 DELETE 影响 0 行且不报错 | FR-3.5 / 边界 |
| BB-D006 | engine | 删除 | - | 按数值条件删除后剩余行正确 | TC-E2E-04 |
| BB-D007 | engine | 删除 | - | AND 条件删除与不删除的边界 | grammar.md §3 |
| BB-D008 | engine | 删除 | - | OR 条件删除多行 | grammar.md §3 |
| BB-D009 | engine | 删除 | - | NULL 参与比较不匹配任何行（a = NULL） | grammar.md §4.1 |
| BB-D010 | engine | 删除 | - | 字符串条件删除 | FR-3.5 |
| BB-D011 | engine | 删除 | - | NOT 条件删除：删除非 17 岁者 | grammar.md §3 |
| BB-D012 | engine | 删除 | - | 删光后整页回收，可继续插入新行 | FR-3.2 页回收 |
| BB-D013 | engine | 删除 | - | 删除未建表报 UnknownTable | grammar.md §4.2 |
| BB-D014 | engine | 删除 | - | WHERE 引用不存在列报 UnknownColumn | grammar.md §4.2 |
| BB-D015 | engine | 删除 | - | WHERE 为 INT 列报 TypeMismatch | grammar.md §4.2 |
| BB-D016 | engine | 删除 | - | WHERE 为 VARCHAR 列报 TypeMismatch | grammar.md §4.2 |
| BB-E001 | engine | NULL | - | 全 NULL 行各列回读为 NULL | grammar.md §4.1 |
| BB-E002 | engine | NULL | - | 部分列插入，未指定列默认为 NULL | FR-3.5 |
| BB-E003 | engine | NULL | - | NULL 行不匹配等值条件 | grammar.md §4.1 |
| BB-E004 | engine | NULL | 是 | NULL 行不匹配不等值条件（unknown） | grammar.md §4.1 |
| BB-E005 | engine | NULL | - | NULL 行不匹配 <= 与 >= | grammar.md §4.1 |
| BB-E006 | engine | NULL | 是 | 与 NULL 字面量比较结果恒为 unknown | grammar.md §4.1 |
| BB-E007 | engine | NULL | - | NOT 作用于含 NULL 行不产生匹配 | grammar.md §4.1 |
| BB-E008 | engine | NULL | 是 | OR 遇 TRUE 短路保留 NULL 行 | 三值逻辑 OR |
| BB-E009 | engine | NULL | - | AND 遇 FALSE 短路排除 NULL 行 | 三值逻辑 AND |
| BB-E010 | engine | NULL | - | NULL 参与算术比较结果为 unknown | 三值逻辑 算术 |
| BB-E011 | engine | NULL | - | 投影中 NULL 值原样展示 | FR-3.1 |
| BB-E012 | engine | NULL | - | NULL 行在数值过滤中被排除、非 NULL 行保留 | grammar.md §4.1 |
| BB-F001 | engine | 名称大小写 | - | 表名/列名大小写不敏感（统一小写解析） | grammar.md §1.2.4 |
| BB-F002 | engine | 名称大小写 | - | 关键字全小写查询可用 | grammar.md §1.1 |
| BB-F003 | engine | 名称大小写 | - | 关键字任意混写大小写可用 | grammar.md §1.1 |
| BB-F004 | engine | 名称大小写 | - | 含下划线与数字的标识符可用 | grammar.md §1.2.4 |
| BB-F005 | engine | 名称大小写 | - | 下划线开头标识符可用 | grammar.md §1.2.4 |
| BB-F006 | engine | 名称大小写 | 是 | 60 字符长表名/列名可建可查 | P5 边界 |
| BB-F007 | engine | 名称大小写 | - | 保留字作 INSERT 列清单项被语法拒绝 | grammar.md §2 |
| BB-F008 | engine | 名称大小写 | - | SELECT 列名按书写大小写返回 | FR-3.1 |
| BB-F009 | engine | 名称大小写 | - | SELECT * 列头保留建表时大小写 | FR-3.3 |
| BB-F010 | engine | 名称大小写 | 是 | 非 ASCII（中文）标识符当前实现允许建表并查询 | grammar.md §1.2.4（实现放宽） |
| BB-F011 | engine | 名称大小写 | 是 | 字符串比较区分大小写（'alice' ≠ 'Alice'） | grammar.md §1.2.4 |
| BB-F012 | engine | 名称大小写 | - | 大写插入与混合大小写查询回读一致 | grammar.md §1.2.4 |
| BB-G001 | engine | 词法字面量 | - | 非法字符 @ 报词法错误 | grammar.md §1.2.8 |
| BB-G002 | engine | 词法字面量 | - | 非法字符 # 报词法错误 | grammar.md §1.2.8 |
| BB-G003 | engine | 词法字面量 | - | 非法字符 $ 报词法错误 | grammar.md §1.2.8 |
| BB-G004 | engine | 词法字面量 | 是 | 未闭合字符串报词法错误 | grammar.md §1.2.6 |
| BB-G005 | engine | 词法字面量 | 是 | 未闭合块注释报词法错误 | grammar.md §1.2.2 |
| BB-G006 | engine | 词法字面量 | 是 | 数字后紧跟字母为非法数字 | grammar.md §1.2.5 |
| BB-G007 | engine | 词法字面量 | 是 | 浮点后再现小数点非法（1.2.3） | grammar.md §1.2.5 |
| BB-G008 | engine | 词法字面量 | 是 | 浮点形式 .5.6 非法 | grammar.md §1.2.5 |
| BB-G009 | engine | 词法字面量 | 是 | 浮点形式 1..2 非法 | grammar.md §1.2.5 |
| BB-G010 | engine | 词法字面量 | - | 孤立感叹号报词法错误 | grammar.md §1.2.8 |
| BB-G011 | engine | 词法字面量 | - | 行注释被跳过，语句正常执行 | grammar.md §1.2.2 |
| BB-G012 | engine | 词法字面量 | - | 跨行块注释被跳过 | grammar.md §1.2.2 |
| BB-G013 | engine | 词法字面量 | - | 语句尾行注释不影响执行 | grammar.md §1.2.2 |
| BB-G014 | engine | 词法字面量 | - | 注释位于关键字之间不干扰 | grammar.md §1.2.2 |
| BB-G015 | engine | 词法字面量 | - | 字符串值内的 -- 不是注释 | grammar.md §1.2.6 |
| BB-G016 | engine | 词法字面量 | 是 | 纯注释输入视为空输入返回 None | FR-3.4 |
| BB-G017 | engine | 词法字面量 | - | 制表符/换行分隔的语句正常执行 | grammar.md §1.2.1 |
| BB-G018 | engine | 词法字面量 | - | 字符串内制表符原样保留 | grammar.md §1.2.6 |
| BB-G019 | engine | 词法字面量 | - | 字符串首尾空格原样保留 | grammar.md §1.2.6 |
| BB-G020 | engine | 词法字面量 | 是 | 负浮点字面量不受支持 | grammar.md §2（已知限制） |
| BB-G021 | engine | 词法字面量 | 是 | 科学计数法 1e3 报词法错误 | README 已知限制 |
| BB-G022 | engine | 词法字面量 | - | 字符串内分号不截断语句（整段执行） | grammar.md §1.2.6 |
| BB-H001 | engine | 表达式 | - | 浮点算术谓词 x + 0.5 = 3.0 | grammar.md §3 |
| BB-H002 | engine | 表达式 | - | 两侧算术表达式比较 a + 1 = b | grammar.md §3 |
| BB-H003 | engine | 表达式 | - | 左侧常量算术 10 - a = 8 | grammar.md §3 |
| BB-H004 | engine | 表达式 | - | 嵌套括号算术 (a + (b - 1)) = 4 | grammar.md §3 |
| BB-H005 | engine | 表达式 | 是 | 40 层括号嵌套不崩溃且求值正确 | P5 边界 |
| BB-H006 | engine | 表达式 | - | 比较链 1 < 2 < 3 不受支持，语法拒绝 | grammar.md §3 |
| BB-H007 | engine | 表达式 | - | NOT 与 AND 组合过滤 | grammar.md §3 |
| BB-H008 | engine | 表达式 | - | 三项 OR 组合命中一项 | grammar.md §3 |
| BB-H009 | engine | 表达式 | - | 列与常量表达式比较 id = 1 + 1 | grammar.md §3 |
| BB-H010 | engine | 表达式 | - | 常量算术谓词 1 + 1 = 2 恒真 | grammar.md §3 |
| BB-H011 | engine | 表达式 | - | 乘号表达式不受支持，语法拒绝 | grammar.md §7（未实现） |
| BB-H012 | engine | 表达式 | - | NOT 常量比较恒假 | grammar.md §3 |
| BB-H013 | engine | 表达式 | - | 两列字符串等值比较 | grammar.md §3 |
| BB-H014 | engine | 表达式 | - | 两 INT 列大小比较 | grammar.md §3 |
| BB-H015 | engine | 表达式 | - | 括号内 OR 的否定过滤 | grammar.md §3 |
| BB-H016 | engine | 表达式 | 是 | 120 项 OR 长链全不命中返回空集 | P5 边界 |
| BB-H017 | engine | 表达式 | - | 布尔字面量不能作为 SELECT 列表项 | grammar.md §2 |
| BB-H018 | engine | 表达式 | - | 混合优先级组合精确命中单行 | grammar.md §3 |
| BB-I001 | engine | 脚本批处理 | - | 多语句 execute 返回最后一条语句结果 | FR-3.4 |
| BB-I002 | engine | 脚本批处理 | - | execute_script 返回各语句结果序列 | FR-3.4 |
| BB-I003 | engine | 脚本批处理 | 是 | execute_script 末尾缺分号宽容执行 | FR-3.4 |
| BB-I004 | engine | 脚本批处理 | - | 脚本中连续分号空语句被跳过 | FR-3.4 |
| BB-I005 | engine | 脚本批处理 | - | 脚本中途出错立即抛出 | FR-3.4 |
| BB-I006 | engine | 脚本批处理 | - | 脚本出错后已生效副作用保留 | FR-3.4 |
| BB-I007 | engine | 脚本批处理 | - | 脚本含注释与空行只执行真实语句 | FR-3.4 |
| BB-I008 | engine | 脚本批处理 | - | 脚本末尾空白与无分号宽容处理 | FR-3.4 |
| BB-I009 | engine | 脚本批处理 | 是 | 脚本中任一语句词法错误则整体不执行 | FR-1.1 |
| BB-I010 | engine | 脚本批处理 | - | CRLF 行尾的脚本正常执行 | grammar.md §1.2.1 |
| BB-J001 | engine | 目录持久化 | - | 全新空库 tables() 为空 | FR-3.3 |
| BB-J002 | engine | 目录持久化 | - | 建表顺序记录在 tables() | FR-3.3 |
| BB-J003 | engine | 目录持久化 | - | table_infos 返回列名与列类型 | FR-3.3 |
| BB-J004 | engine | 目录持久化 | - | 删除不存在的表返回 0 且安全 | FR-3.2 |
| BB-J005 | engine | 目录持久化 | - | 删表后目录移除、可重建同名表 | FR-3.2 |
| BB-J006 | engine | 目录持久化 | - | 执行后 stats 返回完整字段 | FR-2.2 |
| BB-J007 | engine | 目录持久化 | - | 命中率取值在 [0,1] 区间 | FR-2.2 |
| BB-J008 | engine | 目录持久化 | - | 关闭后重启：表结构与数据均保留 | TC-E2E-05 |
| BB-J009 | engine | 目录持久化 | - | 重启后删除结果依然生效 | TC-E2E-05 |
| BB-J010 | engine | 目录持久化 | - | 重启后多个表全部保留 | TC-E2E-05 |
| BB-J011 | engine | 目录持久化 | - | 重启后可继续写入并再次持久化 | TC-E2E-05 |
| BB-J012 | engine | 目录持久化 | - | 删表并重启：表已删除且可重建 | FR-3.2 |
| BB-K001 | engine | 边界 | 是 | 空字符串输入返回 None | FR-3.4 / 边界 |
| BB-K002 | engine | 边界 | 是 | 纯空白输入返回 None | FR-3.4 / 边界 |
| BB-K003 | engine | 边界 | 是 | 孤立分号输入返回 None | FR-3.4 / 边界 |
| BB-K004 | engine | 边界 | 是 | 单 VARCHAR 列 4000 字符可存可回读 | 行容量上限 |
| BB-K005 | engine | 边界 | 是 | 单 VARCHAR 列 4080 字符恰可容纳 | 行容量上限 |
| BB-K006 | engine | 边界 | 是 | 单 VARCHAR 列 4090 字符超页被拒绝 | 行容量上限 |
| BB-K007 | engine | 边界 | 是 | 双 VARCHAR 大列组合行仍可容纳 | 行容量上限 |
| BB-K008 | engine | 边界 | 是 | 300 行跨多页插入后全部可查回 | 跨页存储 |
| BB-K009 | engine | 边界 | 是 | 60 层括号嵌套 WHERE 不崩溃 | 语法深度 |
| BB-K010 | engine | 边界 | 是 | 单次脚本执行 200 条 INSERT | 批处理规模 |
| BB-K011 | engine | 边界 | 是 | 一次建 25 张表并全部登记 | 目录规模 |
| BB-K012 | engine | 边界 | 是 | 5000 字符字符串超行容量被拒绝 | 行容量上限 |
| BB-K013 | engine | 边界 | 是 | 100 字符标识符可建可查 | 标识符长度 |
| BB-K014 | engine | 边界 | 是 | 单列单行表从空到首行 | 最小规模 |
| BB-K015 | engine | 边界 | 是 | \r\n 与制表符混合分隔的 SQL 正常执行 | 格式健壮性 |
| BB-K016 | engine | 边界 | 是 | 大数值浮点 123456.789 往返一致 | 浮点精度 |
| BB-K017 | engine | 边界 | 是 | 空表带 WHERE 查询返回空集不报错 | 空表查询 |
| BB-K018 | engine | 边界 | 是 | 对已清空表重复 DELETE 安全返回 0 | 重复删除 |
| BB-K019 | engine | 边界 | 是 | 四类列型整行往返一致 | 数据保真 |
| BB-K020 | engine | 边界 | 是 | 640 字长中文串入库回读一致 | 中文字符串长度 |
| BB-L001 | cli | CLI | - | 批处理脚本成功执行并回显结果 | FR-3.4 / SRS 5.1 |
| BB-L002 | cli | CLI | - | 批处理中未知表错误返回码 1 且打印错误 | FR-3.4 |
| BB-L003 | cli | CLI | - | 批处理中类型错误返回码 1 且打印错误 | FR-3.4 |
| BB-L004 | cli | CLI | 是 | 批处理中 INT 溢出打印 RowTooLarge | FR-3.4 / 缺陷#1 |
| BB-L005 | cli | CLI | - | REPL 输入 SQL 与 quit 正常退出 | SRS 5.1 |
| BB-L006 | cli | CLI | 是 | REPL 词法错误打印不崩溃 | FR-3.4 |
| BB-L007 | cli | CLI | - | REPL tables 命令列出表结构 | SRS 5.1 |
| BB-L008 | cli | CLI | - | REPL stats 命令输出缓存统计 | SRS 5.1 |
| BB-L009 | cli | CLI | 是 | FIFO 策略 + 容量 1 的批处理可运行 | main.py 参数 |
| BB-L010 | cli | CLI | - | 批处理文件缺失返回码 1 | FR-3.4 |
| BB-L011 | cli | CLI | - | 批处理删除流程输出正确 | FR-3.5 |
| BB-L012 | cli | CLI | - | 脚本末句无分号宽容执行并统计语句数 | FR-3.4 |
| BB-L013 | cli | CLI | - | REPL exit 别名退出 | SRS 5.1 |
| BB-M001 | web | Web | - | 健康检查返回 200 与状态 ok | SRS 2.3 |
| BB-M002 | web | Web | - | 首页返回 200 | SRS 2.3 |
| BB-M003 | web | Web | - | API 建表返回 200 与 OK | SRS 2.3 |
| BB-M004 | web | Web | - | API 插入返回影响行数 | SRS 2.3 |
| BB-M005 | web | Web | - | API 全链路：建表→插入→查询 | SRS 2.3 |
| BB-M006 | web | Web | 是 | API 空表查询返回列头与空行 | SRS 2.3 |
| BB-M007 | web | Web | - | API 未知表错误返回 400 与结构化错误 | FR-3.4 |
| BB-M008 | web | Web | - | API 重复建表返回 400 | FR-3.4 |
| BB-M009 | web | Web | 是 | API INT 溢出返回 400 而非 500 | 缺陷#1 |
| BB-M010 | web | Web | 是 | API 空 SQL 返回 EMPTY | SRS 2.3 |
| BB-M011 | web | Web | - | API 缺 sql 字段按空 SQL 处理 | SRS 2.3 |
| BB-M012 | web | Web | 是 | API 非 JSON 请求体按空 SQL 处理 | SRS 2.3 |
| BB-M013 | web | Web | - | GET /api/tables 列出全部表 | FR-3.3 |
| BB-M014 | web | Web | - | GET /api/stats 返回运行统计 | FR-2.2 |
| BB-M015 | web | Web | - | 未知 API 路由返回 404 | SRS 2.3 |
| BB-M016 | web | Web | - | API 查询返回 NULL 与浮点 JSON 值 | SRS 2.3 |
