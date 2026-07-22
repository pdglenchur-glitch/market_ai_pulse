"""Phase 1 thin vertical slice (step 1.8): query the bronze table to confirm
the full chain — API -> R2 -> volume -> Delta table — actually works.
"""
from warehouse import connect


def main() -> None:
    conn = connect()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM workspace.bronze.market_data")
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        print(f"Columns: {columns}")
        for row in rows:
            print(dict(zip(columns, row)))
    conn.close()


if __name__ == "__main__":
    main()
