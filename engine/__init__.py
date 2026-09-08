"""数据库引擎模块（对应 SRS FR-3.1 ~ FR-3.5）。

    executor.py         执行引擎：CreateTable / Insert / SeqScan / Filter / Project 算子
    storage_engine.py   存储引擎：Row<->Page 序列化、空闲页管理、表扩展与回收
    catalog_manager.py  系统目录：元数据以系统表形式持久化（类似 pg_catalog）

引擎向上对接 SQL 编译器产出的逻辑执行计划，向下调用 storage 的页式存储接口。
"""
