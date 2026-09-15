# 记录存储引擎四项功能演示命令

本文档是 `答辩说明-记录存储引擎与系统目录.md` 的命令演示附录，专门说明以下四项功能如何运行：

1. 插入记录和自动扩页；
2. 顺序扫描；
3. 删除记录和整页回收；
4. 删除整张表、目录序列化和重启加载。

所有命令都应在项目根目录执行：

```powershell
Set-Location H:\vs_code\EchoSQL
```

项目核心运行只依赖 Python 标准库。下面的 Python 演示使用 PowerShell here-string 通过标准输入传给 Python，不会在项目中创建临时脚本文件。

## 一、插入记录和自动扩页

### 1.1 CLI 展示普通插入

创建新的临时数据库目录：

```powershell
$runDir = Join-Path $env:TEMP ("EchoSQL-insert-" + [guid]::NewGuid().ToString())
python main.py --data-dir $runDir
```

在 `MiniDB>` 中输入：

```sql
CREATE TABLE t(id INT, value VARCHAR);
INSERT INTO t VALUES(1, 'first');
INSERT INTO t VALUES(2, 'second');
SELECT * FROM t;
```

这组命令展示的是：

```text
SQL INSERT
  ↓
Executor._exec_insert()
  ↓
TableStorage.insert_row()
  ↓
encode_row()
  ↓
已有 RowPage.insert()
  ↓
Storage.mark_dirty()
```

### 1.2 展示大量数据跨页

一页放满后，`TableStorage` 会向 `Storage` 申请新页，并把新页号加入表的 `_pages` 集合。使用下面的命令插入 500 行：

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

预期结果类似：

```text
pages: [17, 18, 19]
row_count: 500
```

答辩说明：

> `insert_row()` 先尝试已有页。如果所有已有页的 `RowPage.insert()` 都返回 `None`，就调用 `Storage.allocate_page()` 申请新页。新页加入 `_pages` 后返回 `True`，执行器据此调用 `CatalogManager.save()` 保存新的页集合。

## 二、顺序扫描

### 2.1 使用 SQL 触发扫描

顺序扫描没有单独的 CLI 命令，通常由 `SELECT` 触发：

```powershell
$runDir = Join-Path $env:TEMP ("EchoSQL-scan-" + [guid]::NewGuid().ToString())
python main.py --data-dir $runDir
```

在 `MiniDB>` 中输入：

```sql
CREATE TABLE t(id INT, value VARCHAR);
INSERT INTO t VALUES(1, 'first');
INSERT INTO t VALUES(2, 'second');
INSERT INTO t VALUES(3, 'third');
SELECT * FROM t;
SELECT id, value FROM t WHERE id < 3;
```

执行链路是：

```text
SELECT
  ↓
SeqScan
  ↓
TableStorage.scan()
  ↓
遍历 _pages
  ↓
RowPage.decode()
  ↓
遍历 slots
  ↓
RowPage.get()
  ↓
跳过 tombstone
  ↓
decode_row()
```

### 2.2 直接展示 scan() 返回值

如果答辩老师想看物理定位信息，可以运行：

```powershell
$runDir = Join-Path $env:TEMP ("EchoSQL-scan-api-" + [guid]::NewGuid().ToString())
$env:ECHOSQL_DEMO_DIR = $runDir
@'
import os
from engine import Database

db = Database(data_dir=os.environ["ECHOSQL_DEMO_DIR"], log=False)
db.execute("CREATE TABLE t(id INT, value VARCHAR);")
db.execute("INSERT INTO t VALUES(1, 'first');")
db.execute("INSERT INTO t VALUES(2, 'second');")

table = db.catalog_mgr.table_storage("t")
for page_id, slot, values in table.scan():
    print("page_id=%s slot=%s values=%r" % (page_id, slot, values))

db.close()
'@ | python -
```

预期输出类似：

```text
page_id=17 slot=0 values=[1, 'first']
page_id=17 slot=1 values=[2, 'second']
```

这三个返回值的含义是：

```text
page_id：记录所在的数据页
slot：记录在该页中的槽号
values：decode_row() 还原后的字段值列表
```

## 三、删除记录和整页回收

### 3.1 CLI 展示 tombstone 删除

在已有的数据库 REPL 中输入：

```sql
DELETE FROM t WHERE id = 1;
SELECT * FROM t;
```

删除执行后，目标槽会被标记为 `TOMBSTONE`。之后 `scan()` 调用 `RowPage.get()` 时得到 `None`，因此不会把被删除的记录返回给上层。

执行逻辑：

```text
DELETE
  ↓
Executor._exec_delete()
  ↓
扫描页和槽
  ↓
对符合条件的槽调用 rp.delete(slot)
  ↓
有剩余活动行：写回脏页
没有活动行：invalidate_page() + release_page()
```

### 3.2 展示整页回收

创建一张只有一行数据的表，然后删除这唯一的一行：

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

预期结果中，删除前类似：

```text
before: [{'name': 't', 'columns': [{'name': 'id', 'type': 'INT'}], 'pages': [17]}]
```

删除后类似：

```text
after: [{'name': 't', 'columns': [{'name': 'id', 'type': 'INT'}], 'pages': []}]
```

这里说明：

1. `active_count` 变为 0；
2. 页从缓存中失效；
3. 页被归还给底层空闲页位图；
4. 页号从当前表的 `_pages` 集合中删除；
5. 目录被重新保存。

## 四、删表、目录序列化和重启加载

### 4.1 查看目录元数据

CLI 中输入：

```text
tables
```

可以查看表名和列定义。

如果要同时查看数据页列表，可以使用 Python API：

```powershell
$runDir = Join-Path $env:TEMP ("EchoSQL-catalog-" + [guid]::NewGuid().ToString())
$env:ECHOSQL_DEMO_DIR = $runDir
@'
import os
from engine import Database

db = Database(data_dir=os.environ["ECHOSQL_DEMO_DIR"], log=False)
db.execute("CREATE TABLE t(id INT, value VARCHAR);")
db.execute("INSERT INTO t VALUES(1, 'first');")

print("tables:", db.tables())
print("table_infos:", db.table_infos())

db.close()
'@ | python -
```

`table_infos()` 中会显示：

```text
表名
列名和列类型
pages: [17]
```

### 4.2 使用 Python API 删除整张表

当前版本的整表删除主要通过 `Database.drop_table()` API 完成，不能把 `DROP TABLE` 当作已经接通的 CLI SQL 命令：

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

预期结果类似：

```text
before_drop: ... 'pages': [17] ...
released_pages: 1
after_drop: []
tables: []
```

`drop_table()` 的执行逻辑是：

```text
TableStorage.release_all()
  ↓
逐页 invalidate_page()
  ↓
逐页 release_page()
  ↓
清空 _pages
  ↓
从 CatalogManager._tables 移除
  ↓
从编译期 Catalog 移除
  ↓
CatalogManager.save()
```

### 4.3 展示目录序列化和重启恢复

第一次启动：

```powershell
$runDir = Join-Path $env:TEMP ("EchoSQL-restart-" + [guid]::NewGuid().ToString())
python main.py --data-dir $runDir
```

在 REPL 中输入：

```sql
CREATE TABLE t(id INT, value VARCHAR);
INSERT INTO t VALUES(1, 'persisted');
```

查看目录：

```text
tables
```

然后退出：

```text
quit
```

再次使用同一个数据目录启动：

```powershell
python main.py --data-dir $runDir
```

输入：

```text
tables
```

以及：

```sql
SELECT * FROM t;
```

如果能看到表 `t` 和记录 `persisted`，说明：

```text
CatalogManager.save()
  ↓
表元数据转成 JSON
  ↓
JSON 写入目录页 1~16
  ↓
关闭时刷写脏页
  ↓
重新启动
  ↓
CatalogManager.load()
  ↓
恢复 TableStorage 和 page_ids
  ↓
TableStorage.scan()
  ↓
重新查到 persisted
```

## 五、四项功能和源码对应关系

| 演示内容 | 主要源码 | 触发命令 |
|---|---|---|
| 插入和自动扩页 | `engine/storage_engine.py` 的 `TableStorage.insert_row()` | `INSERT INTO ...` 或 500 行 Python 循环 |
| 顺序扫描 | `engine/storage_engine.py` 的 `TableStorage.scan()`、`engine/executor.py` 的 `_scan_table()` | `SELECT * FROM ...` |
| 删除和整页回收 | `RowPage.delete()`、`Executor._exec_delete()`、`TableStorage.delete_row()` | `DELETE FROM ...` |
| 删表和目录持久化 | `CatalogManager.drop_table()`、`save()`、`load()` | `db.drop_table("t")`、退出后重启 |

## 六、答辩时的简短讲法

### 插入

> 插入先编码行，再按顺序检查已有数据页。如果已有页能放下，就写回并标脏；如果所有页都放不下，就申请新页并更新表页集合。页集合变化时必须保存目录。

### 扫描

> 扫描按照表的 page_ids 逐页读取，每页再逐槽读取。遇到 tombstone 就跳过，其他记录使用 decode_row 还原，最终返回页号、槽号和字段值。

### 删除

> 删除不是马上搬移数据，而是把槽标记为 tombstone。这样扫描过程稳定。如果删除后整页没有活动记录，就将整页从缓存失效并归还给空闲页位图。

### 删表和序列化

> 删除整张表时释放它的全部数据页，然后从运行时目录和编译期目录中移除。目录保存时把表名、列定义和 page_ids 编码成 JSON，写入页 1 到页 16；重新启动时再读取 JSON 恢复这些信息。

