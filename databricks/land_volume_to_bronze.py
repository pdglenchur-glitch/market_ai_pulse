"""Phase 1 thin vertical slice (step 1.7): read the landed file from the
raw_landing volume and create a bronze Delta table from it.

This is a one-off proof that the full chain works. From Phase 3 onward,
this read is formalized as a task inside the Lakeflow job instead.
"""
from warehouse import connect

VOLUME_FILE = "/Volumes/workspace/default/raw_landing/market_data.json"


def main() -> None:
    conn = connect()
    with conn.cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS workspace.bronze")
        cursor.execute(
            f"""
            CREATE OR REPLACE TABLE workspace.bronze.market_data AS
            SELECT * FROM read_files('{VOLUME_FILE}', format => 'json')
            """
        )
        print("Created/replaced workspace.bronze.market_data")
    conn.close()


if __name__ == "__main__":
    main()
