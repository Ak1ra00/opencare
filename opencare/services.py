"""Shared application services handed to every UI page."""
from __future__ import annotations

from dataclasses import dataclass

from opencare.core.changes import ChangeStore
from opencare.core.env import Environment
from opencare.core.settings import Settings, get_settings
from opencare.engines.checkup import Checkup


@dataclass
class Services:
    env: Environment
    settings: Settings
    store: ChangeStore
    checkup: Checkup

    @classmethod
    def create(cls) -> "Services":
        env = Environment.real()
        settings = get_settings()
        store = ChangeStore(env)
        return cls(env=env, settings=settings, store=store, checkup=Checkup(env, settings, store))
