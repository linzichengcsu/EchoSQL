"""抽象语法树(AST)节点定义(FR-1.2)。

依据 grammar.md §2/§3 构造。所有节点携带源位置(行, 列, 均从 1 开始),
用于语法/语义错误的精确定位。节点均为不可变 dataclass。
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union

__all__ = [
    "Program",
    "CreateTableStmt",
    "ColumnDef",
    "InsertStmt",
    "SelectStmt",
    "DeleteStmt",
    "Star",
    "ColumnRef",
    "Literal",
    "NotExpr",
    "BinaryExpr",
    "ASTNode",
    "Statement",
    "Expression",
]

# ---------- 数据类型 ----------

#: 列数据类型常量(与 grammar.md §2 data_type 对应)
INT = "INT"
VARCHAR = "VARCHAR"
FLOAT = "FLOAT"
CHAR = "CHAR"

#: 表达式求值得到的动态类型(INT/FLOAT/VARCHAR/BOOL/NULL)
BOOL = "BOOL"
NULL = "NULL"

#: 数值类型(用于数值运算/数值比较判断)
NUMERIC_TYPES = (INT, FLOAT)

# ---------- 基类 ----------


@dataclass(frozen=True)
class ASTNode:
    """AST 节点基类:携带源位置。"""

    line: int
    col: int


@dataclass(frozen=True)
class Statement(ASTNode):
    """语句节点基类。"""


@dataclass(frozen=True)
class Expression(ASTNode):
    """表达式节点基类。"""


# ---------- 语句节点 ----------


@dataclass(frozen=True)
class Program(ASTNode):
    """program := statement*  (grammar.md §2)"""

    statements: List[Statement] = field(default_factory=list)


@dataclass(frozen=True)
class ColumnDef(ASTNode):
    """column_def := IDENTIFIER data_type"""

    name: str
    data_type: str


@dataclass(frozen=True)
class CreateTableStmt(Statement):
    """create_table_stmt := CREATE TABLE IDENTIFIER '(' column_def (',' column_def)* ')'"""

    table: str
    columns: List[ColumnDef]


@dataclass(frozen=True)
class InsertStmt(Statement):
    """insert_stmt := INSERT INTO IDENTIFIER column_list? VALUES row (',' row)*
    row      := '(' literal (',' literal)* ')'

    columns 为 None 表示省略列清单(按表定义列序);
    rows 为多行字面量,每个元素是一行的 literal 列表(单行插入时长度为 1),
    如 `VALUES (1,'a'),(2,'b')` → rows == [[1, 'a'], [2, 'b']]。
    """

    table: str
    columns: Optional[List[str]]
    rows: List[List["Literal"]]


@dataclass(frozen=True)
class SelectStmt(Statement):
    """select_stmt := SELECT select_list FROM IDENTIFIER (WHERE expr)?
    select_list 元素为 Star 或 ColumnRef。
    """

    select_list: List[Union["Star", "ColumnRef"]]
    table: str
    where: Optional[Expression]


@dataclass(frozen=True)
class DeleteStmt(Statement):
    """delete_stmt := DELETE FROM IDENTIFIER (WHERE expr)?"""

    table: str
    where: Optional[Expression]


# ---------- 表达式 / 投影节点 ----------


@dataclass(frozen=True)
class Star(ASTNode):
    """select_list 中的 '*'。"""


@dataclass(frozen=True)
class ColumnRef(Expression):
    """列引用:primary := IDENTIFIER"""

    name: str


@dataclass(frozen=True)
class Literal(Expression):
    """字面量:INT_CONST / FLOAT_CONST / STRING / TRUE / FALSE / NULL
    data_type 取值:INT / FLOAT / VARCHAR / BOOL / NULL。
    """

    value: object
    data_type: str


@dataclass(frozen=True)
class NotExpr(Expression):
    """not_expr := NOT not_expr"""

    operand: Expression


@dataclass(frozen=True)
class BinaryExpr(Expression):
    """二元表达式:AND/OR/比较运算/加减。
    op 为运算符词素,如 'AND'、'OR'、'='、'>='、'+'、'-'。
    """

    op: str
    left: Expression
    right: Expression
