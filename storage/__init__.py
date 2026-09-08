"""存储系统模块(对应 SRS FR-2.1 ~ FR-2.4)。

页式存储 + 缓存管理,模拟磁盘 I/O:
    page.py         页式存储模型(固定 4KB 页),Page / PAGE_SIZE(FR-2.1)
    file_manager.py 磁盘文件管理与页表(空闲页位图),read_page / write_page(FR-2.1/2.4)
    buffer.py       页缓存与替换策略(LRU / FIFO),get_page / flush_page(FR-2.2)
    errors.py       存储错误类型(StorageError 及子类)

统一入口(FR-2.3):Storage 门面类组合 FileManager + BufferPool,
为上层(数据库引擎)提供一致的页式存储访问接口。

约束:每页固定 4KB;页编号唯一;页 0 保留为页表页;
脏页按 Checkpoint 机制刷盘,程序重启后数据不丢失(FR-2.4)。
"""

from .buffer import BufferPool, POLICIES
from .errors import (
    StorageError,
    InvalidPageId,
    PageOutOfRange,
    PageNotAllocated,
    PageAlreadyAllocated,
    DataTooLarge,
    PageTableFull,
)
from .file_manager import DEFAULT_DB_FILENAME, FileManager
from .page import (
    PAGE_SIZE,
    META_PAGE_ID,
    Page,
    split_into_pages,
    combine_pages,
)

__all__ = [
    # 常量
    "PAGE_SIZE",
    "META_PAGE_ID",
    "DEFAULT_DB_FILENAME",
    "POLICIES",
    # 页
    "Page",
    "split_into_pages",
    "combine_pages",
    # 文件管理(FR-2.1 / FR-2.4)
    "FileManager",
    # 缓存(FR-2.2)
    "BufferPool",
    # 统一入口(FR-2.3)
    "Storage",
    # 错误类型
    "StorageError",
    "InvalidPageId",
    "PageOutOfRange",
    "PageNotAllocated",
    "PageAlreadyAllocated",
    "DataTooLarge",
    "PageTableFull",
]


class Storage:
    """存储系统统一入口(FR-2.3):组合文件管理与页缓存。

    对上层(数据库引擎)暴露页级读写、缓存命中统计与替换日志:

        st = Storage(data_dir="data", capacity=8, policy="LRU")
        pid = st.allocate_page()                 # 分配页
        st.write_page(pid, b"...")               # 写缓存并标记脏
        page = st.get_page(pid)                  # 带缓存取页
        st.flush_page(pid)                       # 单页刷盘
        st.checkpoint()                          # Checkpoint 全量刷盘
        st.stats()                               # 命中率等统计
        st.close()
    """

    def __init__(
        self,
        data_dir: str = "data",
        filename: str = DEFAULT_DB_FILENAME,
        capacity: int = 8,
        policy: str = "LRU",
        log: bool = True,
    ):
        self.fm = FileManager(data_dir, filename)
        self.bp = BufferPool(self.fm, capacity=capacity, policy=policy, log=log)

    # ---- 页分配 / 释放 / 磁盘直读(FR-2.1) ----
    def allocate_page(self) -> int:
        return self.fm.allocate_page()

    def release_page(self, page_id: int) -> None:
        self.fm.release_page(page_id)

    def read_page(self, page_id: int) -> bytes:
        """绕过缓存的磁盘直读(FR-2.1 read_page)。"""
        return self.fm.read_page(page_id)

    # ---- 带缓存访问(FR-2.2) ----
    def get_page(self, page_id: int) -> Page:
        return self.bp.get_page(page_id)

    def write_page(self, page_id: int, data) -> Page:
        return self.bp.write_page(page_id, data)

    def mark_dirty(self, page_id: int) -> None:
        self.bp.mark_dirty(page_id)

    def flush_page(self, page_id: int) -> None:
        self.bp.flush_page(page_id)

    def flush_all(self) -> int:
        return self.bp.flush_all()

    def checkpoint(self) -> int:
        """Checkpoint:全部脏页刷盘(FR-2.4),返回刷盘页数。"""
        return self.bp.checkpoint()

    # ---- 统计 / 策略 / 生命周期 ----
    @property
    def hit_rate(self) -> float:
        return self.bp.hit_rate

    @property
    def eviction_log(self):
        return self.bp.eviction_log

    def stats(self) -> dict:
        return self.bp.stats()

    def set_policy(self, policy: str) -> None:
        self.bp.set_policy(policy)

    def close(self) -> None:
        """Checkpoint 刷盘 + 写回页表并关闭文件。"""
        try:
            self.bp.flush_all()
        finally:
            self.fm.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def __repr__(self):
        return "Storage(path=%s, %s)" % (self.fm.path, self.bp)
