import threading
from abc import ABC, abstractmethod

from langgraph.store.base import BaseStore, SearchItem


class MemoryInterface(ABC):
    def __init__(self,store:BaseStore,namespace:tuple[str,...])->None:
        self.store = store
        self.namespace = namespace
    @abstractmethod
    def search(self,query:str,limit:int=3)->list[SearchItem]:
        raise NotImplementedError

