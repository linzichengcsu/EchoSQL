"""存储系统测试(对应测试文档 3.2 TC-ST-01 ~ TC-ST-06 + 持久化 FR-2.4)。

    TC-ST-01  分配 / 释放 / 读写页:页编号唯一,读写内容一致      P0
    TC-ST-02  每页 4KB 边界:超页大小数据正确跨页存储             P1
    TC-ST-03  LRU 替换:命中率统计正确,替换日志输出              P0
    TC-ST-04  FIFO 替换(可选):按先进先出顺序替换                P2
    TC-ST-05  脏页刷盘(flush_page):刷盘后磁盘与内存一致          P0
    TC-ST-06  空闲页回收与再分配:释放的页可被重新分配            P1
    补充      重启持久化(TC-E2E-05 存储层 / FR-2.4)、错误处理
"""
import os
import sys

# 直接运行(python tests/test_storage.py)时也能导入项目根包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from storage import (
    Storage,
    FileManager,
    BufferPool,
    Page,
    PAGE_SIZE,
    META_PAGE_ID,
    split_into_pages,
    combine_pages,
    DataTooLarge,
    InvalidPageId,
    PageNotAllocated,
    PageOutOfRange,
)


@pytest.fixture
def storage(tmp_path):
    """在临时目录构造一个全新 Storage,测试后关闭清理。"""
    st = Storage(data_dir=str(tmp_path), capacity=8, policy="LRU")
    yield st
    st.close()


@pytest.fixture
def fm(tmp_path):
    """在临时目录构造 FileManager。"""
    manager = FileManager(str(tmp_path))
    yield manager
    manager.close()


# ======================================================================
# TC-ST-01 分配 / 释放 / 读写页(页编号唯一,读写内容一致)
# ======================================================================


def test_tc_st01_allocate_pages_have_unique_ids(storage):
    ids = [storage.allocate_page() for _ in range(10)]
    assert len(set(ids)) == 10          # 页编号唯一
    assert all(pid >= 1 for pid in ids)  # 页 0 保留给页表
    assert META_PAGE_ID not in ids


def test_tc_st01_write_read_content_identical(storage):
    pid = storage.allocate_page()
    payload = b"hello mini db"
    storage.write_page(pid, payload)
    page = storage.get_page(pid)
    # 写入内容出现在页头,且物理页恒为 4KB
    assert bytes(page.data[: len(payload)]) == payload
    assert len(page.data) == PAGE_SIZE
    # 刷盘后磁盘直读(绕过缓存)内容一致
    storage.flush_page(pid)
    assert storage.read_page(pid)[: len(payload)] == payload


def test_tc_st01_default_page_is_zero_filled(storage):
    pid = storage.allocate_page()
    page = storage.get_page(pid)
    assert bytes(page.data) == b"\x00" * PAGE_SIZE


# ======================================================================
# TC-ST-02 每页 4KB 边界:超页大小数据正确跨页存储
# ======================================================================


def test_tc_st02_write_oversize_single_page_raises(storage):
    pid = storage.allocate_page()
    with pytest.raises(DataTooLarge):
        storage.write_page(pid, b"x" * (PAGE_SIZE + 1))


def test_tc_st02_oversize_data_spans_multiple_pages(storage):
    """9000 字节数据按 4KB 分段写入多个页,读回还原一致。"""
    data = os.urandom(9000)                      # 跨 3 页:4096 + 4096 + 808
    chunks = split_into_pages(data)
    assert len(chunks) == 3                      # 正确分段
    assert all(len(c) <= PAGE_SIZE for c in chunks)

    pids = [storage.allocate_page() for _ in chunks]
    for pid, chunk in zip(pids, chunks):
        storage.write_page(pid, chunk)
    storage.checkpoint()                                   # 脏页统一刷盘
    restored = combine_pages([storage.read_page(pid) for pid in pids])
    # 物理页恒为 4KB:末页不足部分按零填充,原数据(前 9000 字节)必须完整还原
    assert restored[: len(data)] == data
    assert len(restored) == PAGE_SIZE * len(chunks)
    # 逐段核对:各页头部(除末页填充外)与原始分段一致,跨页边界无错位
    for pid, chunk in zip(pids, chunks):
        page = storage.read_page(pid)
        assert page[: len(chunk)] == chunk


def test_split_combine_empty_data_keeps_one_page():
    assert split_into_pages(b"") == [b""]
    assert combine_pages([b""]) == b""


# ======================================================================
# TC-ST-03 LRU 替换策略(命中率统计 + 替换日志)
# ======================================================================


def test_tc_st03_lru_eviction_order(tmp_path):
    fm = FileManager(str(tmp_path))
    bp = BufferPool(fm, capacity=2, policy="LRU")
    p1, p2, p3 = (fm.allocate_page() for _ in range(3))
    # 访问序列:1, 2, 1, 3
    bp.get_page(p1)
    bp.get_page(p2)
    bp.get_page(p1)          # 命中,1 成为最近使用
    bp.get_page(p3)          # 满,淘汰最久未访问的 2
    assert p2 not in bp.cached_page_ids()
    assert p1 in bp.cached_page_ids() and p3 in bp.cached_page_ids()
    assert any("LRU evict page %d" % p2 in line for line in bp.eviction_log)
    fm.close()


def test_tc_st03_hit_rate_statistics(storage):
    bp = storage.bp
    ids = [storage.allocate_page() for _ in range(4)]
    # get 1,2,3,4 全 miss → get 1,2 命中
    for i in ids:
        bp.get_page(i)
    for i in ids[:2]:
        bp.get_page(i)
    assert bp.hits == 2 and bp.misses == 4
    assert bp.hit_rate == 2 / 6
    stats = bp.stats()
    assert stats["hits"] == 2 and stats["misses"] == 4
    assert abs(stats["hit_rate"] - 2 / 6) < 1e-9


def test_tc_st03_eviction_log_dirty_flag(tmp_path):
    fm = FileManager(str(tmp_path))
    bp = BufferPool(fm, capacity=2, policy="LRU")
    pid = fm.allocate_page()
    bp.write_page(pid, b"modified")        # miss 读入并标脏
    p2 = fm.allocate_page()
    bp.get_page(p2)                        # 缓存满 [pid, p2]
    third = fm.allocate_page()
    bp.get_page(third)                     # 淘汰最久未访问的 pid(脏页)
    assert any("LRU evict page %d (dirty)" % pid in line for line in bp.eviction_log)
    fm.close()


# ======================================================================
# TC-ST-04 FIFO 替换策略(可选):按先进先出顺序替换
# ======================================================================


def test_tc_st04_fifo_eviction_order(tmp_path):
    fm = FileManager(str(tmp_path))
    bp = BufferPool(fm, capacity=2, policy="FIFO")
    p1, p2, p3 = (fm.allocate_page() for _ in range(3))
    bp.get_page(p1)
    bp.get_page(p2)
    bp.get_page(p1)          # FIFO 命中不改变顺序(1 仍是最早进入)
    bp.get_page(p3)          # 满,淘汰最早进入的 1
    assert p1 not in bp.cached_page_ids()
    assert p2 in bp.cached_page_ids() and p3 in bp.cached_page_ids()
    assert any("FIFO evict page %d" % p1 in line for line in bp.eviction_log)
    fm.close()


def test_tc_st04_fifo_different_from_lru(tmp_path):
    fm = FileManager(str(tmp_path))
    fifo = BufferPool(fm, capacity=2, policy="FIFO")
    lru = BufferPool(fm, capacity=2, policy="LRU")
    p1, p2, p3 = (fm.allocate_page() for _ in range(3))
    for bp in (fifo, lru):
        bp.get_page(p1)
        bp.get_page(p2)
        bp.get_page(p1)      # 命中
        bp.get_page(p3)      # 淘汰
    # FIFO 淘汰最早进入的 1;LRU 淘汰最久未访问的 2
    assert p1 not in fifo.cached_page_ids()
    assert p2 not in lru.cached_page_ids()
    fm.close()


def test_switch_policy_keeps_cache(tmp_path):
    fm = FileManager(str(tmp_path))
    bp = BufferPool(fm, capacity=4, policy="LRU")
    p1, p2 = fm.allocate_page(), fm.allocate_page()
    bp.get_page(p1)
    bp.get_page(p2)
    bp.set_policy("FIFO")
    assert bp.policy == "FIFO"
    assert sorted(bp.cached_page_ids()) == sorted([p1, p2])  # 缓存保留
    fm.close()


# ======================================================================
# TC-ST-05 脏页刷盘(flush_page):刷盘后磁盘内容与内存一致
# ======================================================================


def test_tc_st05_flush_page_writes_to_disk(storage):
    pid = storage.allocate_page()
    storage.write_page(pid, b"old")
    storage.flush_page(pid)
    assert storage.read_page(pid)[:3] == b"old"   # 刷盘后磁盘一致

    storage.write_page(pid, b"new")               # 再次修改(脏,未刷盘)
    # 刷盘前磁盘仍是旧内容(延迟刷盘)
    assert storage.read_page(pid)[:3] == b"old"
    storage.flush_page(pid)
    assert storage.read_page(pid)[:3] == b"new"   # 刷盘后磁盘一致


def test_tc_st05_flush_page_clears_dirty(storage):
    pid = storage.allocate_page()
    storage.write_page(pid, b"x")
    assert pid in storage.bp.dirty_page_ids()
    storage.flush_page(pid)
    assert pid not in storage.bp.dirty_page_ids()


def test_checkpoint_flushes_all_dirty_pages(storage):
    pids = [storage.allocate_page() for _ in range(5)]
    for pid in pids:
        storage.write_page(pid, b"data-%d" % pid)
    flushed = storage.checkpoint()
    assert flushed == 5
    assert storage.bp.dirty_page_ids() == []


# ======================================================================
# TC-ST-06 空闲页回收与再分配
# ======================================================================


def test_tc_st06_released_page_reallocated(storage):
    p1, p2, p3 = storage.allocate_page(), storage.allocate_page(), storage.allocate_page()
    storage.release_page(p2)
    reused = storage.allocate_page()
    assert reused == p2                            # 释放的页被重新分配
    assert storage.fm.free_count == 0


def test_tc_st06_free_list_tracks_multiple_releases(storage):
    pids = [storage.allocate_page() for _ in range(4)]
    storage.release_page(pids[1])
    storage.release_page(pids[3])
    assert storage.fm.free_count == 2
    # 再分配优先复用空闲页
    assert storage.allocate_page() in (pids[1], pids[3])


# ======================================================================
# 持久化(FR-2.4 / TC-E2E-05 存储层):重启后数据不丢失
# ======================================================================


def test_persistence_after_reopen(tmp_path):
    path = str(tmp_path)
    # 第一次会话:建页、写数据、释放一页、Checkpoint 刷盘、关闭
    st = Storage(data_dir=path, capacity=4)
    pid1 = st.allocate_page()
    pid2 = st.allocate_page()
    pid3 = st.allocate_page()
    st.write_page(pid1, b"alice")
    st.write_page(pid2, b"bob")
    st.release_page(pid3)
    st.checkpoint()
    st.close()

    # 第二次会话(模拟重启):页表与数据均恢复
    st2 = Storage(data_dir=path, capacity=4)
    assert st2.fm.page_count == 4                 # 页表持久化
    assert st2.read_page(pid1)[:5] == b"alice"    # 数据持久化
    assert st2.read_page(pid2)[:3] == b"bob"
    # 释放的页重启后仍为空闲,可复用
    assert st2.allocate_page() == pid3
    st2.close()


def test_persistence_dirty_pages_flushed_on_close(tmp_path):
    path = str(tmp_path)
    st = Storage(data_dir=path)
    pid = st.allocate_page()
    st.write_page(pid, b"persist me")             # 脏页,未显式刷盘
    st.close()                                     # close 触发 Checkpoint

    st2 = Storage(data_dir=path)
    assert st2.read_page(pid)[:10] == b"persist me"
    st2.close()


# ======================================================================
# 错误处理(非法输入不崩溃)
# ======================================================================


def test_read_out_of_range_page_raises(storage):
    with pytest.raises(PageOutOfRange):
        storage.read_page(99)


def test_read_released_page_raises(storage):
    pid = storage.allocate_page()
    storage.release_page(pid)
    with pytest.raises(PageNotAllocated):
        storage.read_page(pid)


def test_release_page_zero_is_forbidden(storage):
    with pytest.raises(InvalidPageId):
        storage.release_page(META_PAGE_ID)


def test_release_already_free_page_raises(storage):
    pid = storage.allocate_page()
    storage.release_page(pid)
    with pytest.raises(PageNotAllocated):
        storage.release_page(pid)


def test_release_out_of_range_raises(storage):
    with pytest.raises(PageOutOfRange):
        storage.release_page(-1)


def test_page_object_default_zero_filled():
    page = Page(7)
    assert len(page) == PAGE_SIZE
    assert bytes(page.data) == b"\x00" * PAGE_SIZE
    assert not page.dirty
    page.mark_dirty()
    assert page.dirty


# ======================================================================
# 统一入口 Storage 门面(FR-2.3):对上层暴露一致的存储访问接口
# ======================================================================


def test_storage_facade_policy_hit_rate_stats_forwarding(storage):
    assert storage.hit_rate == 0.0          # 无访问记录时为 0
    assert isinstance(storage.stats(), dict)
    assert storage.eviction_log == []
    storage.set_policy("FIFO")
    assert storage.bp.policy == "FIFO"
    assert "Storage" in repr(storage) and "minidb.db" in repr(storage)


def test_storage_facade_mark_dirty_and_flush_all(storage):
    pid = storage.allocate_page()
    page = storage.get_page(pid)            # 门面带缓存取页
    page.data[0:3] = b"abc"                 # 直接改内存页
    storage.mark_dirty(pid)                 # 门面标脏
    assert pid in storage.bp.dirty_page_ids()
    assert storage.flush_all() == 1         # 门面全量刷盘
    assert storage.bp.dirty_page_ids() == []
    assert storage.read_page(pid)[:3] == b"abc"


def test_storage_facade_supports_with_statement(tmp_path):
    path = str(tmp_path)
    with Storage(data_dir=path) as st:      # __exit__ 自动刷盘 + 关闭
        pid = st.allocate_page()
        st.write_page(pid, b"context mgr")
    with Storage(data_dir=path) as st2:     # 重启后仍可读
        assert st2.read_page(pid)[:11] == b"context mgr"


# ======================================================================
# 统一启动方法（P5）：开发者可直接运行本测试模块
#     python tests/test_storage.py
#     或编程调用 run_tests()（返回 pytest 退出码，0 = 全部通过）
# ======================================================================


def run_tests(verbose=True, extra_args=None):
    """统一启动方法：以 pytest 运行本测试模块全部用例。

    用法:
        python tests/test_storage.py          # 命令行直接运行
        from runner import run_module         # 或编程调用(所有模块签名一致)
        run_module("tests/test_storage.py")
    """
    from runner import run_module
    return run_module(__file__, verbose=verbose, extra_args=extra_args)


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())
