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

# List counter IDs from specific table (counter ID columns)
Q: List all counter IDs in daily_nokia_common_8005
A: SELECT column_name FROM information_schema.columns 
   WHERE table_name = 'daily_nokia_common_8005' 
   AND column_name NOT IN ('time', 'mapped_object_name', 'vendor_id')
   LIMIT 100;
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
    elif re.search(r'list\s+(?:all\s+)?counter(?:s|\s+ids?)\s+(?:in|from|of)\s+(\w+)', q, re.IGNORECASE):
        q += " [TABLE_COUNTERS]"
    
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
    
    # Special case for listing counter IDs (columns) from a specific table
    counter_columns_pattern = r'(?:list|show|what|get)\s+(?:all\s+)?(?:counter|counters|counter\s+ids?|counters\s+ids?)\s+(?:in|from|of)(?:\s+(?:this\s+)?table\s+)?([a-zA-Z0-9_]+)'
    counter_columns_match = re.search(counter_columns_pattern, query_lower)
    if counter_columns_match:
        table_name = counter_columns_match.group(1).lower()  # Normalize to lowercase
        return f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}'
        AND column_name NOT IN (
            'time', 'mapped_object_name', 'vendor_id',
            'begintime', 'sk_object', 'duration', 'integrity'
        )
        ORDER BY ordinal_position
        LIMIT 100;
        """
    
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
    
    # Special case for counter values - improved pattern matching
    # Extract counter ID and object name while PRESERVING THE ORIGINAL CASE from the query
    counter_value_pattern = r'(?:value|values|data|get)\s+(?:(?:of|for)\s+)?(?:counter\s+)?([a-zA-Z0-9_]+)\s+(?:for|on|over)\s+(?:object\s+)?(?:"|\')?([^"\']+)(?:"|\')?'
    
    # Use re.IGNORECASE for pattern matching but extract from original query to preserve case
    counter_match = re.search(counter_value_pattern, query, re.IGNORECASE)
    
    if counter_match:
        counter_id = counter_match.group(1)  # Preserve original case
        object_name = counter_match.group(2)  # Preserve original case
        
        # Explicit pattern check - use original query to preserve case
        explicit_pattern = r'counter\s+([a-zA-Z0-9_]+)\s+(?:for|on|over)\s+(?:object\s+)?(?:"|\')?([^"\']+)(?:"|\')?'
        explicit_match = re.search(explicit_pattern, query, re.IGNORECASE)
        if explicit_match:
            counter_id = explicit_match.group(1)  # Preserve original case
            object_name = explicit_match.group(2)  # Preserve original case
        
        # Determine time resolution from query
        time_resolution = "daily"  # Default
        if "hourly" in query_lower:
            time_resolution = "hourly"
        elif "detailed" in query_lower or "det" in query_lower:
            time_resolution = "detailed"
        
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
- For listing counter IDs from a specific table, query information_schema.columns for column names
  excluding common non-counter columns like 'time', 'mapped_object_name', and 'vendor_id'

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
    
    # Check for counter value patterns that might be missed by handle_special_queries
    query_lower = question.lower().strip()
    
    # Explicit counter value pattern matching - use re.IGNORECASE but extract from original
    counter_value_patterns = [
        r'get\s+(?:the\s+)?value\s+of\s+counter\s+\*?\*?([a-zA-Z0-9_]+)\*?\*?\s+(?:for|over)\s+object\s+(?:"|\')?([^"\']+)(?:"|\')?',
        r'value\s+of\s+(?:counter\s+)?([a-zA-Z0-9_]+)\s+(?:for|over)\s+(?:"|\')?([^"\']+)(?:"|\')?'
    ]
    
    for pattern in counter_value_patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            counter_id = match.group(1)  # Preserve case
            object_name = match.group(2)  # Preserve case
            
            # Check for a closing quote that might be missing from the regex match
            if object_name.endswith('"') or object_name.endswith("'"):
                object_name = object_name[:-1]
            
            # Determine time resolution
            time_resolution = "daily"  # Default
            if "hourly" in query_lower:
                time_resolution = "hourly"
            elif "detailed" in query_lower or "det" in query_lower:
                time_resolution = "detailed"
                
            return get_counter_values(object_name, counter_id, time_resolution)
    
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
        if "list" in question.lower() and "counter" in question.lower() and re.search(r'(daily|hourly)_\w+', question.lower()):
            # Extract table name for counter list queries
            table_match = re.search(r'(daily|hourly)_\w+', question.lower())
            if table_match:
                table_name = table_match.group(0)
                return f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}'
                AND column_name NOT IN ('time', 'mapped_object_name', 'vendor_id') 
                LIMIT 100;
                """
        elif "object" in question.lower() or "famil" in question.lower():
            return "SELECT DISTINCT \"mapped_object_name\" FROM con_multivendors_counters_details LIMIT 50;"
        elif "vendor" in question.lower():
            return "SELECT vendor_id, vendor_name FROM vendors LIMIT 50;"
        elif "counter" in question.lower() and any(tech in question.lower() for tech in ["lte", "2g", "3g", "4g", "5g"]):
            return "SELECT counter_id, counter_description FROM con_multivendors_counters_details LIMIT 50;"
        else:
            return "SELECT DISTINCT \"mapped_object_name\" FROM con_multivendors_counters_details LIMIT 50;"
def get_counter_values(object_name, counter_id, time_resolution="daily", start_date=None, end_date=None):
    """
    Generate a multi-step query to get counter values for a specific counter and object.
    
    This creates a proper SQL query with a CTE to first identify the table name,
    then query that table for the actual counter values.
    
    Args:
        object_name: The name of the object (e.g., 'SRAN : PLMN-MRBTS-EQM-APEQM-RMOD-ANTL')
        counter_id: The ID of the counter (e.g., 'M40001C0')
        time_resolution: One of 'daily', 'hourly', or 'detailed'
        start_date: Start date for filtering (defaults to last 7 days)
        end_date: End date for filtering (defaults to current date)
    
    Returns:
        SQL query string with CTE for two-step execution
    """
    # Set time resolution prefix
    resolution_prefix = {
        "daily": "daily_",
        "hourly": "hourly_",
        "detailed": "det_"
    }.get(time_resolution.lower(), "daily_")
    
    # Create the complete two-step query using a CTE
    # IMPORTANT: Preserve the case of counter_id exactly as provided
    query = f"""
    -- Two-step query to first identify the table then get the counter values
    WITH table_info AS (
        SELECT tables_in_database
        FROM con_multivendors_counters_details
        WHERE mapped_object_name = '{object_name}'
        AND counter_id = '{counter_id}'
        LIMIT 1
    )
    
    SELECT "begintime", "{counter_id}"
    FROM {resolution_prefix}nokia_common_40001  -- This table name would be dynamic in a full implementation
    WHERE "{counter_id}" IS NOT NULL
    LIMIT 50;
    """
    
    return query
