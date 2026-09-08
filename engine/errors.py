"""数据库引擎运行时错误类型（FR-3.x 健壮性）。

与 sql_compiler.errors（编译期错误）和 storage.errors（存储错误）分层：
- 编译错误（词法/语法/语义）由 sql_compiler 抛出，格式 [类型, 行:列, 原因]；
- 存储错误（页级）由 storage 抛出，格式 [StorageError, 原因]；
- 本模块为引擎运行时错误（如行超页、目录损坏），格式 [EngineError, 原因]。

所有错误均继承 Exception，保证非法输入 / 异常状态不崩溃（可被捕获）。
"""

__all__ = ["EngineError", "RowTooLarge", "CatalogCorrupted"]


class EngineError(Exception):
    """引擎运行时错误基类。"""

    kind = "EngineError"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return "[%s, %s]" % (self.kind, self.message)


class RowTooLarge(EngineError):
    """单行数据超过一页容量，无法存储（FR-3.2 边界）。"""

    kind = "RowTooLarge"


class CatalogCorrupted(EngineError):
    """系统目录数据损坏或格式非法（FR-3.3 健壮性）。"""

    kind = "CatalogCorrupted"
