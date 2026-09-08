"""页缓存管理(FR-2.2)。

缓冲池(BufferPool)位于 FileManager 之上,为上层提供带缓存的页访问:
    - get_page(page_id)     带缓存取页(命中 / 读盘 + 必要时替换)
    - write_page(...)       写页并标记脏
    - flush_page(page_id)   脏页刷盘(单页)
    - checkpoint()          全部脏页刷盘(Checkpoint 机制,FR-2.4)

替换策略(推荐同时支持并可切换,FR-2.2):
    - LRU  最近最少使用:命中把页移到队尾,淘汰队首(最久未访问)
    - FIFO 先进先出:命中不改变顺序,淘汰最早进入的页

实现说明:缓存容器统一为 collections.OrderedDict(保持插入序),
    LRU 命中时 move_to_end 使其变为"访问序",FIFO 命中不动保持"插入序";
    淘汰统一 popitem(last=False) —— 对 LRU 是"最久未访问",对 FIFO 是"最早进入"。
    切换策略(set_policy)因此只需改标志,无需重建缓存。

提供缓存命中统计(命中率)与替换日志(FR-2.2),供上层展示与验收。
"""

from collections import OrderedDict
from typing import List, Optional

from .errors import DataTooLarge
from .file_manager import FileManager
from .page import PAGE_SIZE, Page

__all__ = ["BufferPool", "POLICIES"]

#: 支持的替换策略
POLICIES = ("LRU", "FIFO")


class BufferPool:
    """页缓存池:容量固定,按 LRU / FIFO 策略替换(TC-ST-03 / TC-ST-04)。

    用法:
        bp = BufferPool(fm, capacity=8, policy="LRU")
        page = bp.get_page(1)          # 可能触发淘汰与磁盘读
        bp.write_page(1, b"new data")  # 写缓存并标记脏
        bp.flush_page(1)               # 脏页刷盘
        bp.checkpoint()                # 全部脏页刷盘
        print(bp.stats())              # 命中率等统计
    """

    def __init__(
        self,
        file_manager: FileManager,
        capacity: int = 8,
        policy: str = "LRU",
        log: bool = True,
    ):
        if capacity <= 0:
            raise ValueError("capacity must be positive, got %d" % capacity)
        self._fm = file_manager
        self.capacity = capacity
        self.policy = policy.upper()
        if self.policy not in POLICIES:
            raise ValueError("policy must be one of %s, got %r" % (POLICIES, policy))

        #: 缓存容器:OrderedDict[page_id -> Page]
        self._cache: "OrderedDict[int, Page]" = OrderedDict()
        #: 是否记录替换日志
        self.log = log
        #: 替换日志(FR-2.2):如 "LRU evict page 2 (dirty)"
        self.eviction_log: List[str] = []
        #: 命中 / 未命中 / 替换次数统计
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    # ------------------------------------------------------------------
    # 缓存核心操作
    # ------------------------------------------------------------------

    def get_page(self, page_id: int) -> Page:
        """带缓存取页:命中直接返回;未命中读盘入缓存(满则先淘汰)。"""
        page = self._cache.get(page_id)
        if page is not None:
            self.hits += 1
            self._on_hit(page_id)
            return page

        self.misses += 1
        if len(self._cache) >= self.capacity:
            self._evict_one()
        data = self._fm.read_page(page_id)  # 未分配页在此抛错误
        page = Page(page_id, data)
        self._cache[page_id] = page
        return page

    def write_page(self, page_id: int, data) -> Page:
        """写入页数据(自动补零到 4KB)并标记脏,数据经缓存延迟刷盘。"""
        page = self.get_page(page_id)
        payload = bytes(data)
        if len(payload) > PAGE_SIZE:
            raise DataTooLarge(
                "data of %d bytes exceeds page size %d" % (len(payload), PAGE_SIZE)
            )
        page.data = bytearray(payload)
        if len(page.data) < PAGE_SIZE:
            page.data.extend(b"\x00" * (PAGE_SIZE - len(page.data)))
        page.mark_dirty()
        return page

    def mark_dirty(self, page_id: int) -> None:
        """标记缓存中的页为脏(get_page 后直接改 data 的场景使用)。"""
        page = self._cache.get(page_id)
        if page is None:
            page = self.get_page(page_id)  # 读入再标脏
        page.mark_dirty()

    # ------------------------------------------------------------------
    # 替换策略
    # ------------------------------------------------------------------

    def _on_hit(self, page_id: int) -> None:
        """命中时的顺序调整:LRU 移到队尾,FIFO 不动。"""
        if self.policy == "LRU":
            self._cache.move_to_end(page_id)

    def _evict_one(self) -> Optional[int]:
        """淘汰一个页(脏页先刷盘),返回被淘汰页编号;缓存空返回 None。"""
        if not self._cache:
            return None
        page_id, page = self._cache.popitem(last=False)
        if page.dirty:
            self._fm.write_page(page_id, page.data)
        self.evictions += 1
        if self.log:
            state = "dirty" if page.dirty else "clean"
            self.eviction_log.append(
                "%s evict page %d (%s)" % (self.policy, page_id, state)
            )
        return page_id

    def set_policy(self, policy: str) -> None:
        """切换替换策略(LRU <-> FIFO),缓存内容保留。"""
        policy = policy.upper()
        if policy not in POLICIES:
            raise ValueError("policy must be one of %s, got %r" % (POLICIES, policy))
        self.policy = policy

    # ------------------------------------------------------------------
    # 刷盘(FR-2.2 flush_page / FR-2.4 Checkpoint)
    # ------------------------------------------------------------------

    def flush_page(self, page_id: int) -> None:
        """将缓存中的指定脏页刷回磁盘(TC-ST-05)。"""
        page = self._cache.get(page_id)
        if page is not None and page.dirty:
            self._fm.write_page(page_id, page.data)
            page.dirty = False

    def flush_all(self) -> int:
        """刷盘全部脏页,返回刷盘页数(Checkpoint,FR-2.4)。"""
        count = 0
        for page in self._cache.values():
            if page.dirty:
                self._fm.write_page(page.page_id, page.data)
                page.dirty = False
                count += 1
        return count

    def checkpoint(self) -> int:
        """Checkpoint:刷盘全部脏页(与 flush_all 等价,名称对应 FR-2.4)。"""
        return self.flush_all()

    def evict(self) -> Optional[int]:
        """主动淘汰一个页(测试/调试用),脏页先刷盘。"""
        return self._evict_one()

    # ------------------------------------------------------------------
    # 统计与查询(FR-2.2 命中统计)
    # ------------------------------------------------------------------

    @property
    def hit_rate(self) -> float:
        """缓存命中率 hits / (hits + misses);无访问记录时返回 0.0。"""
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def cached_page_ids(self) -> List[int]:
        return list(self._cache.keys())

    def dirty_page_ids(self) -> List[int]:
        return [pid for pid, p in self._cache.items() if p.dirty]

    def stats(self) -> dict:
        """命中统计与状态汇总(便于上层输出 / 测试断言)。"""
        return {
            "policy": self.policy,
            "capacity": self.capacity,
            "cached": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_rate": self.hit_rate,
            "dirty_pages": self.dirty_page_ids(),
        }

    def __len__(self):
        return len(self._cache)

    def __repr__(self):
        return "BufferPool(policy=%s, cached=%d/%d, hit_rate=%.2f%%)" % (
            self.policy, len(self._cache), self.capacity, self.hit_rate * 100,
        )
