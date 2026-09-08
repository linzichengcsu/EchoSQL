"""存储系统模块（对应 SRS FR-2.1 ~ FR-2.4）。

页式存储 + 缓存管理，模拟磁盘 I/O：
    page.py         页式存储模型（固定 4KB 页），read_page / write_page（FR-2.1）
    buffer.py       页缓存与替换策略（LRU / FIFO），get_page / flush_page（FR-2.2）
    file_manager.py 磁盘文件管理与空闲页列表（FR-2.3 / FR-2.4）

约束：每页固定 4KB；页编号唯一；脏页按 Checkpoint 刷盘，重启后数据不丢失。
"""
