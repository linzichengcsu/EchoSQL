"""编译器错误类型定义。

依据 SRS 3.2 / 测试文档第 2 章,所有错误统一格式:

    [错误类型, 行:列, 原因说明]

- 词法错误:  [LexError, 1:17, unterminated string]
- 语法错误:  [ParseError, 1:20, expected IDENTIFIER, got ';']
- 语义错误:  [UnknownColumn, 1:8, column 'score' does not exist]

所有错误均继承自 SQLError(Exception),保证非法输入不崩溃(可被捕获)。
"""


class SQLError(Exception):
    """编译器错误基类:携带 错误类型 + 位置(行, 列) + 原因。"""

    kind = "SQLError"

    def __init__(self, line: int, col: int, message: str):
        super().__init__(message)
        self.line = line
        self.col = col
        self.message = message

    @property
    def position(self):
        """(行, 列) 位置元组,均从 1 开始。"""
        return self.line, self.col

    def __str__(self):
        return "[%s, %d:%d, %s]" % (self.kind, self.line, self.col, self.message)


class LexError(SQLError):
    """词法错误(FR-1.1):非法字符、未闭合字符串、非法数字、未闭合注释。"""

    kind = "LexError"


class ParseError(SQLError):
    """语法错误(FR-1.2):缺分号、括号不匹配、期望符号不满足等。"""

    kind = "ParseError"


class SemanticError(SQLError):
    """语义错误基类(FR-1.3),子类按错误类型细分。"""

    kind = "SemanticError"


class UnknownTable(SemanticError):
    kind = "UnknownTable"


class UnknownColumn(SemanticError):
    kind = "UnknownColumn"


class TableAlreadyExists(SemanticError):
    kind = "TableAlreadyExists"


class ColumnCountMismatch(SemanticError):
    kind = "ColumnCountMismatch"


class TypeMismatch(SemanticError):
    kind = "TypeMismatch"
