# MiniDB SQL 子集文法（grammar.md）

> 本文档为《软件需求规约文档》要求的必提交文法文档（SRS 第 8 章 / 技术栈指导文档第 5 章）。
> 本版本于 **P2（SQL 编译器）** 阶段细化定稿，与 `sql_compiler/` 中 Lexer / Parser 的实现严格一致；
> 实现若变更，本文件须同步更新。
>
> 语法记号：
> - 终结符大写：`SELECT`、`IDENTIFIER`、`INT_CONST`、`STRING`、`'('`、`';'`
> - 非终结符小写：`statement`、`expr`
> - `*` 闭包、`?` 可选、`|` 选择、`()` 分组

## 1. 词法（Lexical Grammar）

### 1.1 字符集与 Token 类别

输入为 UTF-8 文本，Token 共分四类：

| 类别 | Token 类型 | 示例 |
| --- | --- | --- |
| 关键字 | `KEYWORD` | `SELECT` `CREATE` `INT`（见 §5，大小写不敏感） |
| 标识符 | `IDENTIFIER` | 表名 / 列名，`[A-Za-z_][A-Za-z0-9_]*` |
| 常量 | `INT_CONST` `FLOAT_CONST` `STRING` | `18`、`3.14`、`'Alice'` |
| 运算符 / 分隔符 | `=` `<>` `!=` `<` `<=` `>` `>=` `+` `-` `*` `/` `(` `)` `,` `;` `.` | — |

每个 Token 携带：种别码（TokenType）、词素值（Lexeme）、行号、列号（均从 1 开始）。

### 1.2 词法规则

1. **空白**：空格、`\t`、`\r`、`\n` 一律跳过。
2. **注释**：
   - 行注释：`--` 至行尾；
   - 块注释：`/* ... */`，可跨行；未闭合报词法错误。
3. **关键字**：大小写不敏感（`select` / `SELECT` / `SeLeCt` 等价，均识别为 `KEYWORD`）；词素保留原始文本。
4. **标识符**：字母或 `_` 开头，后跟字母 / 数字 / `_`；大小写不敏感，名字解析时统一转为小写。
5. **数字常量**：十进制整数或浮点；浮点要求小数点两侧至少一侧有数字（如 `3.14`、`1.`、`.5` 均合法）；
   - 数字后紧跟字母（如 `12abc`）、浮点后再出现小数点且后跟数字（如 `1.2.3`）→ **非法数字**，报词法错误。
6. **字符串常量**：单引号包裹，内容保持原样（含空格与大小写）；
   - 转义：两个连续单引号 `''` 表示一个单引号（如 `'Tom''s book'` → `Tom's book`）；
   - 未闭合字符串（文件结束仍无配对 `'`）→ 词法错误。
7. **多字符运算符**：按最长匹配，`>=` `<=` `<>` `!=` 优先于 `=` `<` `>`。
8. **非法字符**（如 `@` `#` `$`、孤立 `!`）：报词法错误，给出类型 + 位置 + 原因，**不崩溃**。

### 1.3 词法错误

```
[LexError, 行:列, 原因说明]
```

示例：`[LexError, 1:17, unterminated string]`、`[LexError, 1:8, unexpected character '@']`

## 2. 语句文法（Statement Grammar）

```
program              := statement*
statement            := create_table_stmt ';'
                      | insert_stmt ';'
                      | select_stmt ';'
                      | delete_stmt ';'

create_table_stmt    := CREATE TABLE IDENTIFIER '(' column_def (',' column_def)* ')'
column_def           := IDENTIFIER data_type
data_type            := INT | VARCHAR | FLOAT | CHAR

insert_stmt          := INSERT INTO IDENTIFIER column_list? VALUES '(' literal (',' literal)* ')'
column_list          := '(' IDENTIFIER (',' IDENTIFIER)* ')'        -- 省略时按表定义列序

select_stmt          := SELECT select_list FROM IDENTIFIER (WHERE expr)?
select_list          := '*' | select_item (',' select_item)*
select_item          := IDENTIFIER

delete_stmt          := DELETE FROM IDENTIFIER (WHERE expr)?
```

说明：
- 每条语句以 `;` 结束，`program` 支持多条语句（`statement*`），也允许空输入；
- 表名 / 列名均为 `IDENTIFIER`，大小写不敏感；
- 关键字大小写不敏感。

## 3. 表达式文法（优先级：NOT > 比较 > AND > OR，括号改变结合）

```
expr        := or_expr
or_expr     := and_expr (OR and_expr)*
and_expr    := not_expr (AND not_expr)*
not_expr    := NOT not_expr | comparison
comparison  := additive (comp_op additive)?
comp_op     := '=' | '<>' | '!=' | '<' | '<=' | '>' | '>='
additive    := primary (('+' | '-') primary)*
primary     := literal | IDENTIFIER | '(' expr ')'
literal     := INT_CONST | FLOAT_CONST | STRING | TRUE | FALSE | NULL
```

优先级从高到低：`NOT` > 比较运算 > `AND` > `OR`；括号可显式改变结合。

示例：`a=1 OR b=2 AND c=3` 解析为 `a=1 OR (b=2 AND c=3)`（AND 优先于 OR）；
`NOT a=1 AND b=2` 解析为 `(NOT (a=1)) AND (b=2)`（NOT 高于比较、AND）。

## 4. 语义约束（Semantic Constraints）

### 4.1 类型系统

| 类型 | 对应字面量 / 关键字 | 说明 |
| --- | --- | --- |
| `INT` | `INT_CONST` | 32 位有符号整数 |
| `FLOAT` | `FLOAT_CONST` | 浮点数 |
| `VARCHAR` | `STRING` | 变长字符串 |
| `BOOL` | `TRUE` / `FALSE` | 布尔，仅存在于表达式中 |
| `NULL` | `NULL` | 通配类型，可与任意类型匹配 |

### 4.2 名字解析与类型检查

1. 表存在性：`CREATE` / `INSERT` / `SELECT` / `DELETE` 引用的表必须在 Catalog 中注册（CREATE 则要求**未注册**）；
2. 列存在性：投影列、WHERE 中引用的列、INSERT 列清单中的列必须属于该表；
3. `INSERT`：值数量须等于列数（指定列清单时为清单长度，否则为表全部列数），且逐列类型匹配；
4. 运算符类型规则：

| 运算符 | 要求 | 结果类型 |
| --- | --- | --- |
| `+` `-` | 两侧均为数值（INT/FLOAT） | 任一 FLOAT 则 FLOAT，否则 INT |
| `=` `<>` `!=` `<` `<=` `>` `>=` | 两侧类型兼容（INT↔FLOAT 互比、同类型互比、NULL 任意） | BOOL |
| `AND` `OR` `NOT` | 操作数为 BOOL（比较结果为 BOOL，可嵌套） | BOOL |

### 4.3 语义错误格式

```
[错误类型, 行:列, 原因说明]
```

错误类型包括：`UnknownTable`、`UnknownColumn`、`TableAlreadyExists`、
`ColumnCountMismatch`、`TypeMismatch`、`SemanticError`。

示例：`[UnknownColumn, 1:8, column 'score' does not exist]`、
`[TypeMismatch, 1:28, expected INT but got VARCHAR]`

## 5. 关键字表（大小写不敏感）

```
CREATE  TABLE  INSERT  INTO  VALUES  SELECT  FROM  WHERE  DELETE
INT  VARCHAR  FLOAT  CHAR  NOT  AND  OR  TRUE  FALSE  NULL
```

## 6. 与实现对照

| 文法条目 | 实现位置（sql_compiler/） | 状态 |
| --- | --- | --- |
| 词法规则（§1） | `lexer.py` + `tokens.py` | ✅ 已实现 |
| 语句文法（§2） | `parser.py`（递归下降） | ✅ 已实现 |
| 表达式文法（§3） | `parser.py` | ✅ 已实现 |
| 语义约束（§4） | `semantic.py` + `catalog.py` | ✅ 已实现 |
| 执行计划生成 | `planner.py`（SeqScan/Filter/Project/CreateTable/Insert/Delete） | ✅ 已实现 |

## 7. 扩展规划（SRS 第 9 章待确认事项）

以下语法特性按团队能力在后续阶段扩展，本阶段不实现：

- `UPDATE` 语句、`ORDER BY`、`GROUP BY`、`JOIN`、`DISTINCT`；
- 聚合函数（`COUNT(*)` 等）与列别名（`AS`）；
- 表达式中的 `*` `/`（乘除）与 `%` 取模；
- `FLOAT`/`VARCHAR` 的显式长度参数（如 `VARCHAR(32)`）。
