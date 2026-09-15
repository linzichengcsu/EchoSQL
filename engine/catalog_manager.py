"""系统目录管理（FR-3.3）。

维护元数据（表名、列名、列类型、表数据页集合），并把系统目录作为
「特殊表」经存储引擎持久化到磁盘（类似 pg_catalog / sqlite_master）：

    - 目录区固定占用文件开头连续 16 页（页 1~16，页 0 为存储层页表保留），
      新建数据库时预分配，之后永不释放、不被用户表页占用；
    - 首目录页头部 4 字节记录目录 blob 字节数（dir_size），
      blob 内容为 JSON（各表列定义 + 数据页集合），跨目录页存放；
    - 每次建表 / 删表 / 页集合变化后保存目录，程序重启后表结构与数据页
      映射不丢失（TC-E2E-05 / FR-2.4 持久性）。

对外接口（与 SRS 5.2 内部接口一致）：
    catalog          编译期目录视图（供语义分析 / 计划生成使用）
    create_table     建表：注册元数据 + 初始化页集合 + 持久化
    drop_table       删表：释放数据页 + 移除元数据 + 持久化（表的回收）
    table_storage    获取表存储对象（插入 / 扫描 / 删除行）
"""

import json
import struct
from typing import Dict, List, Optional

from sql_compiler.catalog import Catalog, ColumnInfo
from storage import PAGE_SIZE, Storage

from .errors import CatalogCorrupted
from .storage_engine import TableStorage

__all__ = ["CatalogManager", "DIR_START_PAGE", "DIR_PAGES"]

#: 目录区起始页（页 0 为存储层页表保留）
DIR_START_PAGE = 1

#: 目录区固定页数(≈64KB 元数据,教学原型几十张表 / 几百列充足)
DIR_PAGES = 16

#: 目录头:首目录页前 4 字节为目录 blob 字节数(大端)
_DIR_HEADER = ">I"
_DIR_HEADER_SIZE = struct.calcsize(_DIR_HEADER)  # 4


class CatalogManager:
    """系统目录：运行时元数据 + 磁盘持久化（FR-3.3）。"""

    def __init__(self, storage: Storage):
        self._storage = storage
        #: 编译期目录视图(sql_compiler.Catalog),供 analyze / plan 使用
        self._catalog = Catalog()
        #: 表名(原始拼写,大小写敏感) -> TableStorage
        self._tables: Dict[str, TableStorage] = {}

    # ------------------------------------------------------------------
    # 目录持久化(FR-3.3:目录本身也经存储引擎读写)
    # ------------------------------------------------------------------

    def load(self) -> None:
        """从磁盘加载目录(新数据库预分配空目录区;损坏抛 CatalogCorrupted)。"""
        self._ensure_dir_region()
        head = self._storage.read_page(DIR_START_PAGE)
        (dir_size,) = struct.unpack_from(_DIR_HEADER, head, 0)
        if dir_size == 0:
            return  # 空目录
        need_pages = (dir_size + _DIR_HEADER_SIZE + PAGE_SIZE - 1) // PAGE_SIZE
        if need_pages > DIR_PAGES:
            raise CatalogCorrupted(
                "catalog of %d bytes exceeds %d reserved pages" % (dir_size, DIR_PAGES)
            )
        buf = bytearray()
        for i in range(need_pages):
            buf += self._storage.read_page(DIR_START_PAGE + i)
        blob = bytes(buf[_DIR_HEADER_SIZE:_DIR_HEADER_SIZE + dir_size])
        try:
            data = json.loads(blob.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise CatalogCorrupted("catalog blob is not valid JSON: %s" % exc)
        if not isinstance(data, dict) or not isinstance(data.get("tables"), list):
            raise CatalogCorrupted("catalog blob has invalid structure")
        for entry in data["tables"]:
            ts = TableStorage.from_json(self._storage, entry)
            key = ts.name
            self._tables[key] = ts
            self._catalog.create_table(
                ts.name,
                [ColumnInfo(c.name, c.data_type) for c in ts.columns],
            )

    def _ensure_dir_region(self) -> None:
        """确保目录区页 1..DIR_PAGES 已分配(新库预分配 / 异常遗留补全)。"""
        fm = self._storage.fm
        while fm.page_count <= DIR_PAGES:
            fm.allocate_new_page()

    def save(self) -> None:
        """把目录(表元数据 + 页集合)写回目录区(FR-3.3 更新)。"""
        data = {"tables": [ts.to_json() for ts in self._tables.values()]}
        blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
        if len(blob) > DIR_PAGES * PAGE_SIZE - _DIR_HEADER_SIZE:
            raise CatalogCorrupted(
                "catalog of %d bytes exceeds reserved area" % len(blob)
            )
        payload = struct.pack(_DIR_HEADER, len(blob)) + blob
        need_pages = (len(payload) + PAGE_SIZE - 1) // PAGE_SIZE
        for i in range(need_pages):
            chunk = payload[i * PAGE_SIZE:(i + 1) * PAGE_SIZE]
            self._storage.write_page(DIR_START_PAGE + i, chunk)

    # ------------------------------------------------------------------
    # 编译期视图(供语义分析 / 计划生成)
    # ------------------------------------------------------------------

    @property
    def catalog(self) -> Catalog:
        return self._catalog

    def find_table(self, name: str) -> Optional[TableStorage]:
        return self._tables.get(name)

    def table_storage(self, name: str) -> TableStorage:
        ts = self._tables.get(name)
        if ts is None:
            raise CatalogCorrupted("table %r is not registered in catalog" % name)
        return ts

    def has_table(self, name: str) -> bool:
        return name in self._tables

    def table_names(self) -> List[str]:
        return [ts.name for ts in self._tables.values()]

    # ------------------------------------------------------------------
    # 目录更新(FR-3.3:初始化 / 查询 / 更新)
    # ------------------------------------------------------------------

    def create_table(self, name: str, columns: List[ColumnInfo]) -> TableStorage:
        """建表:注册元数据(若未注册)+ 初始化页集合 + 持久化目录。

        语义分析阶段已把表注册进编译期目录,此处兼容两种调用路径,
        避免重复注册报 TableAlreadyExists。
        """
        if not self._catalog.has_table(name):
            self._catalog.create_table(name, columns)
        key = name
        ts = self._tables.get(key)
        if ts is None:
            ts = TableStorage(self._storage, name, columns)
            self._tables[key] = ts
        self.save()
        return ts

    def drop_table(self, name: str) -> int:
        """删表:释放全部数据页(表的回收,FR-3.2)+ 移除元数据 + 持久化。"""
        key = name
        ts = self._tables.pop(key, None)
        if ts is None:
            return 0
        released = ts.release_all()
        self._catalog.drop_table(name)
        self.save()
        return released

    def to_dict(self) -> List[dict]:
        """目录内容(供 Web API 展示表结构)。"""
        return [ts.to_json() for ts in self._tables.values()]

    def __repr__(self):
        return "CatalogManager(tables=%d)" % len(self._tables)
