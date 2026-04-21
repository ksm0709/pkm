import pytest
import asyncio


@pytest.mark.anyio
async def test_async():
    await asyncio.sleep(0)
    assert True
