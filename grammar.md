# MiniDB SQL 子集文法（grammar.md）

> 本文件为《软件需求规约文档》要求的必提交文法文档（SRS 8 章 / 指导文档 5 章）。
> 当前处于开发环境搭建阶段（P1 之前），此处先给出文法骨架，
> 词法/语法分析器实现阶段（P2）将据此细化并同步更新本文件。

## 1. 语法记号

- 终结符大写：如 `SELECT`、`IDENTIFIER`、`INT_CONST`、`STRING`、`'('`、`';'`
- 非终结符小写：如 `statement`、`expr`
- `*` 闭包、`?` 可选、`|` 选择、`()` 分组

## 2. 语句（statement）

```
program        := statement*
statement      := create_table_stmt | insert_stmt | select_stmt | delete_stmt ';'
```

## 3. 建表语句

```
create_table_stmt := CREATE TABLE IDENTIFIER '(' column_def (',' column_def)* ')'
column_def        := IDENTIFIER data_type
data_type         := INT | VARCHAR | FLOAT | CHAR
```

## 4. 插入语句

```
insert_stmt := INSERT INTO IDENTIFIER '(' IDENTIFIER (',' IDENTIFIER)* ')'
               VALUES '(' literal (',' literal)* ')'
```

## 5. 查询语句（含 WHERE）

```
select_stmt := SELECT select_list FROM IDENTIFIER (WHERE expr)?
select_list := '*' | select_item (',' select_item)*
select_item := IDENTIFIER ('.' IDENTIFIER)?        -- 后续可扩展别名/聚合
```

## 6. 删除语句

```
delete_stmt := DELETE FROM IDENTIFIER (WHERE expr)?
```

## 7. 表达式（运算符优先级：NOT > 比较 > AND > OR，括号改变结合）

```
expr        := or_expr
or_expr     := and_expr (OR and_expr)*
and_expr    := not_expr (AND not_expr)*
not_expr    := NOT not_expr | comparison
comparison  := additive (('=' | '<>' | '<' | '<=' | '>' | '>=') additive)?
additive    := primary (('+' | '-') primary)*
primary     := literal | IDENTIFIER | '(' expr ')'
literal     := INT_CONST | FLOAT_CONST | STRING | TRUE | FALSE | NULL
```

## 8. 关键字（大小写不敏感）

`CREATE` `TABLE` `INSERT` `INTO` `VALUES` `SELECT` `FROM` `WHERE`
`DELETE` `INT` `VARCHAR` `FLOAT` `CHAR` `NOT` `AND` `OR` `TRUE` `FALSE` `NULL`

> 待定事项（SRS 9 章）：UPDATE / ORDER BY / GROUP BY / JOIN / DISTINCT 按团队能力扩展。
