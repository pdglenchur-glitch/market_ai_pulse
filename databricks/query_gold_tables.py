from warehouse import connect

TABLES = [
    "market_daily",
    "sector_rotation",
    "volatility",
    "macro_snapshot",
    "ai_vs_market",
    "attention_index",
    "dev_momentum",
    "research_pace",
]


def main() -> None:
    conn = connect()
    with conn.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"SELECT * FROM workspace.gold.{table} LIMIT 5")
            columns = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            cursor.execute(f"SELECT COUNT(*) FROM workspace.gold.{table}")
            count = cursor.fetchone()[0]
            print(f"--- {table} (count={count}) ---")
            print(f"columns: {columns}")
            for row in rows:
                print(dict(zip(columns, row)))
    conn.close()


if __name__ == "__main__":
    main()
