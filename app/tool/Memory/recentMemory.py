from langgraph.store.base import  SearchItem

from app.tool.Memory.Interface.MemoryInterface import MemoryInterface


class RecentMemory(MemoryInterface):
    def search(self,query:str,limit:int=3) ->list[SearchItem]:
        return self.store.search(
            self.namespace,
            limit=limit,
        )