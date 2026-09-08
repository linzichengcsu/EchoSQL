"""编译期模式目录 Catalog(FR-1.3)。

维护表名、列名、列类型等元数据,供语义分析做名字解析与类型检查。

接口(与 SRS 3.2.3 一致):
    create_table(name, columns) -> None        注册新表(重名报 TableAlreadyExists)
    find_table(name) -> TableInfo | None       按表名查询
    find_column(table, col) -> ColumnInfo|None 按表/列名查询
    get_type(table, col) -> str | None         获取列类型

说明:
- 表名 / 列名大小写不敏感,统一转小写存储与查找;
- 本 Catalog 为编译期(内存)目录,运行时持久化目录见 engine.catalog_manager(P4);
- 未注册表返回 None,由 semantic 层抛出 UnknownTable。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .errors import TableAlreadyExists

__all__ = ["ColumnInfo", "TableInfo", "Catalog"]


@dataclass(frozen=True)
class ColumnInfo:
    """列元数据:名称 + 数据类型(INT/VARCHAR/FLOAT/CHAR)。"""

    name: str
    data_type: str


@dataclass
class TableInfo:
    """表元数据:表名 + 列定义列表 + 列名→定义索引。"""

    name: str
    columns: List[ColumnInfo]
    _index: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        for i, col in enumerate(self.columns):
            self._index[col.name.lower()] = i

    def find_column(self, col: str) -> Optional[ColumnInfo]:
        idx = self._index.get(col.lower())
        return self.columns[idx] if idx is not None else None

    def column_names(self) -> List[str]:
        """按定义顺序返回全部列名。"""
        return [c.name for c in self.columns]


class Catalog:
    """编译期模式目录:表注册 / 查询 / 类型获取。"""

    def __init__(self):
        self._tables: Dict[str, TableInfo] = {}

    # ---------- 注册 / 查询 ----------
    def create_table(self, name: str, columns: List[ColumnInfo]) -> TableInfo:
        """注册新表;若表已存在抛出 TableAlreadyExists(TC-S-05)。"""
        key = name.lower()
        if key in self._tables:
            raise TableAlreadyExists(
                0, 0, "table %r already exists" % name
            )
        info = TableInfo(name=name, columns=list(columns))
        self._tables[key] = info
        return info

    def find_table(self, name: str) -> Optional[TableInfo]:
        return self._tables.get(name.lower())

    def find_column(self, table: str, col: str) -> Optional[ColumnInfo]:
        """按表名 + 列名查询列定义;表/列不存在返回 None。"""
        info = self.find_table(table)
        if info is None:
            return None
        return info.find_column(col)

    def get_type(self, table: str, col: str) -> Optional[str]:
        """获取列类型;表/列不存在返回 None。"""
        col_info = self.find_column(table, col)
        return col_info.data_type if col_info else None

    def has_table(self, name: str) -> bool:
        return name.lower() in self._tables

    def tables(self) -> List[TableInfo]:
        """按注册顺序返回全部表(用于测试与调试)。"""
        return list(self._tables.values())
