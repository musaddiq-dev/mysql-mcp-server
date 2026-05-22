import os
import logging
import re
import mysql.connector
from mysql.connector import pooling, Error
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from typing_extensions import Annotated

# Load environment variables
load_dotenv()

# Configure structured logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("mysql-mcp-server")

# Create MCP server
mcp = FastMCP("mysql_mcp")

# Connection Pool Configuration
POOL_NAME = "mysql_mcp_pool"
POOL_SIZE = int(os.getenv("MYSQL_POOL_SIZE", "5"))
pool = None
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")
READ_QUERY_LIMIT = int(os.getenv("MYSQL_READ_QUERY_LIMIT", "1000"))


def validate_identifier(identifier: str, kind: str = "identifier") -> str:
    """Validate a MySQL identifier before using it in quoted SQL."""
    if not IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(
            f"Invalid {kind}: {identifier!r}. Use only letters, numbers, and underscores."
        )
    return identifier


def validate_environment() -> None:
    missing_vars = [name for name in ("MYSQL_DATABASE",) if not os.getenv(name)]
    if missing_vars:
        raise ValueError(
            "Missing required environment variables: "
            f"{', '.join(missing_vars)}. Set them in your environment or .env file."
        )


def initialize_connection_pool():
    """Initialize the MySQL connection pool."""
    global pool
    try:
        pool_config = {
            "host": os.getenv("MYSQL_HOST", "localhost"),
            "user": os.getenv("MYSQL_USER", "root"),
            "password": os.getenv("MYSQL_PASSWORD", ""),
            "database": os.getenv("MYSQL_DATABASE", ""),
            "port": int(os.getenv("MYSQL_PORT", "3306"))
        }
        pool = pooling.MySQLConnectionPool(
            pool_name=POOL_NAME,
            pool_size=POOL_SIZE,
            pool_reset_session=True,
            **pool_config
        )
        logger.info(f"Connection pool '{POOL_NAME}' initialized with size {POOL_SIZE}")
        logger.debug(f"Pool config: host={pool_config['host']}, user={pool_config['user']}, database={pool_config['database']}")
    except Error as e:
        logger.error(f"Failed to initialize connection pool: {e}")
        raise


def get_db_connection():
    """Get a connection from the pool."""
    global pool
    if pool is None:
        try:
            initialize_connection_pool()
        except Exception as e:
            logger.error(f"Cannot initialize connection pool: {e}")
            raise
    try:
        conn = pool.get_connection()
        logger.debug("Acquired connection from pool")
        return conn
    except Error as e:
        logger.error(f"Failed to get connection from pool: {e}")
        raise


@mcp.tool(
    name="mysql_list_tables",
    annotations=ToolAnnotations(title="List MySQL Tables", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def list_tables() -> list[str]:
    """
    List all tables in the database.
    
    Returns:
        A list of table names.
    """
    logger.info("Tool called: list_tables")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        logger.debug(f"Found {len(tables)} tables")
        
        # Extract table names from tuples
        result = [table[0] for table in tables]
        return result
    except Error as e:
        logger.error(f"Error in list_tables: {e}")
        raise
    finally:
        cursor.close()
        conn.close()
        logger.debug("Connection returned to pool")


@mcp.tool(
    name="mysql_describe_table",
    annotations=ToolAnnotations(title="Describe MySQL Table", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def describe_table(
    table_name: Annotated[str, Field(description="Table name to describe", min_length=1, max_length=128)],
) -> list[dict]:
    """
    Describe the schema of a specific table.
    
    Args:
        table_name: The name of the table to describe.
    
    Returns:
        A list of dictionaries containing column information.
    """
    table_name = validate_identifier(table_name, "table name")
    logger.info(f"Tool called: describe_table with table_name='{table_name}'")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(f"DESCRIBE `{table_name}`")
        columns = cursor.fetchall()
        logger.debug(f"Described table '{table_name}', found {len(columns)} columns")
        
        # Convert to list of dictionaries
        result = []
        for col in columns:
            result.append({
                "field": col[0],
                "type": col[1],
                "null": col[2],
                "key": col[3],
                "default": col[4],
                "extra": col[5]
            })
        return result
    except Error as e:
        logger.error(f"Error describing table '{table_name}': {e}")
        raise
    finally:
        cursor.close()
        conn.close()
        logger.debug("Connection returned to pool")


@mcp.tool(
    name="mysql_execute_read_query",
    annotations=ToolAnnotations(title="Execute MySQL Read Query", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def execute_read_query(
    query: Annotated[str, Field(description="Single MySQL SELECT query to execute", min_length=1, max_length=100000)],
) -> list[dict]:
    """
    Execute a SELECT query and return the results.
    
    This tool only allows SELECT statements for safety. It prevents
    DROP, DELETE, INSERT, UPDATE, and other potentially dangerous statements.
    
    Args:
        query: The SQL SELECT query to execute.
    
    Returns:
        A list of dictionaries containing the query results.
    
    Raises:
        ValueError: If the query is not a valid SELECT statement.
    """
    logger.info(f"Tool called: execute_read_query")
    logger.debug(f"Query: {query[:200]}{'...' if len(query) > 200 else ''}")
    
    # Convert to uppercase for checking
    query_upper = query.strip().upper()
    
    # Check if query starts with SELECT
    if not query_upper.startswith("SELECT"):
        logger.warning(f"Rejected non-SELECT query: {query[:100]}")
        raise ValueError(
            "Only SELECT statements are allowed for safety. "
            "DROP, DELETE, INSERT, UPDATE, and other modifying statements are prohibited."
        )
    
    if ";" in query.strip().rstrip(";"):
        raise ValueError("Multiple SQL statements are not allowed.")

    # Additional safety check: prevent dangerous keywords even if they appear elsewhere
    # Use word boundaries to avoid false positives (e.g., "updated_at" should not trigger "UPDATE" check)
    dangerous_keywords = [
        "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE",
        "INTO OUTFILE", "INTO DUMPFILE", "LOAD_FILE", "LOCK", "UNLOCK",
    ]
    for keyword in dangerous_keywords:
        # Use regex word boundary to match only whole keywords, not substrings
        pattern = r'\b' + re.escape(keyword).replace(r'\ ', r'\s+') + r'\b'
        if re.search(pattern, query_upper):
            logger.warning(f"Rejected query containing dangerous keyword '{keyword}': {query[:100]}")
            raise ValueError(
                f"Dangerous keyword '{keyword}' detected. "
                "Only SELECT statements are allowed for safety."
            )
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute(query)
        results = cursor.fetchmany(READ_QUERY_LIMIT + 1)
        if len(results) > READ_QUERY_LIMIT:
            results = results[:READ_QUERY_LIMIT]
            logger.warning("Read query results truncated at %s rows", READ_QUERY_LIMIT)
        logger.debug(f"Query returned {len(results)} rows")
        return results
    except Error as e:
        logger.error(f"Error executing read query: {e}")
        raise
    finally:
        cursor.close()
        conn.close()
        logger.debug("Connection returned to pool")


@mcp.tool(
    name="mysql_execute_write_query",
    annotations=ToolAnnotations(title="Execute MySQL Write Query", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False),
)
def execute_write_query(
    query: Annotated[str, Field(description="Single INSERT, UPDATE, or DELETE query to execute", min_length=1, max_length=100000)],
) -> dict:
    """
    Execute a data modification query (INSERT, UPDATE, DELETE) and return the results.
    
    This tool allows executing DML (Data Manipulation Language) statements that modify
    data in the database. It explicitly validates that only INSERT, UPDATE, or DELETE
    statements are executed.
    
    WARNING: This tool modifies data. Use with caution.
    
    Args:
        query: The SQL INSERT, UPDATE, or DELETE query to execute.
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if the operation was successful
        - message: Human-readable message describing the result
        - rows_affected: Number of rows affected by the operation
    
    Raises:
        ValueError: If the query is not a valid INSERT, UPDATE, or DELETE statement.
    """
    logger.info(f"Tool called: execute_write_query")
    logger.debug(f"Query: {query[:200]}{'...' if len(query) > 200 else ''}")
    
    if ";" in query.strip().rstrip(";"):
        raise ValueError("Multiple SQL statements are not allowed.")

    # Convert to uppercase for checking
    query_upper = query.strip().upper()
    
    # Check if query starts with INSERT, UPDATE, or DELETE
    valid_starts = ["INSERT", "UPDATE", "DELETE"]
    is_valid_start = any(query_upper.startswith(start) for start in valid_starts)
    
    if not is_valid_start:
        logger.warning(f"Rejected invalid write query: {query[:100]}")
        raise ValueError(
            "Only INSERT, UPDATE, and DELETE statements are allowed. "
            "For SELECT queries, use execute_read_query. "
            "For schema operations (CREATE, DROP, ALTER, TRUNCATE), use execute_ddl."
        )
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(query)
        rows_affected = cursor.rowcount
        conn.commit()
        
        logger.info(f"Write query executed successfully, {rows_affected} row(s) affected")
        return {
            "success": True,
            "message": f"Query executed successfully. {rows_affected} row(s) affected.",
            "rows_affected": rows_affected
        }
    except Error as e:
        conn.rollback()
        logger.error(f"Error executing write query: {e}")
        return {
            "success": False,
            "message": f"Error executing query: {str(e)}",
            "rows_affected": 0
        }
    finally:
        cursor.close()
        conn.close()
        logger.debug("Connection returned to pool")


@mcp.tool(
    name="mysql_execute_ddl",
    annotations=ToolAnnotations(title="Execute MySQL DDL", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False),
)
def execute_ddl(
    query: Annotated[str, Field(description="Single CREATE, DROP, ALTER, or TRUNCATE statement", min_length=1, max_length=100000)],
) -> dict:
    """
    Execute a DDL (Data Definition Language) statement for schema modifications.
    
    This tool allows executing schema changes like CREATE TABLE, DROP TABLE,
    ALTER TABLE, and TRUNCATE TABLE.
    
    WARNING: This tool modifies database schema and can result in data loss.
    Use with extreme caution.
    
    Args:
        query: The SQL DDL query to execute (CREATE, DROP, ALTER, TRUNCATE).
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if the operation was successful
        - message: Human-readable message describing the result
    
    Raises:
        ValueError: If the query is not a valid DDL statement.
    """
    logger.info(f"Tool called: execute_ddl")
    logger.debug(f"DDL Query: {query[:200]}{'...' if len(query) > 200 else ''}")
    
    if ";" in query.strip().rstrip(";"):
        raise ValueError("Multiple SQL statements are not allowed.")

    # Convert to uppercase for checking
    query_upper = query.strip().upper()
    
    # Check if query starts with valid DDL keywords
    valid_starts = ["CREATE", "DROP", "ALTER", "TRUNCATE"]
    is_valid_start = any(query_upper.startswith(start) for start in valid_starts)
    
    if not is_valid_start:
        logger.warning(f"Rejected invalid DDL query: {query[:100]}")
        raise ValueError(
            "Only CREATE, DROP, ALTER, and TRUNCATE statements are allowed. "
            "For SELECT queries, use execute_read_query. "
            "For data modifications (INSERT, UPDATE, DELETE), use execute_write_query."
        )
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(query)
        conn.commit()
        logger.info("DDL statement executed successfully")
        return {
            "success": True,
            "message": "DDL statement executed successfully."
        }
    except Error as e:
        conn.rollback()
        logger.error(f"Error executing DDL statement: {e}")
        return {
            "success": False,
            "message": f"Error executing DDL statement: {str(e)}"
        }
    finally:
        cursor.close()
        conn.close()
        logger.debug("Connection returned to pool")


@mcp.tool(
    name="mysql_get_table_ddl",
    annotations=ToolAnnotations(title="Get MySQL Table DDL", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def get_table_ddl(
    table_name: Annotated[str, Field(description="Table name to inspect", min_length=1, max_length=128)],
) -> str:
    """
    Get the DDL (Data Definition Language) statement for creating a table.
    
    This function executes SHOW CREATE TABLE to get the exact SQL used to
    create the table, including foreign keys, indexes, and specific data types.
    
    Args:
        table_name: The name of the table to get DDL for.
    
    Returns:
        A string containing the CREATE TABLE statement.
    """
    table_name = validate_identifier(table_name, "table name")
    logger.info(f"Tool called: get_table_ddl with table_name='{table_name}'")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Use backticks to safely escape the table name
        cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
        result = cursor.fetchone()
        
        # The second column contains the CREATE TABLE statement
        if result and len(result) > 1:
            logger.debug(f"Retrieved DDL for table '{table_name}'")
            return result[1]
        else:
            logger.warning(f"Could not retrieve DDL for table '{table_name}'")
            return f"Error: Could not retrieve DDL for table '{table_name}'"
    except Error as e:
        logger.error(f"Error getting DDL for table '{table_name}': {e}")
        raise
    finally:
        cursor.close()
        conn.close()
        logger.debug("Connection returned to pool")


@mcp.tool(
    name="mysql_explain_query",
    annotations=ToolAnnotations(title="Explain MySQL Query", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def explain_query(
    query: Annotated[str, Field(description="Single SQL query to explain", min_length=1, max_length=100000)],
) -> list[dict]:
    """
    Explain the execution plan of a SQL query.
    
    This function prepends EXPLAIN to the provided SQL query and executes it
    to help analyze the performance and execution plan of complex queries.
    
    Args:
        query: The SQL query to explain.
    
    Returns:
        A list of dictionaries containing the execution plan details.
    """
    if ";" in query.strip().rstrip(";"):
        raise ValueError("Multiple SQL statements are not allowed.")

    logger.info(f"Tool called: explain_query")
    logger.debug(f"Query to explain: {query[:200]}{'...' if len(query) > 200 else ''}")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Prepend EXPLAIN to the query and execute
        explain_query_str = f"EXPLAIN {query}"
        cursor.execute(explain_query_str)
        results = cursor.fetchall()
        logger.debug(f"Explain query returned {len(results)} rows")
        return results
    except Error as e:
        logger.error(f"Error explaining query: {e}")
        raise
    finally:
        cursor.close()
        conn.close()
        logger.debug("Connection returned to pool")


@mcp.tool(
    name="mysql_get_database_summary",
    annotations=ToolAnnotations(title="Get MySQL Database Summary", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def get_database_summary() -> dict:
    """
    Get a comprehensive summary of the current database.
    
    This function returns a JSON summary containing:
    - The current database name
    - The total number of tables
    - A list of all table names with their row counts
    
    Returns:
        A dictionary containing the database summary information.
    """
    logger.info("Tool called: get_database_summary")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get current database name
        cursor.execute("SELECT DATABASE()")
        db_name_result = cursor.fetchone()
        db_name = db_name_result[0] if db_name_result and db_name_result[0] else "No database selected"
        
        # Get all tables
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        table_names = [table[0] for table in tables] if tables else []
        
        logger.debug(f"Found {len(table_names)} tables in database '{db_name}'")
        
        # Get row counts for each table
        tables_with_counts = []
        for table_name in table_names:
            table_name = validate_identifier(table_name, "table name")
            cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
            count_result = cursor.fetchone()
            row_count = count_result[0] if count_result else 0
            tables_with_counts.append({
                "table_name": table_name,
                "row_count": row_count
            })
        
        result = {
            "database_name": db_name,
            "total_tables": len(table_names),
            "tables": tables_with_counts
        }
        logger.debug(f"Database summary: {result}")
        return result
    except Error as e:
        logger.error(f"Error getting database summary: {e}")
        raise
    finally:
        cursor.close()
        conn.close()
        logger.debug("Connection returned to pool")


def main() -> None:
    """Run the MySQL MCP server."""
    try:
        validate_environment()
        initialize_connection_pool()
    except Exception as e:
        logger.error(f"Failed to initialize connection pool at startup: {e}")
        raise SystemExit(f"Error: Could not initialize connection pool - {e}") from e
    logger.info("Starting MySQL MCP Server")
    mcp.run()


if __name__ == "__main__":
    main()
