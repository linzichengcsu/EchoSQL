"""页式存储模型(FR-2.1)。

页(Page)是磁盘 I/O 的最小单位,本系统固定 4KB(见 SRS 1.3 / 2.4)。
本模块只描述"页"这一逻辑/物理单元及其基本工具函数:

    Page        一页数据(page_id + 4KB 可变内容 + 脏标记)
    PAGE_SIZE   页大小常量(4096 字节)
    META_PAGE_ID 页表页编号(0,保留给 FileManager 的元数据)
    split_into_pages / combine_pages  大块数据的跨页分段/还原(TC-ST-02)

页的分配/释放/磁盘读写由 file_manager 负责(本模块不含 I/O)。
"""

import struct
from typing import List

from .errors import DataTooLarge

__all__ = [
    "PAGE_SIZE",
    "META_PAGE_ID",
    "PAGE_HEADER",
    "PAGE_HEADER_SIZE",
    "Page",
    "split_into_pages",
    "combine_pages",
]

#: 每页固定 4KB(4096 字节)。
PAGE_SIZE = 4096

#: 页表页编号:文件第 0 页保留,用于持久化空闲页位图等元数据(FR-2.4)。
META_PAGE_ID = 0

#: 页表页头部格式:大端无符号 32 位 page_count + free_count(共 8 字节)。
PAGE_HEADER = ">II"
PAGE_HEADER_SIZE = struct.calcsize(PAGE_HEADER)  # 8


class Page:
    """内存中的一页:page_id + 4KB 数据 + 脏标记。

    用法:
        page = Page(3, bytearray(PAGE_SIZE))
        page.data[0:4] = b"test"
        page.mark_dirty()
    """

    __slots__ = ("page_id", "data", "dirty")

    def __init__(self, page_id: int, data=None):
        self.page_id = page_id
        if data is None:
            self.data = bytearray(PAGE_SIZE)
        else:
            if len(data) > PAGE_SIZE:
                raise DataTooLarge(
                    "data of %d bytes exceeds page size %d" % (len(data), PAGE_SIZE)
                )
            self.data = bytearray(data)
            # 不足一页自动补零,保证物理页恒为 4KB
            if len(self.data) < PAGE_SIZE:
                self.data.extend(b"\x00" * (PAGE_SIZE - len(self.data)))
        self.dirty = False

    def mark_dirty(self) -> None:
        """标记本页为脏页(修改后须调用,以便 Checkpoint 刷盘)。"""
        self.dirty = True

    def __len__(self):
        return PAGE_SIZE

    def __repr__(self):
        return "Page(id=%d, dirty=%s, len=%d)" % (self.page_id, self.dirty, len(self.data))


def split_into_pages(data: bytes, page_size: int = PAGE_SIZE) -> List[bytes]:
    """将任意长度数据按页大小分段,返回多个不超过 page_size 的字节块。

    配合多个页的分配/写入实现"超页大小数据正确跨页存储"(TC-ST-02)。
    空数据返回单个空块,保证至少占用一页。
    """
    if not data:
        return [b""]
    return [data[i:i + page_size] for i in range(0, len(data), page_size)]


def combine_pages(chunks: List[bytes]) -> bytes:
    """将 split_into_pages 产生的分段按序还原为原始数据。"""
    return b"".join(chunks)
