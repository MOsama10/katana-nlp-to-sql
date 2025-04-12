import os
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import re

# Load DB_URL from db_config.env
load_dotenv('db_config.env')
db_url = os.getenv("DB_URL")

# Normalize file names to table-safe names
def normalize_table_name(filename):
    return re.sub(r'[^a-zA-Z0-9_]', '_', filename.lower().split('.')[0])

def import_files_to_postgres(directory, db_url):
    engine = create_engine(db_url)
    files = os.listdir(directory)
    print(f"Found {len(files)} files in '{directory}'")

    for filename in files:
        filepath = os.path.join(directory, filename)
        table_name = normalize_table_name(filename)

        try:
            if filename.endswith('.csv'):
                print(f"📥 Importing CSV: {filename}")
                df = pd.read_csv(filepath)
            elif filename.endswith('.xlsx') or filename.endswith('.xls'):
                print(f"📥 Importing Excel: {filename}")
                df = pd.read_excel(filepath, engine='openpyxl')
            else:
                print(f"⏭ Skipping unsupported file: {filename}")
                continue

            df.to_sql(table_name, engine, if_exists='replace', index=False)
            print(f"✅ Imported to table: {table_name} ({len(df)} rows)")

        except Exception as e:
            print(f"❌ Failed to import {filename}: {e}")

if __name__ == "__main__":
    csv_directory = './raw_csv/'  # Keep as is if .xlsx files are here
    import_files_to_postgres(csv_directory, db_url)
