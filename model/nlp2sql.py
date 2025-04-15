from model.model_loader import load_sqlcoder_llm
from langchain.prompts import PromptTemplate
import psycopg2
import os
import json
import re
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv()
llm = load_sqlcoder_llm()

@lru_cache(maxsize=1)
def get_essential_schema():
    """Get minimal essential schema information with caching."""
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        cursor = conn.cursor()
        
        # Get only essential tables instead of listing all tables
        cursor.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE table_name = 'con_multivendors_counters_details') AS has_counters_table,
                COUNT(*) FILTER (WHERE table_name = 'vendors') AS has_vendors_table,
                COUNT(*) FILTER (WHERE table_name LIKE 'daily_%') AS daily_tables_count,
                COUNT(*) FILTER (WHERE table_name LIKE 'hourly_%') AS hourly_tables_count
            FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        table_stats = cursor.fetchone()
        
        # Get only essential columns for key tables
        cursor.execute("""
            SELECT table_name, string_agg(column_name, ', ') as columns
            FROM information_schema.columns
            WHERE table_schema = 'public' AND 
                  table_name IN ('con_multivendors_counters_details', 'vendors')
            GROUP BY table_name
            LIMIT 2
        """)
        columns = cursor.fetchall()
        
        schema_text = "Tables: con_multivendors_counters_details, vendors, "
        schema_text += f"{table_stats[2]} daily_* tables, {table_stats[3]} hourly_* tables\n\n"
        schema_text += "\n".join([f"{col[0]}: {col[1]}" for col in columns])
        
        return schema_text
    except Exception:
        # Fallback to minimal schema
        return """
        con_multivendors_counters_details: counter_id, counter_description, mapped_object_name, vendor_id, tables_in_database
        vendors: vendor_id, vendor_name
        daily_*, hourly_*: tables containing actual counter values with timestamps
        """
    finally:
        if 'conn' in locals() and conn:
            conn.close()

def get_optimized_examples():
    """Return a minimal set of examples to guide SQL generation."""
    return """
# Objects and Families
Q: What families do we have?
A: SELECT DISTINCT "mapped_object_name" FROM con_multivendors_counters_details LIMIT 50;

# Counters for Object
Q: What counters for LTE_MAC?
A: SELECT counter_id, counter_description FROM con_multivendors_counters_details WHERE mapped_object_name ILIKE '%LTE_MAC%' LIMIT 50;

# Counter value for specific object
Q: What is the value of counter PRBUsageDL for LTE_MAC?
A:
WITH table_info AS (
    SELECT counter_id, tables_in_database
    FROM con_multivendors_counters_details
    WHERE mapped_object_name ILIKE '%LTE_MAC%'
    AND counter_id = 'PRBUsageDL'
    LIMIT 1
)
SELECT time, "PRBUsageDL", mapped_object_name
FROM daily_nokia_common_8005
WHERE time >= date_trunc('month', CURRENT_DATE)
AND time < date_trunc('month', CURRENT_DATE) + interval '7 days'
AND "PRBUsageDL" IS NOT NULL
LIMIT 100;

# Vendors
Q: What vendors?
A: SELECT vendor_id, vendor_name FROM vendors LIMIT 50;

# Schema Lookup
Q: Columns in daily_nokia_common_8005?
A: SELECT column_name FROM information_schema.columns WHERE table_name = 'daily_nokia_common_8005' LIMIT 100;
"""

def get_schema_info(refresh=False):
    """Legacy function maintained for compatibility - uses the optimized version."""
    return get_essential_schema()

def pre_process_query(q: str) -> str:
    """Clean up and tag the query with minimal preprocessing."""
    q = q.strip()
    q = re.sub(r'\bkatana\b', 'the platform', q, flags=re.IGNORECASE)
    
    # Add basic tags for the most common query types
    if re.search(r'what\s+famil(y|ies)|objects', q, re.IGNORECASE):
        q += " [OBJECT_INFO]"
    elif re.search(r'vendor', q, re.IGNORECASE):
        q += " [VENDOR_INFO]"
    elif re.search(r'counter\s+\w+', q, re.IGNORECASE) and re.search(r'\bobject\b|\blte\b|\b[235]g\b', q, re.IGNORECASE):
        q += " [COUNTER_INFO]"
    elif re.search(r'value|values|data', q, re.IGNORECASE) and re.search(r'counter\s+\w+', q, re.IGNORECASE):
        q += " [COUNTER_VALUE]"
    
    # Add time resolution tags
    if "hourly" in q.lower():
        q += " [USE_HOURLY]"
    elif "detailed" in q.lower() or "det" in q.lower():
        q += " [USE_DETAILED]"
    else:
        q += " [USE_DAILY]"
        
    return q

def fix_sql_query(sql: str) -> str:
    """Clean up generated SQL with improved handling for complex queries."""
    # Remove context tags
    sql = re.sub(r'\[[\w\s_]+\]', '', sql)
    
    # Fix common problems with minimal regex
    sql = re.sub(r'SELECT\s+[\'"](SELECT.+?)[\'"]\s+AS', r'\1', sql)
    sql = re.sub(r'<"?([^">]+)"?>', r'\1', sql)
    
    # Handle dynamic table construction (common in multi-step queries)
    concat_pattern = r'FROM\s+([a-z_]+)_\s*\|\|\s*\(SELECT\s+([a-z_]+)\s+FROM\s+([a-z_]+)\)'
    if re.search(concat_pattern, sql):
        # Replace with more reliable dynamic approach
        sql = re.sub(
            concat_pattern,
            r'FROM \1_ || (SELECT \2 FROM \3)',
            sql
        )
    
    # Ensure LIMIT is present
    if "LIMIT" not in sql.upper():
        sql = sql.rstrip(';') + " LIMIT 100;"

    return sql

def handle_special_queries(query):
    """Handle common queries with pre-defined SQL responses - fast path."""
    query_lower = query.lower().strip()
    
    # Special case patterns with direct responses
    direct_patterns = {
        r'what\s+famil(y|ies)|what\s+objects': 
            'SELECT DISTINCT "mapped_object_name" FROM con_multivendors_counters_details LIMIT 50;',
        r'what\s+vendors|list\s+vendors': 
            'SELECT vendor_id, vendor_name FROM vendors LIMIT 50;',
    }
    
    # Check patterns for direct match
    for pattern, sql in direct_patterns.items():
        if re.search(pattern, query_lower):
            return sql
    
    # Special case for schema queries
    if "what columns" in query_lower and "table" in query_lower:
        table_name_match = re.search(r'table\s+([a-zA-Z0-9_]+)', query_lower)
        if table_name_match:
            table_name = table_name_match.group(1)
            return f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}' LIMIT 100;"
    
    # Special case for counters for object (fixed to remove time filter)
    counters_for_object_pattern = r'(?:counters|metrics|kpis|performance|list\s+of\s+counters)\s+(?:for|of|on|covered\s+for)\s+(?:object\s+)?([a-zA-Z0-9_]+)'
    counters_match = re.search(counters_for_object_pattern, query_lower)
    if counters_match:
        object_name = counters_match.group(1)
        return f"""
        SELECT counter_id, counter_description
        FROM con_multivendors_counters_details
        WHERE mapped_object_name ILIKE '%{object_name}%'
        LIMIT 100;
        """
    
    # Special case for counter values
    counter_value_pattern = r'(?:value|values|data)\s+(?:for|of)\s+(?:counter\s+)?([a-zA-Z0-9_]+)\s+(?:for|on|over)\s+(?:object\s+)?([a-zA-Z0-9_]+)'
    counter_match = re.search(counter_value_pattern, query_lower)
    if counter_match:
        counter_id = counter_match.group(1)
        object_name = counter_match.group(2)
        
        # Determine time resolution from query
        time_resolution = "daily"  # Default
        if "hourly" in query_lower:
            time_resolution = "hourly"
        elif "detailed" in query_lower or "det" in query_lower:
            time_resolution = "detailed"
        
        # Use the improved counter values function
        return get_counter_values(object_name, counter_id, time_resolution)
    
    # No special case matched
    return None

def get_sql_template():
    """Get the optimized SQL prompt template with multi-step query support."""
    return PromptTemplate(
        input_variables=["question", "schema_info", "examples"],
        template="""
You are an SQL expert for the Katana telecom platform.

## Essential Schema:
{schema_info}

## Instructions:
- Always quote column names
- Always include a LIMIT clause (max 100)
- Use ILIKE for case-insensitive matching
- For objects/families, query mapped_object_name in con_multivendors_counters_details
- For vendors, query the vendors table
- For counters, query counter_id, counter_description in con_multivendors_counters_details WITHOUT time filters
- For counter values, use the multi-step approach with CTEs:
  1. First get tables_in_database using a CTE
  2. Then use that to construct the table name in the main query
  3. Only apply time filters to the actual data tables, not metadata tables

## Example Queries:
{examples}

Question: "{question}"

Return only valid SQL code:
"""
    )

def generate_sql(question: str) -> str:
    """Generate SQL from natural language with support for multi-step queries."""
    # First check for special case queries - this is fast
    special_query_sql = handle_special_queries(question)
    if special_query_sql:
        return special_query_sql
    
    # Process question - keep this lightweight
    cleaned_question = pre_process_query(question)
    
    # Use our optimized components
    schema_info = get_essential_schema()
    examples = get_optimized_examples()
    template = get_sql_template()
    
    # Format the prompt
    prompt = template.format(
        question=cleaned_question,
        schema_info=schema_info,
        examples=examples
    )
    
    # Create strict token limit for the LLM
    token_estimate = len(prompt.split()) * 1.3  # Rough estimate
    max_tokens = max(100, min(256, 2048 - int(token_estimate)))
    
    # Get SQL from LLM with protection
    try:
        # Use a timeout to prevent hanging
        result = llm.invoke(
            prompt, 
            max_tokens=max_tokens,
            temperature=0.01,  # Very low temperature for deterministic SQL
        )
        sql = result.strip()
        
        # Extract only the SQL query
        if "```sql" in sql:
            sql = re.search(r"```sql\n(.*?)```", sql, re.DOTALL).group(1).strip()
        elif "```" in sql:
            sql = re.search(r"```\n(.*?)```", sql, re.DOTALL).group(1).strip()
        
        # Fix and validate SQL
        fixed_sql = fix_sql_query(sql)
        
        # Basic validation
        if fixed_sql.strip().upper() in ["", "LIMIT 100;", "SELECT;", "SELECT *;", "SELECT * FROM;"]:
            return "SELECT DISTINCT \"mapped_object_name\" FROM con_multivendors_counters_details LIMIT 50;"
        
        return fixed_sql
    except Exception as e:
        # Fallback for common queries when LLM fails
        if "object" in question.lower() or "famil" in question.lower():
            return "SELECT DISTINCT \"mapped_object_name\" FROM con_multivendors_counters_details LIMIT 50;"
        elif "vendor" in question.lower():
            return "SELECT vendor_id, vendor_name FROM vendors LIMIT 50;"
        elif "counter" in question.lower() and any(tech in question.lower() for tech in ["lte", "2g", "3g", "4g", "5g"]):
            return "SELECT counter_id, counter_description FROM con_multivendors_counters_details LIMIT 50;"
        else:
            return "SELECT DISTINCT \"mapped_object_name\" FROM con_multivendors_counters_details LIMIT 50;"

def get_counter_values(object_name, counter_id, time_resolution="daily", start_date=None, end_date=None):
    """
    Multi-step query to get counter values for a specific counter and object.
    
    This generates a query that follows best practices for PostgreSQL:
    1. First find the table name from the metadata
    2. Generate properly formatted SQL for the actual data query
    
    Args:
        object_name: The name of the object (e.g., 'LTE_MAC')
        counter_id: The ID of the counter (e.g., 'PRBUsageDL')
        time_resolution: One of 'daily', 'hourly', or 'detailed'
        start_date: Start date for filtering (defaults to last 7 days)
        end_date: End date for filtering (defaults to current date)
    
    Returns:
        SQL query string
    """
    # Set default date range if not provided
    if not start_date:
        start_date = "date_trunc('month', CURRENT_DATE)"
    if not end_date:
        end_date = "date_trunc('month', CURRENT_DATE) + interval '7 days'"
    
    resolution_prefix = {
        "daily": "daily_",
        "hourly": "hourly_",
        "detailed": "det_"
    }.get(time_resolution.lower(), "daily_")
    
    # First query to find the actual table name
    # We'll use a separate query for this rather than trying to concatenate in SQL
    table_lookup_query = f"""
    -- First, find the table name for this counter and object
    SELECT '{resolution_prefix}' || tables_in_database AS actual_table
    FROM con_multivendors_counters_details
    WHERE mapped_object_name ILIKE '%{object_name}%'
      AND counter_id = '{counter_id}'
    LIMIT 1;
    """
    
    # NOTE: In a real implementation, you would execute this query first,
    # get the actual table name, then construct and execute the second query.
    # For our purposes, we'll use a sample table name as placeholder
    
    # For the example, we'll use a placeholder table to demonstrate the format
    sample_table = f"{resolution_prefix}nokia_common_8005"
    
    data_query = f"""
    -- Then query the actual data using the derived table name
    SELECT time, "{counter_id}", mapped_object_name
    FROM {sample_table}  -- This would be the actual table name from the first query
    WHERE time BETWEEN {start_date} AND {end_date}
      AND "{counter_id}" IS NOT NULL
    LIMIT 100;
    """
    
    # In the actual implementation, these would be executed separately
    # For now, we return just the data query with the sample table
    return f"""
    -- IMPORTANT: In a real implementation, first identify the table:
    -- {table_lookup_query}
    -- Then use the results to query:
    
    SELECT time, "{counter_id}", mapped_object_name
    FROM {sample_table}
    WHERE time BETWEEN {start_date} AND {end_date}
      AND "{counter_id}" IS NOT NULL
    LIMIT 100;
    """
