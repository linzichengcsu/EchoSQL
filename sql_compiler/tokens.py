"""Token 与 TokenType 定义(词法分析产物,FR-1.1)。

每个 Token 包含:种别码(TokenType)、词素值(Lexeme)、行号、列号(均从 1 开始)。
关键字大小写不敏感(词素保留原始文本,比较时统一转大写)。
"""

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "TokenType",
    "Token",
    "KEYWORDS",
    "DATA_TYPE_KEYWORDS",
    "is_keyword",
]


class TokenType(Enum):
    """Token 种别码。"""

    # 关键字 / 标识符 / 常量
    KEYWORD = "KEYWORD"
    IDENTIFIER = "IDENTIFIER"
    INT_CONST = "INT_CONST"
    FLOAT_CONST = "FLOAT_CONST"
    STRING = "STRING"

    # 运算符
    EQ = "="
    NE = "<>"
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"

    # 分隔符
    LPAREN = "("
    RPAREN = ")"
    COMMA = ","
    SEMICOLON = ";"
    DOT = "."

    # 结束标记
    EOF = "EOF"


#: 保留关键字表(大写形式),识别时大小写不敏感(grammar.md §5)
KEYWORDS = frozenset({
    "CREATE", "TABLE", "INSERT", "INTO", "VALUES", "SELECT", "FROM", "WHERE",
    "DELETE", "INT", "VARCHAR", "FLOAT", "CHAR", "NOT", "AND", "OR",
    "TRUE", "FALSE", "NULL",
})

#: 数据类型关键字(grammar.md §2: data_type)
DATA_TYPE_KEYWORDS = frozenset({"INT", "VARCHAR", "FLOAT", "CHAR"})


def is_keyword(lexeme: str) -> bool:
    """判断词素是否为关键字(大小写不敏感)。"""
    return lexeme.upper() in KEYWORDS


@dataclass(frozen=True)
class Token:
    """一个词法单元:种别码 + 词素 + 位置(行, 列)。"""

    type: TokenType
    lexeme: str
    line: int
    col: int

    def __repr__(self):
        return "Token(%s, %r, %d:%d)" % (
            self.type.name, self.lexeme, self.line, self.col
        )

    def is_keyword(self, word: str) -> bool:
        """当前 Token 是否为指定关键字(大小写不敏感)。"""
        return self.type is TokenType.KEYWORD and self.lexeme.upper() == word.upper()
