import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database import DatabaseClient
    await DatabaseClient.init_tables()
    pool = await DatabaseClient.get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE whatsapp_sessions SET status='cancelled' WHERE to_number='4915204465582' AND status IN ('pending','active')"
        )
        print("Alte Sessions deaktiviert:", result)
    await DatabaseClient.close_pool()

asyncio.run(main())
