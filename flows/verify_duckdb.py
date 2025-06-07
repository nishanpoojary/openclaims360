import duckdb
import os
from flows import config

# Construct the path to the DuckDB file
db_path = os.path.join(config.GOLD_DATA_PATH, config.DUCKDB_FILENAME)
table_name = config.DUCKDB_GOLD_TABLE_NAME

if os.path.exists(db_path):
    try:
        con = duckdb.connect(database=db_path, read_only=True)
        print(f"Connected to {db_path}")
        result = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        if result:
            print(f"Table '{table_name}' contains {result[0]} rows.")

        # Optional: print a few sample rows
        sample_data = con.execute(f"SELECT * FROM {table_name} LIMIT 5").fetchdf()
        print("Sample data:")
        print(sample_data)

        con.close()
    except Exception as e:
        print(f"Error querying DuckDB: {e}")
else:
    print(f"DuckDB file not found at {db_path}")