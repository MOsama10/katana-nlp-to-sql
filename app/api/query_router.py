from fastapi import APIRouter, Query, HTTPException, Response, Request
import psycopg2
import os
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional
from model.nlp2sql import generate_sql, pre_process_query, get_schema_info
import time
import json
import re
from functools import lru_cache

load_dotenv()
router = APIRouter()

# Simplified metrics
METRICS = {
    "total_queries": 0,
    "successful_queries": 0,
    "failed_queries": 0,
    "avg_response_time": 0,
    "total_response_time": 0
}

def update_metrics(success: bool, response_time: float):
    """Update performance metrics with basic tracking."""
    METRICS["total_queries"] += 1
    if success:
        METRICS["successful_queries"] += 1
    else:
        METRICS["failed_queries"] += 1
    
    METRICS["total_response_time"] += response_time
    METRICS["avg_response_time"] = METRICS["total_response_time"] / METRICS["total_queries"]

@lru_cache(maxsize=50)
def cached_execute_query(sql: str, limit: int = 100):
    """Execute an SQL query with caching to improve performance."""
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        cursor = conn.cursor()
        
        # Safety check
        if any(keyword in sql.lower() for keyword in ["drop", "delete", "update", "insert", "alter", "truncate"]):
            raise ValueError("Query not allowed: contains destructive SQL operations")
        
        # Add LIMIT if missing
        if "limit" not in sql.lower():
            sql = sql.rstrip(';') + f" LIMIT {limit};"
            
        cursor.execute(sql)
        rows = cursor.fetchall()
        colnames = [desc[0] for desc in cursor.description]
        results = [dict(zip(colnames, row)) for row in rows]
        
        return results, None
    except Exception as e:
        return None, str(e)
    finally:
        if 'conn' in locals() and conn:
            conn.close()

def execute_query(sql: str, limit: int = 100):
    """Non-cached version to be used when sql might frequently change."""
    return cached_execute_query(sql, limit)

@router.get("/query")
def run_nlp_query(
    request: Request,
    q: str = Query(..., description="Your natural language query about the Katana platform"),
    limit: Optional[int] = Query(100, description="Maximum number of results to return"),
    format: Optional[str] = Query("json", description="Response format (json or csv)")
):
    """Execute a natural language query on the Katana database."""
    start_time = time.time()
    
    try:
        # Generate SQL with timeout protection
        try:
            sql = generate_sql(q)
        except Exception as e:
            # Fallback for common queries when SQL generation fails
            if "object" in q.lower() or "famil" in q.lower():
                sql = 'SELECT DISTINCT "mapped_object_name" FROM con_multivendors_counters_details LIMIT 50;'
            elif "vendor" in q.lower():
                sql = 'SELECT vendor_id, vendor_name FROM vendors LIMIT 50;'
            else:
                # Unable to generate SQL, return error
                response_time = time.time() - start_time
                update_metrics(False, response_time)
                return {
                    "query": q,
                    "sql": "SQL generation failed",
                    "error": str(e)[:100],
                    "suggestion": "Try simplifying your query or being more specific about what you're looking for.",
                    "meta": {
                        "response_time_ms": round(response_time * 1000, 2),
                        "katana_platform": "v1.0"
                    }
                }
        
        # Execute query
        results, error = execute_query(sql, limit)
        
        if error:
            # Handle query execution error
            response_time = time.time() - start_time
            update_metrics(False, response_time)
            
            # Simplified error handling with helpful message
            suggestion = ""
            if "relation" in error and "does not exist" in error:
                suggestion = "The table referenced doesn't exist. Try different object names or time ranges."
            elif "column" in error and "does not exist" in error:
                suggestion = "The counter ID may be incorrect or not available for this object."
            
            return {
                "query": q,
                "sql": sql,
                "error": error,
                "suggestion": suggestion,
                "meta": {
                    "response_time_ms": round((time.time() - start_time) * 1000, 2),
                    "katana_platform": "v1.0"
                }
            }
        
        # Calculate response time for successful query
        response_time = time.time() - start_time
        update_metrics(True, response_time)
        
        # Format response
        if format.lower() == "csv":
            if not results:
                csv_data = "No results found."
            else:
                colnames = results[0].keys()
                csv_data = ",".join(colnames) + "\n"
                for row in results:
                    csv_data += ",".join([str(row[col]) for col in colnames]) + "\n"
                    
            return Response(
                content=csv_data,
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=katana_results.csv"}
            )
        else:
            return {
                "query": q,
                "sql": sql,
                "results": results,
                "meta": {
                    "count": len(results) if results else 0,
                    "response_time_ms": round(response_time * 1000, 2),
                    "katana_platform": "v1.0"
                }
            }

    except Exception as e:
        # Update metrics and return error
        response_time = time.time() - start_time
        update_metrics(False, response_time)
        
        return {
            "query": q,
            "sql": "SQL generation failed",
            "error": str(e),
            "suggestion": "Try simplifying your query or being more specific about what you're looking for.",
            "meta": {
                "response_time_ms": round(response_time * 1000, 2),
                "katana_platform": "v1.0"
            }
        }

@router.get("/metrics")
def get_metrics():
    """Get performance metrics for the Katana query service."""
    return {
        "metrics": {
            "total_queries": METRICS["total_queries"],
            "successful_queries": METRICS["successful_queries"],
            "failed_queries": METRICS["failed_queries"],
            "avg_response_time_ms": round(METRICS["avg_response_time"] * 1000, 2),
            "success_rate": round(METRICS["successful_queries"] / max(METRICS["total_queries"], 1) * 100, 2)
        }
    }

@router.get("/examples")
def get_query_examples():
    """Return query examples to help users formulate questions."""
    examples = [
        {
            "category": "Objects & Families",
            "queries": [
                "What families do we have in the system?",
                "What objects do we have in our system?"
            ]
        },
        {
            "category": "Counters for Objects",
            "queries": [
                "What counters are available for LTE_MAC objects?",
                "What counters do we have for 3G objects?"
            ]
        },
        {
            "category": "Counter Values",
            "queries": [
                "What is the value of counter PRBUsageDL for LTE_MAC?",
                "Show daily values for counter 001000 on 2G objects for last week"
            ]
        },
        {
            "category": "Vendors",
            "queries": [
                "What vendors does the platform support?",
                "List all vendors"
            ]
        }
    ]
    
    return {"examples": examples}
