"""词法分析器(FR-1.1)。

将 SQL 字符流切分为有序 Token 流:
- 识别关键字(大小写不敏感)、标识符、数字/字符串常量、运算符、分隔符;
- 跳过空白与注释(`--` 行注释、`/* */` 块注释);
- 字符串支持 `''` 转义,内容保持原样;
- 非法字符 / 未闭合字符串 / 非法数字 / 未闭合注释 → LexError,不崩溃。

对外接口(与 SRS 5.2 内部接口一致):
    lex(sql: str) -> list[Token]     词法分析,输出带位置的 Token 流(以 EOF 结尾)
"""

from .errors import LexError
from .tokens import KEYWORDS, Token, TokenType

__all__ = ["lex", "Lexer"]


#: 单字符运算符 → TokenType 映射
_SINGLE_OP = {
    "=": TokenType.EQ,
    "<": TokenType.LT,
    ">": TokenType.GT,
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ",": TokenType.COMMA,
    ";": TokenType.SEMICOLON,
    ".": TokenType.DOT,
}

#: 双字符运算符(优先于单字符,按最长匹配)
_TWO_CHAR_OP = {
    ">=": TokenType.GE,
    "<=": TokenType.LE,
    "<>": TokenType.NE,
    "!=": TokenType.NE,
}


class Lexer:
    """手写递归扫描的词法分析器,维护位置(行, 列)。"""

    def __init__(self, sql: str):
        self.sql = sql
        self.length = len(sql)
        self.pos = 0
        self.line = 1
        self.col = 1

    # ---------- 字符游标 ----------
    def _peek(self, offset: int = 0):
        idx = self.pos + offset
        return self.sql[idx] if idx < self.length else ""

    def _advance(self) -> str:
        """消费一个字符并更新 行/列,返回该字符。"""
        ch = self.sql[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    # ---------- 空白与注释 ----------
    def _skip_trivia(self):
        """跳过空白与注释,并检测未闭合的块注释。"""
        while self.pos < self.length:
            ch = self._peek()
            if ch in " \t\r\n":
                self._advance()
                continue
            if ch == "-" and self._peek(1) == "-":
                while self.pos < self.length and self._peek() != "\n":
                    self._advance()
                continue
            if ch == "/" and self._peek(1) == "*":
                start_line, start_col = self.line, self.col
                self._advance()  # '/'
                self._advance()  # '*'
                closed = False
                while self.pos < self.length:
                    if self._peek() == "*" and self._peek(1) == "/":
                        self._advance()
                        self._advance()
                        closed = True
                        break
                    self._advance()
                if not closed:
                    raise LexError(start_line, start_col, "unterminated block comment")
                continue
            break

    # ---------- Token 识别 ----------
    def _make(self, tok_type: TokenType, lexeme: str, line: int, col: int) -> Token:
        return Token(tok_type, lexeme, line, col)

    def _lex_identifier(self, line: int, col: int) -> Token:
        start = self.pos
        while self.pos < self.length:
            ch = self._peek()
            if ch.isalnum() or ch == "_":
                self._advance()
            else:
                break
        lexeme = self.sql[start:self.pos]
        if lexeme.upper() in KEYWORDS:
            return self._make(TokenType.KEYWORD, lexeme, line, col)
        return self._make(TokenType.IDENTIFIER, lexeme, line, col)

    def _lex_number(self, line: int, col: int) -> Token:
        """数字常量:整数或浮点;检测非法数字(12abc / 1.2.3)。"""
        start = self.pos
        while self.pos < self.length and self._peek().isdigit():
            self._advance()
        is_float = False
        if self._peek() == ".":
            # 小数点后必须是数字才算浮点;否则 '.' 留给独立 DOT
            if self._peek(1).isdigit():
                is_float = True
                self._advance()  # '.'
                while self.pos < self.length and self._peek().isdigit():
                    self._advance()
        lexeme = self.sql[start:self.pos]

        # 非法数字:数字后紧跟字母,或浮点后再次出现 '.数字'(如 1.2.3)
        nxt = self._peek()
        if nxt.isalpha() or nxt == "_":
            while self.pos < self.length and (
                self._peek().isalnum() or self._peek() in "._"
            ):
                self._advance()
            bad = self.sql[start:self.pos]
            raise LexError(line, col, "invalid number %r" % bad)
        if is_float and nxt == "." and self._peek(1).isdigit():
            while self.pos < self.length and (
                self._peek().isalnum() or self._peek() in "._"
            ):
                self._advance()
            bad = self.sql[start:self.pos]
            raise LexError(line, col, "invalid number %r" % bad)

        if is_float:
            return self._make(TokenType.FLOAT_CONST, lexeme, line, col)
        return self._make(TokenType.INT_CONST, lexeme, line, col)

    def _lex_string(self, line: int, col: int) -> Token:
        """字符串常量:单引号包裹,`''` 转义为单引号,内容保持原样。"""
        self._advance()  # 开头的 '
        chars = []
        while True:
            if self.pos >= self.length:
                raise LexError(line, col, "unterminated string")
            ch = self._advance()
            if ch == "'":
                if self._peek() == "'":  # '' 转义
                    self._advance()
                    chars.append("'")
                    continue
                break
            chars.append(ch)
        return self._make(TokenType.STRING, "".join(chars), line, col)

    def _lex_operator(self, line: int, col: int) -> Token:
        two = self.sql[self.pos:self.pos + 2]
        if two in _TWO_CHAR_OP:
            self._advance()
            self._advance()
            return self._make(_TWO_CHAR_OP[two], two, line, col)
        ch = self._advance()
        return self._make(_SINGLE_OP[ch], ch, line, col)

    # ---------- 主循环 ----------
    def tokenize(self) -> list:
        tokens = []
        while True:
            self._skip_trivia()
            if self.pos >= self.length:
                tokens.append(Token(TokenType.EOF, "", self.line, self.col))
                return tokens
            line, col = self.line, self.col
            ch = self._peek()
            if ch.isalpha() or ch == "_":
                tokens.append(self._lex_identifier(line, col))
            elif ch.isdigit():
                tokens.append(self._lex_number(line, col))
            elif ch == "'":
                tokens.append(self._lex_string(line, col))
            elif ch in _SINGLE_OP or self.sql[self.pos:self.pos + 2] in _TWO_CHAR_OP:
                tokens.append(self._lex_operator(line, col))
            else:
                raise LexError(line, col, "unexpected character %r" % ch)


def lex(sql: str) -> list:
    """词法分析:输入 SQL 文本,输出以 EOF 结尾的 Token 流(FR-1.1 / SRS 5.2)。"""
    return Lexer(sql).tokenize()
