import asyncio
import asyncpg

async def test():
    try:
        conn = await asyncpg.connect('postgresql://lawer:lawer_password@localhost:5433/lawer')
        print('OK - connected')
        await conn.close()
    except Exception as e:
        print(f'ERROR: {e}')

asyncio.run(test())
