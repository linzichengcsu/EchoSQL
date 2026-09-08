"""磁盘文件管理(FR-2.3 / FR-2.4)。

把数据库文件(data/minidb.db)组织为固定 4KB 页的线性地址空间,
负责:
    - 页的分配 / 释放(空闲页列表,位图形式)
    - 页的磁盘读写(read_page / write_page,模拟磁盘 I/O)
    - 页表持久化:页表(页数 + 空闲位图)保存在保留页 0,
      每次分配/释放即时写回,保证重启后数据与页表不丢失(FR-2.4)。

页 0 布局(4KB):
    +0  8 字节   struct ">II": page_count, free_count
    +8  N 字节   空闲位图(第 i 位 = 1 表示页 i 空闲;N = ceil(page_count/8))
    其余        全零填充

位图容量:页表页可表示 (4096-8)*8 = 32704 个页(教学原型量级充足),
超出抛 PageTableFull。
"""

import os
import struct
from typing import Optional

from .errors import (
    DataTooLarge,
    InvalidPageId,
    PageNotAllocated,
    PageOutOfRange,
    PageTableFull,
)
from .page import PAGE_HEADER, PAGE_HEADER_SIZE, PAGE_SIZE, META_PAGE_ID

__all__ = ["FileManager", "DEFAULT_DB_FILENAME"]

DEFAULT_DB_FILENAME = "minidb.db"


class FileManager:
    """管理数据库文件的页式读写与页表(空闲页位图)。

    用法:
        fm = FileManager("data")          # 打开/创建 data/minidb.db
        pid = fm.allocate_page()          # 分配一个 4KB 页
        fm.write_page(pid, b"hello")
        data = fm.read_page(pid)          # 4KB 字节(不足补零)
        fm.release_page(pid)              # 释放,页可被再分配
        fm.close()                        # 关闭前写回页表
    """

    def __init__(self, data_dir: str = "data", filename: str = DEFAULT_DB_FILENAME):
        self.data_dir = data_dir
        self.filename = filename
        self.path = os.path.join(data_dir, filename)
        os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(self.path):
            # 首次使用:创建空数据文件,后续以 r+b 读写
            with open(self.path, "wb"):
                pass

        self._file = open(self.path, "r+b")
        if os.path.getsize(self.path) == 0:
            # 新数据库:初始化页表(仅页 0 占用,无空闲页)
            self.page_count = 1
            self.free_count = 0
            self._bitmap = bytearray(self._bitmap_len())
            self._store_meta()
        else:
            self._load_meta()

    # ------------------------------------------------------------------
    # 页表(页 0)读写
    # ------------------------------------------------------------------

    def _bitmap_len(self) -> int:
        """空闲位图字节数:每页 1 bit。"""
        return (self.page_count + 7) // 8

    def _bitmap_bytes(self) -> bytes:
        return bytes(self._bitmap)

    def _store_meta(self) -> None:
        """把页表(page_count + free_count + 位图)写回页 0,并落盘。"""
        bitmap = self._bitmap_bytes()
        if PAGE_HEADER_SIZE + len(bitmap) > PAGE_SIZE:
            raise PageTableFull(
                "page table exceeds page 0 capacity (page_count=%d)" % self.page_count
            )
        payload = struct.pack(PAGE_HEADER, self.page_count, self.free_count) + bitmap
        payload += b"\x00" * (PAGE_SIZE - len(payload))
        self._file.seek(META_PAGE_ID * PAGE_SIZE)
        self._file.write(payload)
        self._file.flush()

    def _load_meta(self) -> None:
        """打开数据库时从页 0 恢复页表。"""
        self._file.seek(META_PAGE_ID * PAGE_SIZE)
        header = self._file.read(PAGE_HEADER_SIZE)
        if len(header) != PAGE_HEADER_SIZE:
            raise IOError("corrupted page table header in %s" % self.path)
        self.page_count, self.free_count = struct.unpack(PAGE_HEADER, header)
        bitmap_len = (self.page_count + 7) // 8
        rest = self._file.read(bitmap_len)
        if len(rest) != bitmap_len:
            raise IOError("corrupted page bitmap in %s" % self.path)
        self._bitmap = bytearray(rest)

    # ------------------------------------------------------------------
    # 空闲位图操作
    # ------------------------------------------------------------------

    def _is_free(self, page_id: int) -> bool:
        byte_idx, bit_idx = divmod(page_id, 8)
        return bool((self._bitmap[byte_idx] >> bit_idx) & 1)

    def _set_free(self, page_id: int) -> None:
        byte_idx, bit_idx = divmod(page_id, 8)
        self._bitmap[byte_idx] |= 1 << bit_idx

    def _clear_free(self, page_id: int) -> None:
        byte_idx, bit_idx = divmod(page_id, 8)
        self._bitmap[byte_idx] &= ~(1 << bit_idx)

    def _find_first_free(self) -> Optional[int]:
        """从页 1 起找第一个空闲页(页 0 保留,不可分配)。"""
        for page_id in range(1, self.page_count):
            if self._is_free(page_id):
                return page_id
        return None

    # ------------------------------------------------------------------
    # 页分配 / 释放(FR-2.1 / TC-ST-01 / TC-ST-06)
    # ------------------------------------------------------------------

    def allocate_page(self) -> int:
        """分配一个新页,返回唯一页编号。

        优先复用空闲页(TC-ST-06),否则扩展文件末尾分配新页(allocate_new_page);
        分配后立即写回页表,保证持久化。
        """
        reused = self._find_first_free()
        if reused is not None:
            self._clear_free(reused)
            self.free_count -= 1
            page_id = reused
        else:
            page_id = self.allocate_new_page()
            return page_id
        self._store_meta()
        return page_id

    def allocate_new_page(self) -> int:
        """在文件末尾强制追加分配一个全新页(不查空闲位图)。

        供需要「连续区」的上层使用(如引擎的系统目录区):
        追加的页号恒等于当前 page_count,保证按序分配时页号连续。
        """
        page_id = self.page_count
        if page_id >= (PAGE_SIZE - PAGE_HEADER_SIZE) * 8:
            raise PageTableFull(
                "page table full, cannot allocate page %d" % page_id
            )
        self.page_count += 1
        self._bitmap = bytearray(self._bitmap_len())
        # 在文件末尾预留一页全零空间,保证后续可读
        self._file.seek(page_id * PAGE_SIZE)
        self._file.write(b"\x00" * PAGE_SIZE)
        self._file.flush()
        self._store_meta()
        return page_id

    def release_page(self, page_id: int) -> None:
        """释放一个页,加入空闲列表,供后续再分配(TC-ST-06)。

        页 0(页表页)不可释放。
        """
        self._check_allocated(page_id)
        if page_id == META_PAGE_ID:
            raise InvalidPageId("page 0 is reserved for page table")
        if self._is_free(page_id):
            raise PageNotAllocated("page %d is already free" % page_id)
        self._set_free(page_id)
        self.free_count += 1
        self._store_meta()

    # ------------------------------------------------------------------
    # 页读写(FR-2.1 read_page / write_page)
    # ------------------------------------------------------------------

    def _check_allocated(self, page_id: int) -> None:
        if page_id < 0 or page_id >= self.page_count:
            raise PageOutOfRange(
                "page %d out of range (page_count=%d)" % (page_id, self.page_count)
            )
        if page_id != META_PAGE_ID and self._is_free(page_id):
            raise PageNotAllocated(
                "page %d is not allocated (released)" % page_id
            )

    def read_page(self, page_id: int) -> bytes:
        """从磁盘读取一页(4KB 字节),模拟磁盘 I/O。

        页编号必须已分配(释放后的页不可读)。
        """
        self._check_allocated(page_id)
        self._file.seek(page_id * PAGE_SIZE)
        data = self._file.read(PAGE_SIZE)
        if len(data) < PAGE_SIZE:
            raise IOError("short read on page %d in %s" % (page_id, self.path))
        return data

    def write_page(self, page_id: int, data) -> None:
        """把数据写入磁盘上的一页(模拟磁盘 I/O)。

        data 长度不得超过 PAGE_SIZE,不足自动补零;超长抛 DataTooLarge,
        上层应使用 split_into_pages 跨页分段(TC-ST-02)。
        """
        if len(data) > PAGE_SIZE:
            raise DataTooLarge(
                "data of %d bytes exceeds page size %d" % (len(data), PAGE_SIZE)
            )
        self._check_allocated(page_id)
        payload = bytes(data)
        if len(payload) < PAGE_SIZE:
            payload += b"\x00" * (PAGE_SIZE - len(payload))
        self._file.seek(page_id * PAGE_SIZE)
        self._file.write(payload)
        self._file.flush()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def close(self) -> None:
        """关闭文件前写回页表并落盘(FR-2.4 持久化)。"""
        try:
            self._store_meta()
        finally:
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def __repr__(self):
        return "FileManager(path=%s, page_count=%d, free=%d)" % (
            self.path, self.page_count, self.free_count,
        )
