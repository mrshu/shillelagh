from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from shillelagh.backends.apsw.dialects.base import APSWDialect
from sqlalchemy.engine.url import URL


class APSWSafeDialect(APSWDialect):
    def __init__(
        self,
        adapters: Optional[List[str]] = None,
        adapter_kwargs: Optional[Dict[str, Dict[str, Any]]] = None,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self._adapters = adapters
        self._adapter_kwargs = adapter_kwargs or {}
        self._safe = True

    def create_connect_args(
        self,
        url: URL,
    ) -> Tuple[
        Tuple[
            str,
            Optional[List[str]],
            Optional[Dict[str, Dict[str, Any]]],
            bool,
            Optional[str],
        ],
        Dict[str, Any],
    ]:
        return (
            (
                ":memory:",
                self._adapters,
                self._adapter_kwargs,
                True,
                self.isolation_level,
            ),
            {},
        )
