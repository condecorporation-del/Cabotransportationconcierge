import time
from collections import Counter
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status


def rate_limit(limit: int, per_seconds: int = 60) -> Callable[[Request], Awaitable[None]]:
    """Ventana fija por ruta e IP; el contador se reinicia al cambiar de ventana.

    Vive en `app.state.rate_limits` (una instancia). F13.3 lo mueve a un almacén compartido.
    La IP real detrás del proxy llega con `uvicorn --proxy-headers`.
    """

    async def check(request: Request) -> None:
        now = time.time()
        window = int(now // per_seconds)
        route = request.scope["route"].path
        store: dict[str, tuple[int, Counter[str]]] = request.app.state.rate_limits
        current, hits = store.get(route, (window, Counter()))
        if current != window:
            hits = Counter()
        store[route] = (window, hits)
        client = request.client.host if request.client else "unknown"
        hits[client] += 1
        if hits[client] > limit:
            retry_after = per_seconds - int(now % per_seconds)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests. Try again shortly.",
                headers={"Retry-After": str(retry_after)},
            )

    return check
