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
        rows = await conn.fetch(
            "SELECT id, status, current_step, messages, created_at, last_message_at "
            "FROM whatsapp_sessions WHERE to_number='4915204465582' "
            "ORDER BY created_at DESC LIMIT 3"
        )
        for row in rows:
            import json
            msgs = row['messages'] if row['messages'] else []
            if isinstance(msgs, str):
                msgs = json.loads(msgs)
            print(f"\nSession {row['id']}: status={row['status']}, step={row['current_step']}")
            print(f"  Erstellt: {row['created_at']}, Letzte Msg: {row['last_message_at']}")
            print(f"  Nachrichten ({len(msgs)}):")
            for m in msgs[-4:]:
                role = m.get('role', '?')
                content = str(m.get('content', ''))[:100]
                print(f"    [{role}] {content}")
    await DatabaseClient.close_pool()

asyncio.run(main())
