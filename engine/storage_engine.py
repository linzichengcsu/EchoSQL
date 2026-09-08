"""存储引擎（FR-3.2）。

位于页式存储之上，负责把「表 / 行」映射到「页 / 槽」：

    RowPage       槽页（Slotted Page）：页头 + 槽数组 + 行数据（SRS 第 6 章数据需求）
    encode_row / decode_row   Row 与二进制数据的序列化 / 反序列化
    TableStorage  单表的页集合管理：插入（自动扩展新页）、顺序扫描、
                  删除（删除标记 + 整页回收）、释放全部页

页布局（4KB，SRS 第 6 章：页内含页头、槽、行数据、空闲空间）：
    +0    8B  页头 ">HHHH": slot_count, free_off, free_len, flags
    +8    4B×N 槽数组，每个槽 ">HH": (行偏移 offset, 行长度 length)
    ...   空闲区（从页尾向头部增长，插入行时占用）
    行删除采用删除标记：槽偏移置为 TOMBSTONE(0xFFFF)，行空间暂不回收；
    页内所有行被删除后整页释放（表的页集合回收）。

行编码（自描述 tag + payload，任意列类型组合）：
    INT     -> 0x00 + ">i"   4B 大端
    FLOAT   -> 0x01 + ">d"   8B 大端
    VARCHAR -> 0x02 + ">H" 长度 + UTF-8 字节
    NULL    -> 0x03
"""

import struct
from typing import Iterator, List, Optional, Tuple

from sql_compiler.catalog import ColumnInfo
from storage import PAGE_SIZE, Storage

from .errors import EngineError, RowTooLarge

__all__ = [
    "TOMBSTONE",
    "RowPage",
    "encode_row",
    "decode_row",
    "TableStorage",
]

# ----------------------------------------------------------------------
# 槽页结构常量
# ----------------------------------------------------------------------

#: 页头格式：槽数、空闲区起点、空闲长度、标志（保留）
_PAGE_HEADER = ">HHHH"
_PAGE_HEADER_SIZE = struct.calcsize(_PAGE_HEADER)  # 8

#: 槽格式：行偏移、行长度
_SLOT_FMT = ">HH"
_SLOT_SIZE = struct.calcsize(_SLOT_FMT)  # 4

#: 删除标记：槽偏移为该值时表示行已被删除（tombstone）
TOMBSTONE = 0xFFFF

#: 行编码 tag
_TAG_INT = 0
_TAG_FLOAT = 1
_TAG_STRING = 2
_TAG_NULL = 3


# ----------------------------------------------------------------------
# RowPage：槽页
# ----------------------------------------------------------------------


class RowPage:
    """一页内的行集合（Slotted Page 结构，SRS 第 6 章）。

    用法：
        rp = RowPage()                 # 全新空页
        slot = rp.insert(b"row-data")  # 返回槽号；页满返回 None
        raw = rp.get(slot)             # 读取行字节；已删除返回 None
        rp.delete(slot)                # 删除标记
        data = rp.encode()             # 编码为整页 4KB 字节（写盘/写缓存）
        rp2 = RowPage.decode(data)     # 从整页字节还原
    """

    __slots__ = ("_data", "slots", "free_off", "free_len", "flags")

    def __init__(self):
        self._data = bytearray(PAGE_SIZE)
        self.slots: List[Tuple[int, int]] = []          # [(offset, length), ...]
        self.free_off: int = PAGE_SIZE                   # 空闲区起点（数据从页尾向下写）
        self.free_len: int = PAGE_SIZE - _PAGE_HEADER_SIZE
        self.flags: int = 0

    # ---------- 页头 / 槽区 ----------

    def _slots_bytes(self) -> int:
        """槽数组占用的字节数。"""
        return len(self.slots) * _SLOT_SIZE

    def _available(self) -> int:
        """当前空闲字节数（含未来槽位所需空间）。"""
        return self.free_off - (_PAGE_HEADER_SIZE + self._slots_bytes())

    @property
    def slot_count(self) -> int:
        return len(self.slots)

    @property
    def active_count(self) -> int:
        """未删除的行数。"""
        return sum(1 for off, _ in self.slots if off != TOMBSTONE)

    # ---------- 行操作 ----------

    def insert(self, payload: bytes) -> Optional[int]:
        """向页内追加一行，返回槽号；页满返回 None（由上层分配新页）。"""
        need = len(payload) + _SLOT_SIZE
        if need > self._available():
            return None
        self.free_off -= len(payload)
        self._data[self.free_off:self.free_off + len(payload)] = payload
        self.slots.append((self.free_off, len(payload)))
        self.free_len = self._available()
        return len(self.slots) - 1

    def get(self, slot: int) -> Optional[bytes]:
        """读取指定槽的行字节；槽已被删除返回 None。"""
        if slot < 0 or slot >= len(self.slots):
            raise EngineError("slot %d out of range" % slot)
        offset, length = self.slots[slot]
        if offset == TOMBSTONE:
            return None
        return bytes(self._data[offset:offset + length])

    def delete(self, slot: int) -> None:
        """删除标记（tombstone）：行空间暂不回收，扫描时跳过。"""
        if slot < 0 or slot >= len(self.slots):
            raise EngineError("slot %d out of range" % slot)
        offset, length = self.slots[slot]
        if offset != TOMBSTONE:
            self.slots[slot] = (TOMBSTONE, length)

    def compact(self) -> "RowPage":
        """压缩：把未删除行按序重写为紧凑的新页（回收行空间）。"""
        new_page = RowPage()
        for slot in range(len(self.slots)):
            raw = self.get(slot)
            if raw is not None:
                new_page.insert(raw)
        return new_page

    # ---------- 编解码 ----------

    def encode(self) -> bytes:
        """编码为整页 4KB 字节（页头 + 槽数组 + 数据区）。"""
        self.free_len = self._available()
        struct.pack_into(
            _PAGE_HEADER, self._data, 0,
            len(self.slots), self.free_off, self.free_len, self.flags,
        )
        for i, (offset, length) in enumerate(self.slots):
            struct.pack_into(
                _SLOT_FMT, self._data, _PAGE_HEADER_SIZE + i * _SLOT_SIZE,
                offset, length,
            )
        return bytes(self._data)

    @classmethod
    def decode(cls, raw: bytes) -> "RowPage":
        """从整页字节还原 RowPage。

        对「全新空页」（全零，页头 free_off=0）宽容处理为标准空页，
        保证新分配页（复用页也先清零）可直接插入。
        """
        if len(raw) != PAGE_SIZE:
            raise EngineError("page data must be %d bytes, got %d" % (PAGE_SIZE, len(raw)))
        slot_count, free_off, free_len, flags = struct.unpack_from(_PAGE_HEADER, raw, 0)
        if slot_count == 0 and free_off == 0:
            free_off = PAGE_SIZE
            free_len = PAGE_SIZE - _PAGE_HEADER_SIZE
        page = cls.__new__(cls)
        page._data = bytearray(raw)
        page.slots = [
            struct.unpack_from(_SLOT_FMT, raw, _PAGE_HEADER_SIZE + i * _SLOT_SIZE)
            for i in range(slot_count)
        ]
        page.free_off = free_off
        page.free_len = free_len
        page.flags = flags
        return page

    def __repr__(self):
        return "RowPage(slots=%d, active=%d, free=%dB)" % (
            len(self.slots), self.active_count, self._available(),
        )


# ----------------------------------------------------------------------
# Row 序列化（FR-3.2：Row 与 Page 的序列化 / 反序列化方法）
# ----------------------------------------------------------------------


def encode_row(values: List[object]) -> bytes:
    """把一行值序列化为二进制（自描述 tag + payload）。

    values 中 None 表示 NULL；数值按 Python 类型编码为 INT/FLOAT；
    其余（字符串等）按 UTF-8 变长字符串编码。
    """
    buf = bytearray()
    for value in values:
        if value is None:
            buf.append(_TAG_NULL)
        elif isinstance(value, bool):
            buf.append(_TAG_INT)
            buf += struct.pack(">i", 1 if value else 0)
        elif isinstance(value, int):
            buf.append(_TAG_INT)
            buf += struct.pack(">i", value)
        elif isinstance(value, float):
            buf.append(_TAG_FLOAT)
            buf += struct.pack(">d", value)
        else:
            data = str(value).encode("utf-8")
            if len(data) > 0xFFFF:
                raise RowTooLarge("string value of %d bytes exceeds 65535" % len(data))
            buf.append(_TAG_STRING)
            buf += struct.pack(">H", len(data))
            buf += data
    if len(buf) > PAGE_SIZE - _PAGE_HEADER_SIZE - _SLOT_SIZE:
        raise RowTooLarge("row of %d bytes cannot fit one page" % len(buf))
    return bytes(buf)


def decode_row(data: bytes) -> List[object]:
    """反序列化一行：还原为 Python 值列表（NULL 为 None）。"""
    out: List[object] = []
    pos = 0
    n = len(data)
    while pos < n:
        tag = data[pos]
        pos += 1
        if tag == _TAG_NULL:
            out.append(None)
        elif tag == _TAG_INT:
            if pos + 4 > n:
                raise EngineError("corrupted row: truncated INT")
            out.append(struct.unpack_from(">i", data, pos)[0])
            pos += 4
        elif tag == _TAG_FLOAT:
            if pos + 8 > n:
                raise EngineError("corrupted row: truncated FLOAT")
            out.append(struct.unpack_from(">d", data, pos)[0])
            pos += 8
        elif tag == _TAG_STRING:
            if pos + 2 > n:
                raise EngineError("corrupted row: truncated string length")
            (length,) = struct.unpack_from(">H", data, pos)
            pos += 2
            if pos + length > n:
                raise EngineError("corrupted row: truncated string body")
            out.append(data[pos:pos + length].decode("utf-8"))
            pos += length
        else:
            raise EngineError("corrupted row: unknown tag %d" % tag)
    return out


# ----------------------------------------------------------------------
# TableStorage：单表页集合管理
# ----------------------------------------------------------------------


class TableStorage:
    """一张表的数据存储：行经序列化写入页集合，支持扩展与回收（FR-3.2）。

        ts = TableStorage(storage, "student", columns)
        ts.insert_row([1, "Alice", 20])      # 返回是否扩展了新页
        for pid, slot, values in ts.scan():  # 顺序扫描全部行
            ...
        ts.delete_row(pid, slot)             # 删除标记；页空则整页回收
        ts.release_all()                     # 释放全部页（删表）
    """

    def __init__(self, storage: Storage, name: str, columns: List[ColumnInfo]):
        self._storage = storage
        self.name = name
        self.columns = list(columns)
        self._pages: List[int] = []

    # ---------- 页集合 ----------

    def page_ids(self) -> List[int]:
        return list(self._pages)

    def set_pages(self, pages: List[int]) -> None:
        self._pages = list(pages)

    def add_page(self, page_id: int) -> None:
        self._pages.append(page_id)

    def remove_page(self, page_id: int) -> bool:
        try:
            self._pages.remove(page_id)
            return True
        except ValueError:
            return False

    # ---------- 行操作（FR-3.2 组织 / 存储 / 访问表数据） ----------

    def insert_row(self, values: List[object]) -> bool:
        """插入一行；返回是否扩展了新页（页集合变化需持久化目录）。

        先尝试在已有页中找到空闲槽（从前往后，按页序填充），
        全部满页则分配新页扩展表（FR-3.2 表的扩展）。
        """
        payload = encode_row(values)
        for page_id in list(self._pages):
            page = self._storage.get_page(page_id)
            rp = RowPage.decode(page.data)
            slot = rp.insert(payload)
            if slot is not None:
                page.data = rp.encode()
                self._storage.mark_dirty(page_id)
                return False
        # 全满 → 分配新页（复用页先清零，避免残留旧数据）
        page_id = self._storage.allocate_page()
        self._pages.append(page_id)
        rp = RowPage()
        if rp.insert(payload) is None:  # pragma: no cover - 理论上不可能
            self._pages.pop()
            self._storage.release_page(page_id)
            raise RowTooLarge("row cannot fit a fresh page")
        self._storage.write_page(page_id, rp.encode())
        return True

    def scan(self) -> Iterator[Tuple[int, int, List[object]]]:
        """顺序扫描全部行，产出 (page_id, slot, values)。"""
        for page_id in list(self._pages):
            page = self._storage.get_page(page_id)
            rp = RowPage.decode(page.data)
            for slot in range(rp.slot_count):
                raw = rp.get(slot)
                if raw is None:
                    continue
                values = decode_row(raw)
                if len(values) != len(self.columns):  # pragma: no cover - 防御损坏
                    raise EngineError(
                        "corrupted row in table %r: %d values, expect %d"
                        % (self.name, len(values), len(self.columns))
                    )
                yield page_id, slot, values

    def delete_row(self, page_id: int, slot: int) -> bool:
        """删除指定 (页, 槽) 的行；返回 True。

        若删除后页内无活动行，整页回收（释放页 + 移出页集合）。
        注意：调用方应在页扫描结束后再触发回收，避免迭代器失效。
        """
        page = self._storage.get_page(page_id)
        rp = RowPage.decode(page.data)
        rp.delete(slot)
        if rp.active_count == 0:
            self._storage.invalidate_page(page_id)
            self._storage.release_page(page_id)
            self.remove_page(page_id)
        else:
            page.data = rp.encode()
            self._storage.mark_dirty(page_id)
        return True

    def release_all(self) -> int:
        """释放本表全部数据页（删表回收，FR-3.2 表的回收），返回释放页数。"""
        count = 0
        for page_id in list(self._pages):
            self._storage.invalidate_page(page_id)
            self._storage.release_page(page_id)
            count += 1
        self._pages = []
        return count

    # ---------- 元数据（目录持久化用） ----------

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "columns": [
                {"name": c.name, "type": c.data_type} for c in self.columns
            ],
            "pages": list(self._pages),
        }

    @classmethod
    def from_json(cls, storage: Storage, data: dict) -> "TableStorage":
        columns = [
            ColumnInfo(name=c["name"], data_type=c["type"]) for c in data["columns"]
        ]
        ts = cls(storage, data["name"], columns)
        ts.set_pages(data.get("pages", []))
        return ts

    def __repr__(self):
        return "TableStorage(%r, pages=%d)" % (self.name, len(self._pages))
