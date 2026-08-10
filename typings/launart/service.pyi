from abc import abstractmethod
from contextlib import AbstractAsyncContextManager

from .manager import Launart
from .status import Phase, ServiceStage, ServiceStatus

class Service:
    id: str
    status: ServiceStatus
    manager: Launart | None

    def __init__(self) -> None: ...
    @property
    @abstractmethod
    def required(self) -> set[str]: ...
    @property
    @abstractmethod
    def stages(self) -> set[Phase]: ...
    def ensure_manager(self, manager: Launart) -> None: ...
    def stage(self, stage: Phase) -> AbstractAsyncContextManager[None]: ...
    async def wait_for_required(
        self,
        stage: ServiceStage | None = "prepared",
    ) -> None: ...
    async def wait_for(
        self,
        stage: ServiceStage | None,
        *component_id: str | type[Service],
    ) -> None: ...
    @abstractmethod
    async def launch(self, manager: Launart) -> None: ...
