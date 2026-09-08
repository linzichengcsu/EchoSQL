"""语法分析器(FR-1.2):递归下降,将 Token 流构造为 AST。

依据 grammar.md §2/§3:
- 支持 CREATE TABLE / INSERT / SELECT / DELETE 四类语句;
- 表达式优先级:NOT > 比较 > AND > OR,括号可显式改变结合;
- 遇语法错误抛出 ParseError(出错位置 + 期望符号),不崩溃。

对外接口(与 SRS 5.2 内部接口一致):
    parse(tokens: list[Token]) -> AST    语法分析,构造抽象语法树
"""

from .ast_nodes import (
    BOOL,
    NULL,
    BinaryExpr,
    ColumnDef,
    ColumnRef,
    CreateTableStmt,
    DeleteStmt,
    InsertStmt,
    Literal,
    NotExpr,
    Program,
    SelectStmt,
    Star,
    Statement,
)
from .errors import ParseError
from .tokens import Token, TokenType

__all__ = ["parse", "Parser"]

#: 比较运算符词素集合(grammar.md §3 comp_op)
COMPARISON_OPS = {"=", "<>", "!=", "<", "<=", ">", ">="}

#: primary 起始 Token 类型(TC-P-04 报错信息用)
_PRIMARY_START = {
    TokenType.INT_CONST, TokenType.FLOAT_CONST, TokenType.STRING,
    TokenType.IDENTIFIER, TokenType.LPAREN,
}


class Parser:
    """递归下降语法分析器。"""

    def __init__(self, tokens: list):
        self.tokens = tokens
        self.pos = 0

    # ---------- 游标工具 ----------
    def _peek(self, offset: int = 0) -> Token:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def _advance(self) -> Token:
        tok = self._peek()
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def _check(self, tok_type: TokenType) -> bool:
        return self._peek().type is tok_type

    def _match(self, tok_type: TokenType) -> bool:
        if self._check(tok_type):
            self._advance()
            return True
        return False

    def _expect(self, tok_type: TokenType, what: str) -> Token:
        tok = self._peek()
        if tok.type is not tok_type:
            raise ParseError(
                tok.line, tok.col,
                "expected %s, got %r" % (what, tok.lexeme or "end of input"),
            )
        return self._advance()

    def _expect_keyword(self, word: str) -> Token:
        tok = self._peek()
        if not (tok.type is TokenType.KEYWORD and tok.is_keyword(word)):
            raise ParseError(
                tok.line, tok.col,
                "expected keyword %s, got %r" % (word, tok.lexeme or "end of input"),
            )
        return self._advance()

    # ---------- program / statement ----------
    def parse_program(self) -> Program:
        statements = []
        while self._peek().type is not TokenType.EOF:
            statements.append(self.parse_statement())
        tok = self._peek()
        return Program(tok.line, tok.col, statements)

    def parse_statement(self) -> Statement:
        tok = self._peek()
        if tok.type is TokenType.KEYWORD:
            if tok.is_keyword("CREATE"):
                stmt = self.parse_create_table()
            elif tok.is_keyword("INSERT"):
                stmt = self.parse_insert()
            elif tok.is_keyword("SELECT"):
                stmt = self.parse_select()
            elif tok.is_keyword("DELETE"):
                stmt = self.parse_delete()
            else:
                raise ParseError(tok.line, tok.col,
                                 "expected statement (CREATE/INSERT/SELECT/DELETE), "
                                 "got keyword %r" % tok.lexeme)
        else:
            raise ParseError(tok.line, tok.col,
                             "expected statement (CREATE/INSERT/SELECT/DELETE), "
                             "got %r" % (tok.lexeme or "end of input"))
        # 语句必须以分号结束(grammar.md §2 / TC-P-05)
        self._expect(TokenType.SEMICOLON, "';'")
        return stmt

    # ---------- 建表 ----------
    def parse_create_table(self) -> CreateTableStmt:
        kw = self._expect_keyword("CREATE")
        self._expect_keyword("TABLE")
        name = self._expect(TokenType.IDENTIFIER, "table name IDENTIFIER")
        self._expect(TokenType.LPAREN, "'('")
        columns = [self.parse_column_def()]
        while self._match(TokenType.COMMA):
            columns.append(self.parse_column_def())
        self._expect(TokenType.RPAREN, "')'")
        return CreateTableStmt(kw.line, kw.col, name.lexeme, columns)

    def parse_column_def(self) -> ColumnDef:
        name = self._expect(TokenType.IDENTIFIER, "column name IDENTIFIER")
        dt = self._peek()
        if not (dt.type is TokenType.KEYWORD and dt.is_keyword("INT")
                or dt.type is TokenType.KEYWORD and dt.is_keyword("VARCHAR")
                or dt.type is TokenType.KEYWORD and dt.is_keyword("FLOAT")
                or dt.type is TokenType.KEYWORD and dt.is_keyword("CHAR")):
            raise ParseError(dt.line, dt.col,
                             "expected data type (INT/VARCHAR/FLOAT/CHAR), got %r"
                             % (dt.lexeme or "end of input"))
        self._advance()
        return ColumnDef(name.line, name.col, name.lexeme, dt.lexeme.upper())

    # ---------- 插入 ----------
    def parse_insert(self) -> InsertStmt:
        kw = self._expect_keyword("INSERT")
        self._expect_keyword("INTO")
        table = self._expect(TokenType.IDENTIFIER, "table name IDENTIFIER")
        columns = None
        if self._match(TokenType.LPAREN):
            columns = [self._expect(TokenType.IDENTIFIER, "column name IDENTIFIER").lexeme]
            while self._match(TokenType.COMMA):
                columns.append(self._expect(TokenType.IDENTIFIER, "column name IDENTIFIER").lexeme)
            self._expect(TokenType.RPAREN, "')'")
        self._expect_keyword("VALUES")
        self._expect(TokenType.LPAREN, "'('")
        values = [self.parse_literal()]
        while self._match(TokenType.COMMA):
            values.append(self.parse_literal())
        self._expect(TokenType.RPAREN, "')'")
        return InsertStmt(kw.line, kw.col, table.lexeme, columns, values)

    def parse_literal(self) -> Literal:
        tok = self._peek()
        if tok.type is TokenType.INT_CONST:
            self._advance()
            return Literal(tok.line, tok.col, int(tok.lexeme), "INT")
        if tok.type is TokenType.FLOAT_CONST:
            self._advance()
            return Literal(tok.line, tok.col, float(tok.lexeme), "FLOAT")
        if tok.type is TokenType.STRING:
            self._advance()
            return Literal(tok.line, tok.col, tok.lexeme, "VARCHAR")
        if tok.type is TokenType.KEYWORD:
            if tok.is_keyword("TRUE"):
                self._advance()
                return Literal(tok.line, tok.col, True, BOOL)
            if tok.is_keyword("FALSE"):
                self._advance()
                return Literal(tok.line, tok.col, False, BOOL)
            if tok.is_keyword("NULL"):
                self._advance()
                return Literal(tok.line, tok.col, None, NULL)
        raise ParseError(tok.line, tok.col,
                         "expected literal (const/STRING/TRUE/FALSE/NULL), got %r"
                         % (tok.lexeme or "end of input"))

    # ---------- 查询 ----------
    def parse_select(self) -> SelectStmt:
        kw = self._expect_keyword("SELECT")
        select_list = self.parse_select_list()
        self._expect_keyword("FROM")
        table = self._expect(TokenType.IDENTIFIER, "table name IDENTIFIER")
        where = None
        if self._peek().type is TokenType.KEYWORD and self._peek().is_keyword("WHERE"):
            self._advance()
            where = self.parse_expr()
        return SelectStmt(kw.line, kw.col, select_list, table.lexeme, where)

    def parse_select_list(self):
        tok = self._peek()
        if tok.type is TokenType.STAR:
            self._advance()
            return [Star(tok.line, tok.col)]
        items = [self.parse_select_item()]
        while self._match(TokenType.COMMA):
            items.append(self.parse_select_item())
        return items

    def parse_select_item(self):
        tok = self._peek()
        if tok.type is TokenType.IDENTIFIER:
            self._advance()
            return ColumnRef(tok.line, tok.col, tok.lexeme)
        raise ParseError(tok.line, tok.col,
                         "expected column IDENTIFIER, got %r"
                         % (tok.lexeme or "end of input"))

    # ---------- 删除 ----------
    def parse_delete(self) -> DeleteStmt:
        kw = self._expect_keyword("DELETE")
        self._expect_keyword("FROM")
        table = self._expect(TokenType.IDENTIFIER, "table name IDENTIFIER")
        where = None
        if self._peek().type is TokenType.KEYWORD and self._peek().is_keyword("WHERE"):
            self._advance()
            where = self.parse_expr()
        return DeleteStmt(kw.line, kw.col, table.lexeme, where)

    # ---------- 表达式(优先级:NOT > 比较 > AND > OR) ----------
    def parse_expr(self):
        return self.parse_or_expr()

    def parse_or_expr(self):
        left = self.parse_and_expr()
        while self._peek().type is TokenType.KEYWORD and self._peek().is_keyword("OR"):
            op = self._advance()
            right = self.parse_and_expr()
            left = BinaryExpr(op.line, op.col, "OR", left, right)
        return left

    def parse_and_expr(self):
        left = self.parse_not_expr()
        while self._peek().type is TokenType.KEYWORD and self._peek().is_keyword("AND"):
            op = self._advance()
            right = self.parse_not_expr()
            left = BinaryExpr(op.line, op.col, "AND", left, right)
        return left

    def parse_not_expr(self):
        tok = self._peek()
        if tok.type is TokenType.KEYWORD and tok.is_keyword("NOT"):
            self._advance()
            operand = self.parse_not_expr()
            return NotExpr(tok.line, tok.col, operand)
        return self.parse_comparison()

    def parse_comparison(self):
        left = self.parse_additive()
        tok = self._peek()
        if tok.type in (
            TokenType.EQ, TokenType.NE, TokenType.LT,
            TokenType.LE, TokenType.GT, TokenType.GE,
        ):
            op = self._advance()
            right = self.parse_additive()
            return BinaryExpr(op.line, op.col, tok.lexeme, left, right)
        return left

    def parse_additive(self):
        left = self.parse_primary()
        while self._peek().type in (TokenType.PLUS, TokenType.MINUS):
            op = self._advance()
            right = self.parse_primary()
            left = BinaryExpr(op.line, op.col, op.lexeme, left, right)
        return left

    def parse_primary(self):
        tok = self._peek()
        if tok.type is TokenType.INT_CONST:
            self._advance()
            return Literal(tok.line, tok.col, int(tok.lexeme), "INT")
        if tok.type is TokenType.FLOAT_CONST:
            self._advance()
            return Literal(tok.line, tok.col, float(tok.lexeme), "FLOAT")
        if tok.type is TokenType.STRING:
            self._advance()
            return Literal(tok.line, tok.col, tok.lexeme, "VARCHAR")
        if tok.type is TokenType.IDENTIFIER:
            self._advance()
            return ColumnRef(tok.line, tok.col, tok.lexeme)
        if tok.type is TokenType.KEYWORD:
            if tok.is_keyword("TRUE"):
                self._advance()
                return Literal(tok.line, tok.col, True, BOOL)
            if tok.is_keyword("FALSE"):
                self._advance()
                return Literal(tok.line, tok.col, False, BOOL)
            if tok.is_keyword("NULL"):
                self._advance()
                return Literal(tok.line, tok.col, None, NULL)
        if tok.type is TokenType.LPAREN:
            self._advance()
            expr = self.parse_expr()
            self._expect(TokenType.RPAREN, "')'")
            return expr
        # TC-P-04:期望 IDENTIFIER/CONST/'('/NOT
        raise ParseError(
            tok.line, tok.col,
            "expected IDENTIFIER/CONST/'('/', NOT, got %r"
            % (tok.lexeme or "end of input"),
        )


def parse(tokens: list) -> Program:
    """语法分析:Token 流 → AST(FR-1.2 / SRS 5.2)。"""
    return Parser(tokens).parse_program()
