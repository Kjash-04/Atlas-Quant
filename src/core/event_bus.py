"""
Asynchronous In-Memory & Redis Event Bus.
Dispatches MarketSnapshots, Agent messages, and Risk notifications.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Any], Any]]] = {}

    def subscribe(self, topic: str, handler: Callable[[Any], Any]) -> None:
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)
        logger.debug(f"Subscribed handler to topic '{topic}'")

    def publish(self, topic: str, message: Any) -> None:
        handlers = self._subscribers.get(topic, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(message))
                else:
                    handler(message)
            except Exception as e:
                logger.error(f"Error executing event handler for topic '{topic}': {e}")


event_bus = EventBus()
