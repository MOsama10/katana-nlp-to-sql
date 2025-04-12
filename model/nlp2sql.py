# from model.model_loader import load_sqlcoder_llm
# from langchain.prompts import PromptTemplate

# llm = load_sqlcoder_llm()

# sql_template = PromptTemplate(
#     input_variables=["question", "schema_info"],
#     template="""
# You are an expert SQL assistant.
# The database has the following schema:
# {schema_info}

# Convert the following user question into a syntactically correct PostgreSQL query.
# Only return the SQL query. Do not include any explanations.

# Question: "{question}"
# SQL:
# """
# )

# def get_schema_info():
#     return """
# Table: con_multivendors_counters_details
# - counter_id: VARCHAR
# - counter_description: TEXT
# - mapped_object_name: VARCHAR
# - tables_in_database: VARCHAR

# Table: vendors
# - vendor_id: SERIAL
# - vendor_name: VARCHAR
# - vendor_description: TEXT
# """

# def generate_sql(question):
#     prompt = sql_template.format(question=question, schema_info=get_schema_info())
#     result = llm.invoke(prompt)
#     return result.strip()
from model.model_loader import load_sqlcoder_llm
from langchain.prompts import PromptTemplate
import psycopg2
import os
import json
from dotenv import load_dotenv

load_dotenv()
llm = load_sqlcoder_llm()

def load_katana_context(path="docs/training_data/parsed_content.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            sections = json.load(f)
        return "\n\n".join(
            f"{title}:\n{content.strip()}"
            for title, content in sections.items()
            if content.strip()
        )[:2000]
    except Exception as e:
        return f"-- Failed to load Katana PDF context: {e}"

def get_katana_examples():
    return """
# Objects and Families
Q: What families do we have in the system?
A: SELECT DISTINCT "mapped_object_name" FROM "con_multivendors_counters_details" LIMIT 50;

# Counters for an Object
Q: What is the list of counters covered for object X?
A: SELECT counter_id, counter_description FROM "con_multivendors_counters_details" WHERE "mapped_object_name" ILIKE '%X%' LIMIT 50;

# List counters for object type using fuzzy match
Q: What counters are available for 3G-related objects in the system?
A: SELECT DISTINCT counter_id FROM con_multivendors_counters_details WHERE mapped_object_name ILIKE '%3G%' ORDER BY counter_id;

# Counter Details for Object Y
Q: What is the table for counter PRBUsageDL in object LTE_MAC?
A: SELECT counter_id, counter_description, tables_in_database FROM "con_multivendors_counters_details" WHERE "mapped_object_name" ILIKE '%LTE_MAC%' AND counter_id = 'PRBUsageDL' LIMIT 1;

# Final Query Over Daily Table
Q: Get values for PRBUsageDL for LTE_MAC between April 1 and April 8.
A: SELECT * FROM daily_nokia_common_8005 WHERE time BETWEEN '2024-04-01' AND '2024-04-08' AND "PRBUsageDL" IS NOT NULL;

# Vendors
Q: What vendors does Katana support?
A: SELECT * FROM "vendors" LIMIT 50;
"""

katana_background = load_katana_context()
example_block = get_katana_examples()

from langchain.prompts import PromptTemplate

sql_template = PromptTemplate(
    input_variables=["question", "schema_info", "katana_context", "examples"],
    template="""
You are an expert SQL assistant working on the Katana platform.
Katana is an analytics platform that manages performance, vendors, counters, and operational data across multi-vendor networks.

Katana Background:
{katana_context}

Schema Snapshot:
{schema_info}

Follow these examples when converting questions to SQL:
{examples}

Instructions:
- Use ONLY the columns and tables from the schema.
- Do NOT invent values. Never use 'Katana' as a vendor name.
- Use double quotes for column names with spaces (e.g., "Alarm ID").
- When filtering based on object or vendor names, prefer partial matching using ILIKE and wildcards (e.g., ILIKE '%bsc%').
- Return only the final SQL. No explanation.

Question: "{question}"
SQL:
"""
)


def get_schema_info(max_tables=6, max_columns=6):
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
        """)
        rows = cursor.fetchall()
        conn.close()

        schema = {}
        for table, column, dtype in rows:
            schema.setdefault(table, []).append(f"- {column}: {dtype}")
        trimmed = dict(list(schema.items())[:max_tables])
        for table in trimmed:
            trimmed[table] = trimmed[table][:max_columns]

        return "\n\n".join([f"Table: {table}\n" + "\n".join(cols) for table, cols in trimmed.items()])
    except Exception as e:
        return f"-- Failed to fetch schema: {e}"

def pre_process_query(q: str) -> str:
    q = q.lower()
    if "katana" in q:
        q = q.replace("katana", "the platform")  # Stop model from misusing as value
    return q

def generate_sql(question: str) -> str:
    schema_info = get_schema_info()
    prompt = sql_template.format(
        question=question,
        schema_info=schema_info,
        katana_context=katana_background,
        examples=example_block
    )
    result = llm.invoke(prompt)
    return result.strip()


