"""存储系统错误类型定义。

与编译器错误(errors.py)风格一致:所有错误继承自统一基类,
携带 kind 分类与人类可读 message,保证非法输入不崩溃(可被捕获)。

格式统一为:
    [StorageError] message
    [PageOutOfRange] page 99 out of range (page_count=3)
"""


class StorageError(Exception):
    """存储错误基类:携带错误类型(kind)与原因(message)。"""

    kind = "StorageError"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return "[%s] %s" % (self.kind, self.message)


class InvalidPageId(StorageError):
    """非法页编号(负数 / 保留页 0 被误操作等)。"""

    kind = "InvalidPageId"


class PageOutOfRange(StorageError):
    """页编号超出已分配范围(page_id >= page_count 或 < 0)。"""

    kind = "PageOutOfRange"


class PageNotAllocated(StorageError):
    """页未分配(读/写已释放页、释放未分配页等)。"""

    kind = "PageNotAllocated"


class PageAlreadyAllocated(StorageError):
    """页重复分配(allocate_page 拿到已占用页等,防御性错误)。"""

    kind = "PageAlreadyAllocated"


class DataTooLarge(StorageError):
    """写入数据超过单页容量(4KB),应由上层跨页分段。"""

    kind = "DataTooLarge"


class PageTableFull(StorageError):
    """页表(页 0 位图)容量耗尽,无法继续分配页。"""

    kind = "PageTableFull"
