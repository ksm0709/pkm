"""Typed aiohttp application keys used by web routes."""

from __future__ import annotations

from aiohttp import web

SEARCH_RUNNER_KEY = web.AppKey("pkm.search_runner", object)
