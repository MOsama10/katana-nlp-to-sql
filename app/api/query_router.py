# from fastapi import APIRouter, Query
# import psycopg2
# import os
# from dotenv import load_dotenv
# from model.nlp2sql import generate_sql

# load_dotenv()

# router = APIRouter()

# @router.get("/query")
# def run_nlp_query(q: str = Query(..., description="Your natural language query")):
#     sql = generate_sql(q)

#     try:
#         conn = psycopg2.connect(
#             dbname=os.getenv("DB_NAME"),
#             user=os.getenv("DB_USER"),
#             password=os.getenv("DB_PASSWORD"),
#             host=os.getenv("DB_HOST"),
#             port=os.getenv("DB_PORT")
#         )
#         cursor = conn.cursor()
#         cursor.execute(sql)
#         rows = cursor.fetchall()
#         colnames = [desc[0] for desc in cursor.description]
#         results = [dict(zip(colnames, row)) for row in rows]

#         return {
#             "query": q,
#             "sql": sql,
#             "results": results
#         }

#     except Exception as e:
#         return {"query": q, "sql": sql, "error": str(e)}
from fastapi import APIRouter, Query
import psycopg2
import os
from dotenv import load_dotenv
from model.nlp2sql import generate_sql, pre_process_query

load_dotenv()
router = APIRouter()

@router.get("/query")
def run_nlp_query(q: str = Query(..., description="Your natural language query about the Katana platform")):
    cleaned = pre_process_query(q)
    sql = generate_sql(cleaned)

    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        colnames = [desc[0] for desc in cursor.description]
        results = [dict(zip(colnames, row)) for row in rows]
        conn.close()

        return {
            "query": q,
            "sql": sql,
            "results": results or [],
            "note": "Query executed successfully on the Katana platform." if results else "No results found for this Katana query."
        }

    except Exception as e:
        return {
            "query": q,
            "sql": sql,
            "error": str(e),
            "hint": "Ensure tables/columns referenced exist. Katana avoids guessing invalid names or values."
        }
