# EchoSQL / MiniDB 记录存储引擎答辩完整指南

> 本文档面向本项目当前代码版本，用于答辩准备。
> 
> 重点范围：记录存储引擎、槽页、行序列化、表页集合、系统目录、正常关闭与重启恢复。
> 
> 当前项目目录：`H:\vs_code\EchoSQL`

---

## 0. 先看结论

你负责的是数据库的“记录层”，对应需求 `FR-3.2` 和 `FR-3.3`。

这一层位于：

```text
SQL 编译器
    ↓
Executor 执行器
    ↓
TableStorage 表页集合
    ↓
RowPage 槽页
    ↓
encode_row / decode_row 行编解码
    ↓
Storage 页式存储、缓存和文件
    ↓
data/minidb.db
```

你需要掌握的核心事实只有以下几条：

1. 下层 `Storage` 只认识固定大小的 4096 字节页。
2. `RowPage` 在一个页内管理多条变长行。
3. 槽数组记录每行的 `(offset, length)`。
4. 行先通过 `encode_row()` 变成二进制，再写入槽页。
5. `TableStorage` 管理一张表使用的多个数据页。
6. 插入时优先填充旧页，旧页都放不下时才申请新页。
7. 删除先标记 `TOMBSTONE`，整页没有活动行时才释放整个页。
8. `CatalogManager` 持久化表名、列定义和数据页号列表。
9. 正常关闭时保存目录、刷写脏页和页表；重新启动时重新加载目录。
10. 当前版本没有完整实现索引、事务、WAL、并发控制和自动页内压缩。

最适合答辩的总述是：

> 我负责数据库的记录层，将 Executor 传入的逻辑行通过 Tag + Payload 编码成二进制数据，再利用 RowPage 的槽页结构组织到 4KB 数据页中；TableStorage 负责管理一张表的多个数据页，实现插入扩页、顺序扫描、删除标记和整页回收；CatalogManager 负责保存表结构和数据页映射，使数据库正常关闭后重新启动时能够恢复表和数据。

---

## 1. 当前项目真实状态

### 1.1 已经实现的功能

当前源码已经实现：

- `RowPage` 槽页结构；
- 页头、槽数组和行数据区；
- 行数据从页尾向前写入；
- `RowPage.insert()` 插入行；
- `RowPage.get()` 按槽读取行；
- `RowPage.delete()` tombstone 删除标记；
- `RowPage.compact()` 基础压缩接口；
- `RowPage.encode()` 和 `RowPage.decode()`；
- INT、FLOAT、字符串、NULL 的行编码；
- INT 32 位范围检查；
- 字符串 65535 字节限制；
- 单行不能超过一个页的限制；
- `TableStorage` 按页管理一张表；
- 插入时自动扩展数据页；
- 顺序扫描；
- 删除后整页回收；
- 删除整张表时释放所有数据页；
- 系统目录 JSON 序列化；
- 系统目录跨 4KB 页保存；
- 数据库关闭后重启恢复表和数据；
- CLI 批处理和交互式 REPL；
- `demo.sql` 端到端演示。

### 1.2 部分实现或尚未完成的功能

当前不要把下面这些功能说成“已经完整实现”：

- `compact()` 有接口，但删除后不会自动执行；
- 删除部分记录后的页内空间不会立即复用；
- SQL 批量 DELETE 主要在 `Executor._exec_delete()` 中直接处理，而不是完全通过 `TableStorage.delete_row()`；
- 整表删除主要通过 Python API `db.drop_table("t")`，不要把 `DROP TABLE t;` 说成当前 CLI 已经支持；
- 查询没有 B+ 树或哈希索引，主要采用顺序扫描；
- 没有完整事务、WAL、回滚和崩溃恢复；
- 没有并发控制、锁或 MVCC；
- 系统目录固定保留 16 页，容量有限；
- 当前机器的默认 Python 环境没有安装 pytest 和 Flask，因此自动化测试和 Web 尚未在当前环境运行；
- 目录内部字段缺失等极端损坏情况的异常包装还不完整；
- 行数据非法 UTF-8 等极端解码异常没有全部统一包装成 `EngineError`。

### 1.3 已进行的实际运行验证

核心 CLI 演示已经使用全新临时目录运行成功，退出码为 0，完成了：

```text
建表
插入 Alice、Bob、Carol
条件查询
删除 Bob
再次查询
```

跨页和重启也进行过实际验证：

```text
pages_before_close: [17, 18, 19]
rows_after_restart: 500
pages_after_delete: []
```

这说明：

- 500 行数据跨到了 3 个数据页；
- 关闭后重新打开仍然可以查回 500 行；
- 删除全部数据后，表的数据页集合变成空集合。

自动化测试当前没有执行成功的原因是环境缺少 pytest，不是已经确认测试代码失败：

```text
No module named pytest
```

---

## 2. 核心文件和源码位置

| 文件 | 当前作用 | 答辩关注点 |
|---|---|---|
| `engine/storage_engine.py` | `RowPage`、`encode_row`、`decode_row`、`TableStorage` | 你的核心文件 |
| `engine/catalog_manager.py` | 系统目录保存、加载、建表、删表 | FR-3.3 |
| `engine/errors.py` | 引擎错误类型 | 错误边界 |
| `engine/executor.py` | 执行器调用记录层 | 上下游连接 |
| `engine/__init__.py` | `Database` 统一门面 | 启动、关闭、持久化 |
| `storage/page.py` | 4KB Page 对象 | 页的基本模型 |
| `storage/file_manager.py` | 页分配、释放、页表和文件读写 | 页从哪里来 |
| `storage/buffer.py` | LRU/FIFO 缓存、脏页、刷盘 | 缓存一致性 |
| `storage/__init__.py` | Storage 统一入口 | 下层接口 |
| `tests/test_engine.py` | 记录层和持久化测试 | 功能验证 |
| `tests/test_boundary.py` | 边界和跨页测试 | 异常场景 |
| `demo.sql` | 端到端演示 SQL | 现场运行 |
| `main.py` | CLI 主入口 | 启动命令 |

### 2.1 `engine/storage_engine.py`

重点类和函数：

```text
RowPage
    insert()
    get()
    delete()
    compact()
    encode()
    decode()

encode_row()
decode_row()

TableStorage
    insert_row()
    scan()
    delete_row()
    release_all()
    to_json()
    from_json()
```

### 2.2 `engine/catalog_manager.py`

重点接口：

```text
load()
save()
create_table()
drop_table()
table_storage()
table_names()
to_dict()
```

### 2.3 `engine/executor.py`

记录层相关的执行器入口：

```text
_exec_create()
_exec_insert()
_scan_table()
_exec_delete()
```

当前版本的 `_exec_insert()` 支持一条 INSERT 中包含多行 values，并且会在所有行处理完后统一判断是否需要保存目录。

### 2.4 `engine/__init__.py`

统一数据库入口 `Database`：

```python
db = Database(data_dir="data")
db.execute("SELECT * FROM t;")
db.close()
```

启动时：

```python
self.catalog_mgr.load()
```

关闭时：

```python
self.catalog_mgr.save()
self.storage.close()
```

---

## 3. RowPage 槽页的底层逻辑

### 3.1 为什么采用槽页

表中的记录是变长的：

```text
[1, "Alice", 20]
[2, "Bob", 17]
[3, "一段较长的中文字符串", 22]
```

如果把记录简单连续放置：

- 无法通过固定偏移快速定位变长记录；
- 删除一条记录时可能需要搬移后续记录；
- 搬移后外部保存的行位置可能失效。

槽页用一个固定结构的槽数组记录每条行数据的位置：

```text
槽号 0 → offset 4070, length 20
槽号 1 → offset 4030, length 30
槽号 2 → offset 3990, length 25
```

行数据本身从页尾向前写入，槽数组从页头向后增长。

### 3.2 页内布局

每页大小是 4096 字节：

```text
偏移 0
┌────────────────────────────────────────┐
│ 页头 8 字节                             │
│ slot_count / free_off / free_len / flags │
├────────────────────────────────────────┤
│ 槽 0：offset + length                   │
│ 槽 1：offset + length                   │
│ 槽 2：offset + length                   │
├────────────────────────────────────────┤
│ 空闲区                                  │
├────────────────────────────────────────┤
│ 行数据区：从页尾向前写入                │
└────────────────────────────────────────┘
偏移 4096
```

源码中的格式：

```python
_PAGE_HEADER = ">HHHH"
_SLOT_FMT = ">HH"
TOMBSTONE = 0xFFFF
```

含义：

- `>`：大端序；
- `H`：无符号 16 位整数；
- 页头大小：4 × 2 = 8 字节；
- 槽大小：2 × 2 = 4 字节；
- `TOMBSTONE`：删除标记。

### 3.3 插入一条记录

`RowPage.insert(payload)`：

```text
1. 计算 payload 长度；
2. 为新槽额外预留 4 字节；
3. 判断槽数组和行数据区是否会碰撞；
4. 空间不足时返回 None；
5. 空间足够时 free_off 向前移动；
6. 将 payload 写到页尾方向；
7. 将 (offset, length) 加入 slots；
8. 返回新槽号。
```

空页的理论最大单行 payload 约为：

```text
4096 - 8 - 4 = 4084 字节
```

这里的 4 字节是为至少一个槽预留的空间。

### 3.4 读取一条记录

`RowPage.get(slot)`：

```text
1. 检查 slot 是否越界；
2. 读取槽中的 offset 和 length；
3. 如果 offset == TOMBSTONE，返回 None；
4. 否则读取页内指定范围的字节。
```

### 3.5 删除一条记录

删除不会立刻清除行数据，而是：

```text
原槽：        (offset, length)
删除以后：    (TOMBSTONE, length)
```

这样做的原因：

- 不用搬移其他行；
- 不影响其他槽号；
- 扫描时可以安全跳过；
- 可以把整页回收留给上层处理。

### 3.6 compact 的当前状态

`compact()` 会创建新页，把所有有效记录重新插入新页：

```text
旧页
  ├── tombstone
  ├── Alice
  └── Carol

compact()
  ↓

新页
  ├── Alice
  └── Carol
```

但是当前版本不会在每次删除后自动调用 compact。部分记录删除以后，原来的行数据空间仍然可能被占用，插入也不会自动复用 tombstone 槽。

这属于当前实现的限制，答辩时应主动说明。

---

## 4. 行序列化和反序列化

### 4.1 编码格式

`encode_row(values)` 按列顺序把一行转换为字节：

| 类型 | Tag | Payload |
|---|---:|---|
| INT | `0x00` | `>i`，4 字节大端有符号整数 |
| FLOAT | `0x01` | `>d`，8 字节大端双精度浮点数 |
| 字符串 | `0x02` | `>H` 长度 + UTF-8 字节 |
| NULL | `0x03` | 无额外 payload |

示例：

```python
[1, 2.5, "Alice", None]
```

会按以下顺序编码：

```text
INT Tag + 4 字节整数
FLOAT Tag + 8 字节浮点数
STRING Tag + 2 字节长度 + UTF-8 内容
NULL Tag
```

### 4.2 为什么要使用 Tag

因为解码器需要知道后面应该读取多少字节：

```text
Tag 0 → 读取 4 字节
Tag 1 → 读取 8 字节
Tag 2 → 先读取 2 字节长度，再读取字符串
Tag 3 → 不读取额外数据
```

这种格式是“字段值类型自描述”，但不是完整的表结构描述。表名、列名和列定义仍然保存在系统目录中。

### 4.3 编码时的边界

#### INT

合法范围：

```text
-2147483648 <= value <= 2147483647
```

超过范围抛出 `RowTooLarge`。

#### 字符串

字符串长度字段是 2 字节，所以最多 65535 字节。

注意是 UTF-8 字节数，不是 Python 字符数：

```text
ASCII 字符通常 1 字节
中文字符通常 3 字节
```

#### 整行大小

整行还要满足单页容量限制。一个字符串即使小于 65535 字节，只要整行超过约 4084 字节，仍然无法放入一个槽页。

### 4.4 解码时的检查

`decode_row(data)` 会逐个读取 Tag，并检查：

- INT 是否有完整 4 字节；
- FLOAT 是否有完整 8 字节；
- 字符串长度字段是否完整；
- 字符串 body 是否完整；
- Tag 是否是 0、1、2、3 中的一种。

发现截断或未知 Tag 时抛出 `EngineError`。

---

## 5. TableStorage 的逻辑

### 5.1 一张表保存什么

`TableStorage` 保存：

```python
self.name       # 表名
self.columns    # 列定义
self._pages     # 该表的数据页号列表
```

例如：

```text
student → [17, 18, 19]
```

表示 `student` 表的数据分布在 17、18、19 号页中。

### 5.2 插入逻辑

`TableStorage.insert_row(values)`：

```text
1. encode_row(values)；
2. 按 _pages 顺序遍历已有页；
3. Storage.get_page(page_id)；
4. RowPage.decode(page.data)；
5. RowPage.insert(payload)；
6. 成功则 page.data = rp.encode()；
7. 调用 Storage.mark_dirty(page_id)；
8. 返回 False；
9. 所有旧页都满时申请新页；
10. 将新页加入 _pages；
11. 写入第一条记录；
12. 返回 True。
```

返回值：

```text
False：使用已有页，页集合没有改变
True ：申请了新页，页集合发生改变
```

上层用这个返回值判断是否需要保存系统目录。

### 5.3 为什么插入新页后必须保存目录

假设插入前：

```text
t → [17]
```

第 17 页放满后申请第 18 页：

```text
t → [17, 18]
```

如果只把数据写入第 18 页，但不保存目录，那么重启后目录仍然可能是：

```text
t → [17]
```

扫描只读取第 17 页，导致第 18 页上的数据“存在于文件中但不可见”。

所以 `insert_row()` 返回 `True` 后，Executor 会调用 `CatalogManager.save()`。

### 5.4 顺序扫描

`TableStorage.scan()`：

```text
for page_id in _pages:
    get_page(page_id)
    RowPage.decode()
    for slot in range(slot_count):
        raw = RowPage.get(slot)
        if raw is None:
            continue
        values = decode_row(raw)
        检查字段数量
        yield (page_id, slot, values)
```

返回：

```python
(page_id, slot, values)
```

例如：

```python
(17, 0, [1, "Alice", 20])
```

`page_id` 和 `slot` 是物理定位信息，`values` 是逻辑字段值。

### 5.5 删除逻辑

底层单行接口 `TableStorage.delete_row(page_id, slot)`：

```text
1. 读取页；
2. decode 成 RowPage；
3. 将槽标记为 tombstone；
4. 如果仍有活动行：编码并标脏；
5. 如果 active_count == 0：
      invalidate_page()
      release_page()
      从 _pages 移除。
```

### 5.6 SQL DELETE 的真实实现

当前 SQL 批量 DELETE 的主路径在 `Executor._exec_delete()` 中：

```text
Executor._exec_delete()
  ↓
遍历 table.page_ids()
  ↓
逐页读取并 decode
  ↓
逐槽 decode_row
  ↓
判断 WHERE 条件
  ↓
rp.delete(slot)
  ↓
检查 active_count
  ├── 大于 0：写回并 mark_dirty
  └── 等于 0：invalidate_page + release_page
```

答辩时不要简单说“SQL DELETE 一定调用了 TableStorage.delete_row()”。准确说法是：

> TableStorage 提供了单行删除接口；SQL 的批量删除由 Executor 直接扫描和标记 tombstone，并使用相同的整页回收策略。

### 5.7 删除整张表

`release_all()` 会：

```text
遍历该表所有数据页
    ↓
invalidate_page(page_id)
    ↓
release_page(page_id)
    ↓
清空 _pages
```

之后 `CatalogManager.drop_table()` 再从运行时目录和编译期目录中移除表。

---

## 6. 系统目录 CatalogManager

### 6.1 目录和数据页的分区

```text
页 0       Storage 页表
页 1~16    系统目录保留区
页 17 起   用户数据页
```

常量：

```python
DIR_START_PAGE = 1
DIR_PAGES = 16
```

目录区总容量约为：

```text
16 × 4096 = 65536 字节 ≈ 64KB
```

目录区通过 `allocate_new_page()` 连续分配，普通用户表不应占用页 1～16。

### 6.2 目录保存的内容

每张表保存：

```text
name
columns
pages
```

示例：

```json
{
  "tables": [
    {
      "name": "student",
      "columns": [
        {"name": "id", "type": "INT"},
        {"name": "name", "type": "VARCHAR"},
        {"name": "age", "type": "INT"}
      ],
      "pages": [17, 18]
    }
  ]
}
```

### 6.3 保存格式

目录页的第一个 4 字节保存 `dir_size`，即 JSON blob 的字节数。

```text
页 1 前 4 字节：dir_size
页 1 后续内容：JSON 前半部分
页 2：JSON 中间部分
页 3：JSON 后半部分
```

保存流程：

```text
1. 遍历 _tables；
2. 对每个 TableStorage 调用 to_json()；
3. 组织成 {"tables": [...]}；
4. json.dumps(..., ensure_ascii=False)；
5. 转成 UTF-8；
6. 前面加 4 字节长度；
7. 按 4096 字节切片；
8. 写入页 1、2、3……。
```

### 6.4 加载流程

启动数据库时：

```text
Database()
  ↓
创建 Storage
  ↓
创建 CatalogManager
  ↓
CatalogManager.load()
  ↓
确保页 1~16 已分配
  ↓
读取页 1 前 4 字节
  ↓
计算需要读取的目录页数
  ↓
读取并拼接 JSON
  ↓
解析表名、列定义和 pages
  ↓
创建 TableStorage
  ↓
注册编译期 Catalog
```

### 6.5 两个 Catalog 的区别

| 内容 | 编译期 `sql_compiler.Catalog` | 运行时 `CatalogManager` |
|---|---|---|
| 生命周期 | 编译或执行期间 | 数据库整个生命周期 |
| 是否持久化 | 否 | 是 |
| 保存内容 | 表名和列定义 | 表名、列定义和数据页集合 |
| 用途 | 语义分析、计划生成 | 恢复真实数据和管理表存储 |
| 对象 | 编译器内存对象 | `TableStorage` 字典加磁盘目录 |

`CatalogManager` 内部同时维护：

```python
self._catalog  # 编译期目录视图
self._tables   # 表名 → TableStorage
```

### 6.6 `save()` 是否等于立即落盘

不是完全等同。

当前链路是：

```text
CatalogManager.save()
  ↓
Storage.write_page()
  ↓
BufferPool 中的 Page
  ↓
标记 dirty
  ↓
缓存淘汰 / checkpoint / close
  ↓
FileManager.write_page()
  ↓
minidb.db
```

因此更准确的表述是：

> `save()` 更新了目录页并将其置于缓存的脏页状态；正常关闭时 `Database.close()` 会调用 `Storage.close()`，把脏页刷回数据库文件。

---

## 7. 页表、缓存和文件的底层关系

### 7.1 页 0 的作用

页 0 是底层 FileManager 的元数据页，保存：

```text
page_count
free_count
空闲页位图
```

它回答的是：

> 数据库中有哪些物理页，哪些页可以被分配？

它不记录哪张表使用了哪些页。

### 7.2 系统目录的作用

系统目录页 1～16 保存：

```text
表名
列定义
表 → 数据页列表
```

它回答的是：

> 有哪些逻辑表，每张表的数据在哪里？

### 7.3 页分配

`FileManager.allocate_page()`：

```text
1. 先查空闲位图；
2. 如果有空闲页，优先复用；
3. 如果没有空闲页，在文件末尾追加新页；
4. 更新页表。
```

释放页时不会把数据库文件截短，而是把页标记为空闲，供以后重新分配。

### 7.4 页缓存

`BufferPool.get_page()`：

```text
缓存命中
  → 直接返回 Page

缓存未命中
  → 缓存满时淘汰一页
  → 脏页先刷盘
  → 从文件读取新页
  → 放入缓存
```

支持：

- LRU：最近最少使用；
- FIFO：先进先出。

### 7.5 为什么释放页前先 invalidate

假设页 17 已经在缓存中：

```text
缓存：page 17 → 旧表内容
```

如果直接释放页 17，然后马上把 17 分配给新表，缓存里仍然可能有旧对象。

所以必须：

```text
invalidate_page(17)
    ↓
从缓存移除旧页
    ↓
release_page(17)
    ↓
允许页 17 重新分配
```

`invalidate_page()` 如果发现页是 dirty，会先把它刷盘，然后再从缓存移除。

---

## 8. 正常持久化闭环

### 8.1 建表

```text
CREATE TABLE
  ↓
Executor._exec_create()
  ↓
CatalogManager.create_table()
  ↓
创建空 TableStorage
  ↓
CatalogManager.save()
```

空表刚创建时一般还没有数据页：

```text
t → []
```

第一次插入时才申请数据页。

### 8.2 插入已有页

```text
INSERT
  ↓
encode_row()
  ↓
读取已有 RowPage
  ↓
insert(payload)
  ↓
page.data = rp.encode()
  ↓
mark_dirty()
```

目录页号列表没有变化。

### 8.3 插入导致扩页

```text
旧页全部放不下
  ↓
Storage.allocate_page()
  ↓
_pages 增加新页号
  ↓
写入新页
  ↓
insert_row() 返回 True
  ↓
CatalogManager.save()
```

### 8.4 删除部分记录

```text
DELETE
  ↓
扫描页和槽
  ↓
rp.delete(slot)
  ↓
active_count > 0
  ↓
encode + mark_dirty
```

### 8.5 删除整页记录

```text
DELETE
  ↓
active_count == 0
  ↓
invalidate_page()
  ↓
release_page()
  ↓
从 _pages 移除
  ↓
CatalogManager.save()
```

### 8.6 关闭数据库

```text
Database.close()
  ↓
CatalogManager.save()
  ↓
Storage.close()
  ↓
BufferPool.flush_all()
  ↓
FileManager 保存页表
```

### 8.7 重启数据库

```text
Database()
  ↓
FileManager 从页 0 恢复页表
  ↓
CatalogManager 从页 1~16 恢复目录
  ↓
恢复 TableStorage 和 _pages
  ↓
Executor 可以继续查询
```

---

## 9. 答辩现场运行命令

### 9.1 进入项目目录

```powershell
Set-Location H:\vs_code\EchoSQL
```

### 9.2 环境自检

```powershell
python --version
python smoke_test.py
python main.py doctor
```

### 9.3 运行 `demo.sql`

不要直接反复使用默认 `data/` 目录，因为 `student` 表可能已经存在。建议使用新的临时目录：

```powershell
$runDir = Join-Path $env:TEMP ("EchoSQL-defense-" + [guid]::NewGuid().ToString())
python main.py -f .\demo.sql --data-dir $runDir
```

预期过程：

```text
OK
1 row inserted
1 row inserted
1 row inserted
查询出 Alice、Carol
1 row deleted
最终查询只剩 Alice、Carol
```

### 9.4 进入交互式 REPL

```powershell
$runDir = Join-Path $env:TEMP ("EchoSQL-repl-" + [guid]::NewGuid().ToString())
python main.py --data-dir $runDir
```

在 `MiniDB>` 中输入：

```sql
CREATE TABLE student(id INT, name VARCHAR, age INT);
INSERT INTO student VALUES(1, 'Alice', 20);
INSERT INTO student VALUES(2, 'Bob', 17);
SELECT * FROM student;
SELECT id, name FROM student WHERE age > 18;
DELETE FROM student WHERE id = 2;
SELECT * FROM student;
```

内置命令不需要分号：

```text
tables
stats
quit
```

### 9.5 重启验证

退出：

```text
quit
```

使用同一个目录重新启动：

```powershell
python main.py --data-dir $runDir
```

输入：

```text
tables
```

再输入：

```sql
SELECT * FROM student;
```

如果表结构和数据仍然存在，就证明目录和数据页都成功恢复。

### 9.6 运行测试

如果当前环境没有 pytest，先创建虚拟环境：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

运行记录层测试：

```powershell
.\.venv\Scripts\python.exe -m pytest .\tests\test_engine.py -q
```

运行边界测试：

```powershell
.\.venv\Scripts\python.exe -m pytest .\tests\test_boundary.py -q
```

运行全部测试：

```powershell
.\.venv\Scripts\python.exe -m pytest .\tests -q
```

### 9.7 启动 Web

安装依赖后：

```powershell
.\.venv\Scripts\python.exe -m web.app
```

访问：

```text
http://127.0.0.1:5000
```

当前 Web 默认使用项目的 `data/` 目录，没有 CLI 的 `--data-dir` 参数，因此答辩演示记录层时优先使用 CLI。

---

## 10. 四项功能的现场演示

### 10.1 插入和自动扩页

普通插入：

```sql
CREATE TABLE t(id INT, value VARCHAR);
INSERT INTO t VALUES(1, 'first');
INSERT INTO t VALUES(2, 'second');
SELECT * FROM t;
```

跨页插入：

```powershell
$runDir = Join-Path $env:TEMP ("EchoSQL-multipage-" + [guid]::NewGuid().ToString())
$env:ECHOSQL_DEMO_DIR = $runDir
@'
import os
from engine import Database

db = Database(data_dir=os.environ["ECHOSQL_DEMO_DIR"], log=False)
db.execute("CREATE TABLE t(id INT, value VARCHAR);")
for i in range(500):
    db.execute("INSERT INTO t VALUES(%d, 'row-%d');" % (i, i))
print("pages:", db.table_infos()[0]["pages"])
print("row_count:", len(db.execute("SELECT * FROM t;").rows))
db.close()
'@ | python -
```

预期：

```text
pages: [17, 18, 19]
row_count: 500
```

### 10.2 顺序扫描

```sql
SELECT * FROM t;
SELECT id, value FROM t WHERE id < 10;
```

调用链：

```text
SELECT
  ↓
SeqScan
  ↓
TableStorage.scan()
  ↓
逐页、逐槽读取
  ↓
跳过 tombstone
  ↓
decode_row()
```

### 10.3 删除和整页回收

删除部分记录：

```sql
DELETE FROM t WHERE id = 1;
SELECT * FROM t;
```

删除最后一行并观察 pages：

```powershell
$runDir = Join-Path $env:TEMP ("EchoSQL-delete-" + [guid]::NewGuid().ToString())
$env:ECHOSQL_DEMO_DIR = $runDir
@'
import os
from engine import Database

db = Database(data_dir=os.environ["ECHOSQL_DEMO_DIR"], log=False)
db.execute("CREATE TABLE t(id INT);")
db.execute("INSERT INTO t VALUES(1);")
print("before:", db.table_infos())
db.execute("DELETE FROM t WHERE id = 1;")
print("after:", db.table_infos())
db.close()
'@ | python -
```

预期：

```text
before: ... 'pages': [17] ...
after:  ... 'pages': [] ...
```

### 10.4 删表、目录序列化和重启

当前整表删除通过 Python API：

```powershell
$runDir = Join-Path $env:TEMP ("EchoSQL-drop-" + [guid]::NewGuid().ToString())
$env:ECHOSQL_DEMO_DIR = $runDir
@'
import os
from engine import Database

db = Database(data_dir=os.environ["ECHOSQL_DEMO_DIR"], log=False)
db.execute("CREATE TABLE t(id INT);")
db.execute("INSERT INTO t VALUES(1);")
print("before_drop:", db.table_infos())
released = db.drop_table("t")
print("released_pages:", released)
print("after_drop:", db.table_infos())
print("tables:", db.tables())
db.close()
'@ | python -
```

预期：

```text
released_pages: 1
after_drop: []
tables: []
```

重启恢复：

```powershell
$runDir = Join-Path $env:TEMP ("EchoSQL-restart-" + [guid]::NewGuid().ToString())
python main.py --data-dir $runDir
```

输入：

```sql
CREATE TABLE t(id INT, value VARCHAR);
INSERT INTO t VALUES(1, 'persisted');
```

退出：

```text
quit
```

重新启动：

```powershell
python main.py --data-dir $runDir
```

验证：

```text
tables
```

```sql
SELECT * FROM t;
```

---

## 11. 预测答辩问题和标准回答

### Q1：你负责的模块到底解决了什么问题？

回答：

> 底层 Storage 只认识固定大小的 4KB 页，而 SQL 执行器处理的是逻辑表和逻辑行。我负责的记录层把两者连接起来：把一行编码成字节，用槽页把多条变长记录放进一个页，用 TableStorage 管理一张表的多个页，再用 CatalogManager 保存表结构和页集合，使数据可以重启恢复。

### Q2：为什么不用一个 Python list 直接保存所有行？

回答：

> Python list 只适合内存对象，不能体现数据库的页式 I/O、缓存和持久化。项目需要模拟数据库的物理存储，因此必须将记录编码成固定页中的字节，并维护页和槽的定位信息。

### Q3：为什么使用槽页？

回答：

> 因为记录是变长的。槽数组保存每条记录的 offset 和 length，可以在同一页中定位不同长度的记录。删除时只修改槽状态，不需要马上搬移其他记录。

### Q4：槽数组和行数据区为什么从两边向中间增长？

回答：

> 槽数组从页头向后增长，行数据从页尾向前增长，中间就是空闲区。插入时只要两者没有碰撞，就可以继续插入变长记录。

### Q5：一页最多能存多大一行？

回答：

> 页大小为 4096 字节，页头占 8 字节，至少还要为一个槽预留 4 字节，因此单个 payload 的理论上限约为 4084 字节。实际还要考虑一行中每个字段的 Tag 和长度字段。

### Q6：为什么 `RowPage.insert()` 返回 `None`，而不是直接抛异常？

回答：

> “当前页放不下”是正常的扩页条件，不是错误。返回 `None` 可以通知 TableStorage 尝试其他页或申请新页。只有单行本身大到连空页都放不下，才抛出 `RowTooLarge`。

### Q7：为什么删除使用 tombstone？

回答：

> 立即搬移行数据会改变其他记录的位置，可能导致扫描迭代器失效。tombstone 只修改槽信息，扫描时跳过，既简单又稳定。整页没有活动记录时，再把整个页回收。

### Q8：删除后的空间是否马上被复用？

回答：

> 当前版本不是马上复用。部分删除会留下 tombstone 和页内碎片，`compact()` 可以整理，但不会自动触发。当前主要保证整页为空时回收整个页。

### Q9：compact 会不会改变 slot？

回答：

> 会有这种可能。compact 会把有效记录重新插入新页，槽号可能重新排列。因此如果未来把 compact 应用到在线页，需要额外考虑 `(page_id, slot)` 物理行标识的稳定性。当前版本的 compact 只是返回一个新页对象，并未自动替换原页。

### Q10：一行是怎么编码成二进制的？

回答：

> 每个字段前面写一个 Tag。INT 写 Tag 加 4 字节整数，FLOAT 写 Tag 加 8 字节浮点数，字符串写 Tag、2 字节长度和 UTF-8 内容，NULL 只写 Tag。解码器再按照 Tag 逆向读取。

### Q11：为什么 INT 超范围要自己检查？

回答：

> 如果直接让 `struct.pack()` 处理超范围整数，会抛出底层 `struct.error`，不在引擎统一错误体系中。提前检查并抛出 `RowTooLarge`，CLI 和 Web 才能统一处理。

### Q12：字符串长度是按字符还是按字节？

回答：

> 按 UTF-8 编码后的字节数。长度字段为 2 字节，所以单个字符串最多 65535 字节；同时整行还必须满足单页大小限制。

### Q13：一张表的数据页列表保存在哪里？

回答：

> 保存在 CatalogManager 的系统目录中。目录区固定占用页 1 到页 16，内容是带长度前缀的 JSON，JSON 中保存表名、列定义和 pages 列表。

### Q14：页 0 和页 1 到 16 分别保存什么？

回答：

> 页 0 是 FileManager 的页表，记录物理页数量和空闲页位图；页 1 到页 16 是 CatalogManager 的系统目录，记录逻辑表和数据页映射。一个管理物理页分配状态，一个管理逻辑表元数据。

### Q15：为什么目录需要保存 `dir_size`？

回答：

> JSON 目录可能跨多个 4KB 页。第一个目录页前 4 字节保存 JSON 的实际字节数，启动时可以据此计算需要读取多少页，并从拼接结果中截取有效 JSON。

### Q16：插入新页后为什么必须保存目录？

回答：

> 新页加入表的 `_pages` 后，表到数据页的映射发生变化。如果不保存目录，重启后仍然只会按照旧的 pages 列表扫描，新页中的数据虽然写在文件中，但不会被查询到。

### Q17：`save()` 调用后是不是已经落盘？

回答：

> `save()` 通过 Storage 写入缓存并标记脏页，真正物理刷盘会在缓存淘汰、checkpoint 或 close 时发生。正常关闭时 Database 会先保存目录，再关闭 Storage，Storage 会刷写所有脏页。

### Q18：释放页为什么要先 invalidate？

回答：

> 页释放后可能马上被重新分配。如果缓存中还保留旧页对象，新表访问该页号时可能命中旧数据。invalidate 可以清除缓存中的旧页，且会在必要时先刷写脏页。

### Q19：释放页会缩小数据库文件吗？

回答：

> 不会。释放页只是把它加入空闲页位图，后续可以复用。数据库文件通常不会因为释放中间页而自动截短。

### Q20：SQL DELETE 是不是调用 `TableStorage.delete_row()`？

回答：

> TableStorage 提供了单行删除接口，但 SQL 的批量 DELETE 主路径在 Executor 中直接遍历页和槽，对匹配行进行 tombstone 标记，并在整页为空时执行 invalidate 和 release。两者采用的是同样的删除和回收策略。

### Q21：为什么 TableStorage 需要返回是否扩页？

回答：

> 因为普通插入只改变已有页内容，而扩页会改变表的 pages 列表。返回布尔值可以让 Executor 判断什么时候必须保存 CatalogManager。

### Q22：为什么不用索引直接查找？

回答：

> 当前版本没有实现 B+ 树或哈希索引，查询主要使用顺序扫描。这样实现简单，重点是验证 SQL、执行器、记录层、页存储和持久化的完整链路。索引属于后续扩展方向。

### Q23：当前有没有事务和回滚？

回答：

> 当前没有完整事务和 WAL。多行操作中如果中途出错，前面已经执行成功的副作用可能保留。当前持久化保证主要针对正常关闭和重启场景。

### Q24：如果程序突然断电，数据一定安全吗？

回答：

> 不能保证完整的崩溃恢复。当前实现了正常关闭时的目录保存、脏页刷盘和页表持久化，但没有 WAL 和原子提交机制，因此突然断电时可能存在部分写入问题。

### Q25：有没有并发控制？

回答：

> 当前项目是单进程、单数据库实例的教学型原型，没有实现锁、事务隔离或 MVCC，也没有针对多个进程同时操作同一个数据库文件做并发保护。

### Q26：系统目录损坏时怎么办？

回答：

> 加载时会检查目录长度、JSON 解码和顶层结构，主要格式错误会抛出 `CatalogCorrupted`，避免把错误的目录继续交给执行器。当前对目录内部字段缺失等极端情况的保护还不完全。

### Q27：为什么有两个 Catalog？

回答：

> 编译期 Catalog 只服务 SQL 的语义分析和计划生成；运行时 CatalogManager 还要管理真实的 TableStorage 和数据页集合，并将这些信息持久化。一个是编译视图，一个是运行时物理目录。

### Q28：如果一页中只删了一半数据，为什么不马上释放页？

回答：

> 因为页面仍然包含有效记录，释放会造成数据丢失。此时只标记被删除槽并保留页面；只有 `active_count == 0` 时才可以释放整个页。

### Q29：为什么新建空表时没有立即分配数据页？

回答：

> 空表没有数据，不需要占用用户数据页。当前表创建时只在目录中注册表结构，第一次插入时才申请数据页，减少不必要的空间占用。

### Q30：表名和列名大小写是否敏感？

回答：

> 当前运行时 `_tables` 使用表名原始拼写作为字典 key，代码注释和实现按大小写敏感处理。答辩时可以说这是当前实现选择，如果需要大小写不敏感，应在词法或目录层统一规范化名称。

---

## 12. 老师让你手算一个页时怎么答

假设：

```text
页大小 = 4096
页头 = 8
槽大小 = 4
第一条行 payload = 20 字节
```

空页：

```text
free_off = 4096
slot_count = 0
available = 4096 - 8 = 4088
```

插入第一条记录需要：

```text
20 + 4 = 24 字节
```

插入后：

```text
free_off = 4096 - 20 = 4076
slot 0 = (4076, 20)
slot_count = 1
```

新的可用空间：

```text
4076 - (8 + 1 × 4) = 4064
```

如果第二条 payload 是 30 字节，需要：

```text
30 + 4 = 34 字节
```

因为 34 小于 4064，所以可以插入。

第二条记录数据位置：

```text
4076 - 30 = 4046
slot 1 = (4046, 30)
```

页数据区大致是：

```text
slot 0 → [4076, 4096)
slot 1 → [4046, 4076)
```

答辩时，这个计算可以证明你理解了页内布局，而不是只记住类名。

---

## 13. 推荐答辩陈述顺序

按照下面顺序讲，最不容易被问乱：

### 第一步：先讲定位

```text
Executor → TableStorage → RowPage → Storage
```

说清楚你的模块是记录层。

### 第二步：讲一行如何落盘

```text
逻辑值列表
  ↓ encode_row
二进制 payload
  ↓ RowPage.insert
槽和页内行数据
  ↓ Storage
缓存和数据库文件
```

### 第三步：讲一张表如何跨页

```text
TableStorage._pages = [17, 18, 19]
```

强调：旧页放不下才扩页，扩页后必须保存目录。

### 第四步：讲删除

```text
部分删除 → tombstone
整页为空 → invalidate + release
```

### 第五步：讲重启恢复

```text
close → save catalog + flush dirty pages
restart → load catalog → restore pages → scan
```

### 第六步：主动讲限制

主动说明：

- 当前主要是顺序扫描；
- 没有索引；
- 没有 WAL 和事务回滚；
- compact 不是自动执行；
- DROP TABLE 主要是 API；
- 完整测试和 Web 需要依赖环境。

主动说明限制通常比老师问出来以后再解释更稳。

---

## 14. 最后背这段总结

> 我的工作主要是实现数据库的记录层。底层 Storage 提供固定大小的 4KB 页，但它不理解表和行，所以我在上面实现了 RowPage 槽页结构，用槽数组保存变长记录的偏移和长度；通过 encode_row 和 decode_row 完成逻辑字段与二进制 payload 的转换；通过 TableStorage 管理一张表的多个数据页，实现插入时优先填充旧页、页满后自动扩页、顺序扫描、tombstone 删除和整页回收；通过 CatalogManager 将表名、列定义以及数据页号列表序列化到固定目录页中，使数据库正常关闭后重新启动时可以恢复表和数据。当前版本已经打通了记录编码、槽页组织、跨页存储、目录持久化和正常重启恢复，但索引、事务日志、并发控制、自动 compact 和完整崩溃恢复还没有实现。

