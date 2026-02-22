import os
import io
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.utils
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

try:
    from tabulate import tabulate
except ImportError:
    tabulate = None


def generate_ascii_table(df):
    """Generate a dynamic ASCII table from a pandas DataFrame."""
    if df is None or df.empty:
        return ""
    
    # Handle single value: format as "Header: Value"
    if len(df) == 1 and len(df.columns) == 1:
        col_name = df.columns[0]
        value = df.iloc[0, 0]
        # Clean column name
        clean_name = col_name.replace('_', ' ').title()
        # Fix common unit casing
        clean_name = re.sub(r'kwh', 'kWh', clean_name, flags=re.IGNORECASE)
        clean_name = re.sub(r'kw\b', 'kW', clean_name, flags=re.IGNORECASE)
        clean_name = re.sub(r'wh\b', 'Wh', clean_name, flags=re.IGNORECASE)
        
        # Format value
        if pd.api.types.is_numeric_dtype(df[col_name]):
            if pd.notna(value):
                value = f"{value:,.2f}".replace('.', ',')
            else:
                value = "N/A"
        return f"{clean_name}: {value}"
    
    # Create a copy to avoid modifying the original
    df_copy = df.copy()
    
    # Clean column names
    new_columns = []
    for col in df_copy.columns:
        clean_col = col.replace('_', ' ').title()
        # Fix common unit casing
        clean_col = re.sub(r'kwh', 'kWh', clean_col, flags=re.IGNORECASE)
        clean_col = re.sub(r'kw\b', 'kW', clean_col, flags=re.IGNORECASE)
        clean_col = re.sub(r'wh\b', 'Wh', clean_col, flags=re.IGNORECASE)
        new_columns.append(clean_col)
    df_copy.columns = new_columns
    
    # Clean dates and format numbers
    for col in df_copy.columns:
        # Check if column contains timestamps
        if df_copy[col].dtype == 'object' or str(df_copy[col].dtype).startswith('datetime'):
            # Try to convert to datetime and format
            try:
                dates = pd.to_datetime(df_copy[col], errors='coerce')
                if dates.notna().any():
                    df_copy[col] = dates.dt.strftime('%Y-%m-%d')
            except:
                pass
        
        # Format numbers with German locale (comma decimals)
        if pd.api.types.is_numeric_dtype(df_copy[col]):
            df_copy[col] = df_copy[col].apply(
                lambda x: f"{x:,.2f}".replace('.', ',') if pd.notna(x) else "N/A"
            )
    
    # Generate markdown table
    if tabulate:
        try:
            return "\n" + tabulate(df_copy.head(20), headers='keys', tablefmt="pipe", showindex=False)
        except Exception as e:
            print(f"ASCII table generation failed: {e}")
            return ""
    else:
        # Fallback to pandas to_markdown
        try:
            return "\n" + df_copy.head(20).to_markdown(index=False, tablefmt="pipe")
        except Exception as e:
            print(f"Markdown table generation failed: {e}")
            return ""
from psycopg2 import pool

load_dotenv()

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "energy_db")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

conn_pool = None


def get_db_pool():
    global conn_pool
    if conn_pool is None:
        conn_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME
        )
    return conn_pool


def init_database():
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sites (
                site_id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255),
                description TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS meters (
                meter_id VARCHAR(255) PRIMARY KEY,
                site_id VARCHAR(255),
                name VARCHAR(255),
                description TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS energy_readings (
                timestamp TIMESTAMPTZ NOT NULL,
                site_id VARCHAR(255) NOT NULL,
                meter_id VARCHAR(255) NOT NULL,
                export_energy NUMERIC,
                export_power NUMERIC,
                import_energy NUMERIC,
                import_power NUMERIC,
                day_of_week VARCHAR(10),
                workday BOOLEAN DEFAULT true,
                PRIMARY KEY (timestamp, site_id, meter_id)
            )
        """)
        
        cursor.execute("""
            SELECT create_hypertable('energy_readings', 'timestamp', if_not_exists => TRUE)
        """)
        
        # Add site_id column to meters if it doesn't exist
        cursor.execute("""
            ALTER TABLE meters ADD COLUMN IF NOT EXISTS site_id VARCHAR(255)
        """)
        
        # Add last_updated column to meters if it doesn't exist
        cursor.execute("""
            ALTER TABLE meters ADD COLUMN IF NOT EXISTS last_updated TIMESTAMPTZ
        """)
        
        conn.commit()
        print("Database initialized: tables ready")
    finally:
        get_db_pool().putconn(conn)


vn = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global vn
    
    init_database()
    
    if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_key_here":
        try:
            from vanna.chromadb import ChromaDB_VectorStore
            from vanna.openai import OpenAI_Chat
            
            class VannaAI(ChromaDB_VectorStore, OpenAI_Chat):
                def __init__(self, config=None):
                    ChromaDB_VectorStore.__init__(self, config=config)
                    OpenAI_Chat.__init__(self, config=config)
            
            vn = VannaAI(config={
                "api_key": OPENAI_API_KEY,
                "model": "gpt-4o",
                "chroma_persist_directory": "./chroma_data"
            })
            
            vn.add_ddl("""
            CREATE TABLE sites (
                site_id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255),
                description TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """)
            
            vn.add_ddl("""
            CREATE TABLE meters (
                meter_id VARCHAR(255) PRIMARY KEY,
                site_id VARCHAR(255),
                name VARCHAR(255),
                description TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """)
            
            vn.add_ddl("""
            CREATE TABLE energy_readings (
                timestamp TIMESTAMPTZ NOT NULL,
                site_id VARCHAR(255) NOT NULL,
                meter_id VARCHAR(255) NOT NULL,
                export_energy NUMERIC,
                export_power NUMERIC,
                import_energy NUMERIC,
                import_power NUMERIC,
                day_of_week VARCHAR(10),
                workday BOOLEAN DEFAULT true,
                PRIMARY KEY (timestamp, site_id, meter_id)
            )
            """)
            
            vn.train(documentation="""
            Tables:
            - sites: Contains site information (site_id, name, description)
            - meters: Contains meter information (meter_id, site_id, name, description). Each meter belongs to a site via site_id.
            - energy_readings: Contains energy data (timestamp, site_id, meter_id, export_energy, export_power, import_energy, import_power, day_of_week, workday)
            
            Relationships:
            - meters.site_id references sites.site_id
            - energy_readings.site_id references sites.site_id
            - energy_readings.meter_id references meters.meter_id
            
            Units (IMPORTANT - ALWAYS use these):
            - export_energy and import_energy are in KILOWATT-HOURS (kWh)
            - export_power and import_power are in KILOWATTS (kW)
            - NEVER say "units of energy" - always say "kWh"
            - NEVER say "units of power" - always say "kW"
            
            Naming Convention for SQL Aliases:
            - Always include the unit in column aliases: use '_kWh' suffix for energy columns
            - Always include the unit in column aliases: use '_kW' suffix for power columns
            - Example: SELECT SUM(import_energy) AS import_energy_kWh, AVG(import_power) AS import_power_kW
            
            Visualization Rules:
            - NEVER use a pie chart for time-series data (dates, weeks, months, years).
            - If the data has a 'timestamp', 'date', 'week', 'month', or 'year' column, ALWAYS use a Line chart (px.line) or Bar chart (px.bar).
            - If the user asks for a trend ("Verlauf", "Entwicklung", "trend"), ALWAYS use a Line chart.
            - Only use Pie charts if the user explicitly asks for "share", "percentage", or comparing categories.
            - When writing Plotly Express code, ensure the 'y' axis is always the numerical value (kWh, kW) and the 'x' axis is the time or category.
            
            Vocabulary and Business Rules:
            - The 'workday' column is BOOLEAN: true = workday, false = non-workday (weekend or holiday).
            - If a user asks about 'Holidays', filter using: workday = FALSE AND EXTRACT(ISODOW FROM timestamp) <= 5.
            - If a user asks about 'weekends', filter using: workday = FALSE AND EXTRACT(ISODOW FROM timestamp) > 5.
            - Do not string match on day_of_week column.
            - export_energy = energy sent TO the grid (production/solar)
            - import_energy = energy drawn FROM the grid (consumption)
            
            Query Rules:
            - When a user asks for the 'maximum', 'highest', or 'peak' value of any column, 
              always add a WHERE clause ensuring the column IS NOT NULL, 
              and use 'ORDER BY column DESC NULLS LAST LIMIT 1' instead of grouping.
            
            Language Rules:
            - CRITICAL: You MUST generate the final natural language summary in the EXACT SAME LANGUAGE as the user's original question. 
            - If the user asks the question in German (e.g., "Wie hoch war der Verbrauch?"), the summary MUST be written in German.
            - If the user asks in English, reply in English.
            """)
            
            vn.train(
                question="how much energy did we import on workdays from 5pm to 7am on average per week", 
                sql="""
                    SELECT AVG(weekly_import_kWh) AS avg_weekly_night_import_kWh
                    FROM (
                        SELECT 
                            DATE_TRUNC('week', timestamp) AS week_start,
                            SUM(import_energy) AS weekly_import_kWh
                        FROM energy_readings
                        WHERE workday = TRUE
                          AND (EXTRACT(HOUR FROM timestamp) >= 17 OR EXTRACT(HOUR FROM timestamp) < 7)
                        GROUP BY DATE_TRUNC('week', timestamp)
                    ) AS weekly_totals;
                """
            )
            
            vn.train(
                question="what is the average import energy in kWh",
                sql="SELECT AVG(import_energy) AS avg_import_energy_kWh FROM energy_readings WHERE import_energy IS NOT NULL"
            )
            
            vn.train(
                question="show me the average consumption in kWh",
                sql="SELECT AVG(import_energy) AS avg_consumption_kWh FROM energy_readings WHERE import_energy IS NOT NULL"
            )
            
            print("Vanna initialized with OpenAI + ChromaDB")
            
            # OVERRIDE THE SUMMARY PROMPT TO FORCE GERMAN/LANGUAGE MATCHING
            vn.system_prompt_summary = """
Du bist ein hochqualifizierter Datenanalyst. 
Deine Aufgabe ist es, die Daten aus dem bereitgestellten Pandas DataFrame in einem kurzen, präzisen Satz zusammenzufassen, der die Frage des Benutzers direkt beantwortet.
KRITISCHE REGELN:

Du MUSST zwingend auf Deutsch antworten, wenn die Frage auf Deutsch gestellt wurde.

Verwende NIEMALS generische Begriffe wie "units of energy" oder "units of power".

Nutze IMMER die exakten Einheiten, die in den Spaltennamen stehen (z.B. 'kWh' für Energie, 'kW' für Leistung).

Sei präzise und direkt. Keine ausschweifenden Erklärungen.
"""
            
            print("Vanna summary prompt overridden for German")
        except Exception as e:
            print(f"Vanna init failed: {e}")
            vn = None
    else:
        print("Vanna not configured - set OPENAI_API_KEY in .env")
        vn = None
    
    yield
    
    if conn_pool:
        conn_pool.closeall()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BUILD_DIR = Path("src/client/build")

if BUILD_DIR.exists():
    app.mount("/static", StaticFiles(directory="src/client/build/static"), name="static")


    @app.get("/")
    async def root():
        with open("src/client/build/index.html") as f:
            return HTMLResponse(f.read())


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/debug-data")
async def debug_data(limit: int = 5):
    import math
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, site_id, meter_id, export_energy, import_energy FROM energy_readings WHERE export_energy IS NOT NULL OR import_energy IS NOT NULL LIMIT %s", [limit])
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "timestamp": str(r[0]),
                "site_id": r[1],
                "meter_id": r[2],
                "export_energy": float(r[3]) if r[3] and not math.isnan(r[3]) else None,
                "import_energy": float(r[4]) if r[4] and not math.isnan(r[4]) else None
            })
        return result
    except Exception as e:
        return {"error": str(e)}
    finally:
        get_db_pool().putconn(conn)


@app.get("/api/data")
async def get_data(year: str = "2024", month: str = "", day: str = ""):
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor()
        
        if day:
            # Raw 15-minute data when day is selected - group by timestamp to combine meters
            cursor.execute("""
                SELECT timestamp,
                       SUM(import_energy) as import_energy,
                       SUM(export_energy) as export_energy
                FROM energy_readings
                WHERE timestamp >= %s AND timestamp < %s
                GROUP BY timestamp
                ORDER BY timestamp
            """, [f"{year}-{month.zfill(2)}-{day.zfill(2)}T00:00:00+00:00", f"{year}-{month.zfill(2)}-{day.zfill(2)}T23:59:59+00:00"])
        elif month:
            # Get the last day of the month properly
            month_int = int(month)
            if month_int == 12:
                next_month = f"{int(year) + 1}-01-01T00:00:00+00:00"
            else:
                next_month = f"{year}-{month_int + 1:02d}-01T00:00:00+00:00"
            # Daily aggregation when month is selected
            cursor.execute("""
                SELECT date_trunc('day', timestamp) as day,
                       SUM(import_energy) as import_energy,
                       SUM(export_energy) as export_energy
                FROM energy_readings
                WHERE timestamp >= %s AND timestamp < %s
                GROUP BY date_trunc('day', timestamp)
                ORDER BY day
            """, [f"{year}-{month.zfill(2)}-01T00:00:00+00:00", next_month])
        else:
            # Monthly aggregation for full year
            cursor.execute("""
                SELECT date_trunc('month', timestamp) as month,
                       SUM(import_energy) as import_energy,
                       SUM(export_energy) as export_energy
                FROM energy_readings
                WHERE timestamp >= %s AND timestamp < %s
                GROUP BY date_trunc('month', timestamp)
                ORDER BY month
            """, [f"{year}-01-01T00:00:00+00:00", f"{int(year) + 1}-01-01T00:00:00+00:00"])
        
        rows = cursor.fetchall()
        print(f"DEBUG data: year={year}, month={month}, day={day}, rows={len(rows)}")
        result = []
        for row in rows:
            result.append({
                "timestamp": row[0].isoformat() if row[0] else None,
                "import_energy": float(row[1]) if row[1] else None,
                "export_energy": float(row[2]) if row[2] else None,
            })
        return result
    finally:
        get_db_pool().putconn(conn)


@app.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files allowed")
    
    contents = await file.read()
    df = pd.read_csv(io.BytesIO(contents))
    
    df.columns = df.columns.str.lower().str.strip()
    
    column_mapping = {
        'timestamp': 'timestamp',
        'time': 'timestamp',
        'site_id': 'site_id',
        'site': 'site_id',
        'meter_id': 'meter_id',
        'meter': 'meter_id',
        # Export (what you send to grid)
        'export_energy': 'export_energy',
        'production_energy': 'export_energy',
        'export_power': 'export_power',
        'production_power': 'export_power',
        # Import (what you draw from grid)
        'import_energy': 'import_energy',
        'consumption_energy': 'import_energy',
        'import_power': 'import_power',
        'consumption_power': 'import_power',
    }
    
    df = df.rename(columns=column_mapping)
    
    # Require site_id and meter_id - no defaults
    if 'site_id' not in df.columns:
        # Check for common variations or BOM
        found_site = next((c for c in df.columns if 'site' in c.lower()), None)
        if found_site:
            df = df.rename(columns={found_site: 'site_id'})
        else:
            print(f"DEBUG: Columns found: {list(df.columns)}")
            raise HTTPException(status_code=400, detail=f"CSV must have site_id column. Found: {list(df.columns)}")
            
    if 'meter_id' not in df.columns:
        found_meter = next((c for c in df.columns if 'meter' in c.lower()), None)
        if found_meter:
            df = df.rename(columns={found_meter: 'meter_id'})
        else:
            raise HTTPException(status_code=400, detail=f"CSV must have meter_id column. Found: {list(df.columns)}")
    
    if 'timestamp' not in df.columns:
        raise HTTPException(status_code=400, detail="CSV must have timestamp column")
    
    # robust timestamp parsing
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    if df['timestamp'].isna().any():
        print(f"WARNING: Dropping {df['timestamp'].isna().sum()} rows with invalid timestamps")
        df = df.dropna(subset=['timestamp'])
    
    if df.empty:
        raise HTTPException(status_code=400, detail="No valid timestamps found")

    df['site_id'] = df['site_id'].astype(str)
    
    # Auto-populate day_of_week and workday using Austrian holidays (Lower Austria / Niederösterreich)
    import holidays
    at_holidays = holidays.Austria(years=range(2020, 2030), subdiv=3)  # State 3 = Lower Austria
    
    if df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
    df['timestamp'] = df['timestamp'].dt.tz_convert('Europe/Vienna')
    df['day_of_week'] = df['timestamp'].dt.day_name()
    df['date_only'] = df['timestamp'].dt.date
    df['workday'] = df.apply(
        lambda r: r['date_only'] not in at_holidays and r['day_of_week'] not in ['Saturday', 'Sunday'],
        axis=1
    )
    df = df.drop(columns=['date_only'])
    
    # Ensure numeric columns are actually numeric
    numeric_cols = ['export_energy', 'export_power', 'import_energy', 'import_power']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df = df.dropna(subset=['timestamp', 'site_id', 'meter_id'])
    df = df.drop_duplicates(subset=['timestamp', 'site_id', 'meter_id'])
    
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor()
        
        values = []
        for _, row in df.iterrows():
            # Handle NaN values explicitly for DB (convert to None)
            export_energy = row.get('export_energy')
            if pd.isna(export_energy): export_energy = None
            
            export_power = row.get('export_power')
            if pd.isna(export_power): export_power = None
            
            import_energy = row.get('import_energy')
            if pd.isna(import_energy): import_energy = None
            
            import_power = row.get('import_power')
            if pd.isna(import_power): import_power = None

            values.append((
                row['timestamp'],
                str(row['site_id']),
                str(row['meter_id']),
                export_energy,
                export_power,
                import_energy,
                import_power,
                row.get('day_of_week'),
                row.get('workday')
            ))
        
        # Debug: log first row
        if values:
            print(f"DEBUG: First row to insert: {values[0]}")
        else:
            print("DEBUG: No rows to insert after filtering")
        
        from psycopg2.extras import execute_values
        query = """
            INSERT INTO energy_readings (timestamp, site_id, meter_id, export_energy, export_power, import_energy, import_power, day_of_week, workday)
            VALUES %s
            ON CONFLICT (timestamp, site_id, meter_id) DO UPDATE SET
                export_energy = COALESCE(EXCLUDED.export_energy, energy_readings.export_energy),
                export_power = COALESCE(EXCLUDED.export_power, energy_readings.export_power),
                import_energy = COALESCE(EXCLUDED.import_energy, energy_readings.import_energy),
                import_power = COALESCE(EXCLUDED.import_power, energy_readings.import_power),
                day_of_week = EXCLUDED.day_of_week,
                workday = EXCLUDED.workday
        """
        execute_values(cursor, query, values)
        
        # Auto-create sites and meters from imported data (batch)
        unique_sites = df[['site_id']].drop_duplicates().values.tolist()
        unique_meters = df[['meter_id', 'site_id']].drop_duplicates().values.tolist()
        
        if unique_sites:
            site_values = [[s[0], f"Site {s[0]}", "Auto-created from import"] for s in unique_sites]
            execute_values(cursor, """
                INSERT INTO sites (site_id, name, description) 
                VALUES %s
                ON CONFLICT (site_id) DO NOTHING
            """, site_values)
        
        if unique_meters:
            meter_values = [[m[0], m[1], f"Meter {m[0]}", "Auto-created from import"] for m in unique_meters]
            execute_values(cursor, """
                INSERT INTO meters (meter_id, site_id, name, description, last_updated)
                VALUES %s
                ON CONFLICT (meter_id) DO UPDATE SET site_id = EXCLUDED.site_id, last_updated = NOW()
            """, meter_values)
        
        conn.commit()
        
        return {"success": True, "message": f"Inserted/updated {len(values)} rows"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        get_db_pool().putconn(conn)


@app.post("/api/chat")
async def chat(request: dict):
    if vn is None:
        return {"error": "Vanna AI not configured. Set OPENAI_API_KEY in .env", "question": request.get("question", "")}
    
    question = request.get("question", "")
    debug_mode = request.get("debugMode", False)
    brief_mode = request.get("briefMode", False)
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    
    try:
        vn.connect_to_postgres(
            host=DB_HOST,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT
        )
        sql = vn.generate_sql(question=question)
        
        if not sql:
            return {"question": question, "sql": None, "summary": None, "chart": None, "result": [], "error": "Could not generate SQL"}
        
        df = vn.run_sql(sql=sql)
        
        # 1. Aggressive Rounding: Catch Postgres Decimals and convert to float
        if df is not None and not df.empty:
            for col in df.columns:
                try:
                    # Force conversion to float to handle psycopg2 Decimal objects, then round
                    df[col] = df[col].astype(float).round(2)
                except (ValueError, TypeError):
                    pass  # Safely skip timestamps and string columns
        
        if df is None or (hasattr(df, 'empty') and df.empty):
            return {
                "question": question,
                "sql": sql,
                "summary": None if debug_mode else "No data found for this query.",
                "chart": None,
                "result": [],
                "error": None
            }
        
        summary = None
        chart_json = None

        # Priority: debug_mode (even more) takes precedence over brief_mode (save tokens)
        if debug_mode:
            # Even more tokens saved: no summary, just query & result
            summary = None
        elif brief_mode:
            # Save tokens mode: return ASCII table
            summary = generate_ascii_table(df)
        else:
            # Normal mode: Generate conversational summary with OpenAI (temperature=0.7)
            from openai import OpenAI
            client = OpenAI()
            
            summary = "Keine Daten gefunden."
            
            if df is not None and not df.empty:
                # 1. Convert the first few rows of the dataframe to a clean string
                data_str = df.head(10).to_string(index=False)
                
                # 2. Build the strict but conversational prompt
                system_prompt = "Du bist ein freundlicher, professioneller Datenanalyst. Fasse die folgenden Datenpunkte basierend auf der Frage des Nutzers in 1-2 natürlichen, deutschen Sätzen zusammen. Nutze zwingend ein Komma als Dezimaltrennzeichen und die Einheiten aus den Spaltennamen (z.B. kWh)."
                
                # 3. Call OpenAI directly with Temperature = 0.7 for natural language
                try:
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        temperature=0.7,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Frage: {question}\n\nDaten:\n{data_str}"}
                        ]
                    )
                    llm_summary = response.choices[0].message.content
                except Exception as e:
                    print(f"Direct summary failed: {e}")
                    llm_summary = "Die Daten konnten nicht zusammengefasst werden."
                
                summary = llm_summary
            else:
                summary = "Keine Daten gefunden."

            chart_json = None

            if df is not None and not df.empty:
                # Rule 1: No charts for single events/numbers
                if len(df) == 1:
                    pass
                else:
                    # Rule 2: The LLM Bypass Interceptor
                    # Find columns that look like time/dates
                    time_keywords = ['time', 'date', 'week', 'month', 'year', 'day']
                    time_cols = [col for col in df.columns if any(w in col.lower() for w in time_keywords)]

                    # Find the metric columns - only numeric columns (not time columns, not site_id/meter_id)
                    other_cols = [col for col in df.columns if col not in time_cols and pd.api.types.is_numeric_dtype(df[col])]

                    if time_cols and other_cols:
                        try:
                            x_col = time_cols[0]
                            y_col = other_cols[0]
                            df = df.sort_values(by=x_col)
                            
                            dt_series = pd.to_datetime(df[x_col], errors='coerce', utc=True)
                            
                            if not dt_series.isna().all():
                                dt_series = dt_series.dt.tz_localize(None)
                                
                                if dt_series.dt.date.nunique() == 1:
                                    df[x_col] = dt_series.dt.strftime('%H:%M')
                                elif (dt_series.dt.hour == 0).all() and (dt_series.dt.minute == 0).all():
                                    df[x_col] = dt_series.dt.strftime('%d.%m.%Y')
                                else:
                                    df[x_col] = dt_series.dt.strftime('%d.%m. %H:%M')
                            else:
                                df[x_col] = df[x_col].astype(str)
                            
                            # 2. SMART CHART SELECTION
                            if len(df) > 25:
                                # Use a scatter plot (points) because interleaved nulls break px.line
                                # Pass ALL other columns to y so both import and export points are plotted if present
                                fig = px.scatter(df, x=x_col, y=other_cols)
                                
                                # Style: dark blue (#004973) points
                                fig.update_traces(marker=dict(size=5, color='#004973', opacity=0.8))
                            else:
                                fig = px.bar(df, x=x_col, y=other_cols)
                                # Style: dark blue (#004973) bars
                                fig.update_traces(marker_color='#004973')
                            
                            # Transparent background
                            fig.update_layout(
                                xaxis_type='category', 
                                margin=dict(l=20, r=20, t=30, b=50),
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)'
                            )
                            chart_json = json.loads(fig.to_json())
                        except Exception as e:
                            print(f"Deterministic chart failed: {e}")
                    else:
                        # Rule 3: Fallback to Vanna/LLM only if it's NOT a time-series
                        try:
                            plotly_code = vn.generate_plotly_code(question=question, sql=sql, df=df)
                            fig = vn.get_plotly_figure(plotly_code=plotly_code, df=df)
                            if fig:
                                chart_json = json.loads(fig.to_json())
                        except Exception as e:
                            print(f"Vanna chart generation failed: {e}")

        sanitized_data = []
        if df is not None and not df.empty:
            datetime_cols = df.select_dtypes(include=['datetime64', 'datetimetz']).columns
            for col in datetime_cols:
                df[col] = df[col].astype(str)

            df = df.replace({np.nan: None})
            sanitized_data = df.to_dict(orient="records")

        return {
            "question": question,
            "sql": sql,
            "summary": summary,
            "chart": chart_json,
            "result": sanitized_data,
            "error": None
        }
    except Exception as e:
        return {
            "question": question,
            "sql": None,
            "summary": None,
            "chart": None,
            "result": [],
            "error": str(e)
        }


# Sites API
@app.get("/api/sites")
async def get_sites():
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM sites ORDER BY site_id")
        return cursor.fetchall()
    finally:
        get_db_pool().putconn(conn)


@app.post("/api/sites")
async def create_site(request: dict):
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sites (site_id, name, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (site_id) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description
        """, [request.get('site_id'), request.get('name'), request.get('description')])
        conn.commit()
        return {"success": True}
    finally:
        get_db_pool().putconn(conn)


@app.put("/api/sites/{site_id}")
async def update_site(site_id: str, request: dict):
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE sites SET name = %s, description = %s WHERE site_id = %s
        """, [request.get('name'), request.get('description'), site_id])
        conn.commit()
        return {"success": True}
    finally:
        get_db_pool().putconn(conn)


@app.delete("/api/sites/{site_id}")
async def delete_site(site_id: str):
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sites WHERE site_id = %s", [site_id])
        conn.commit()
        return {"success": True}
    finally:
        get_db_pool().putconn(conn)


@app.delete("/api/energy-readings")
async def delete_all_energy_readings():
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM energy_readings")
        cursor.execute("DELETE FROM sites")
        cursor.execute("DELETE FROM meters")
        conn.commit()
        return {"success": True, "message": "All data deleted"}
    finally:
        get_db_pool().putconn(conn)


@app.post("/api/split-meters")
async def split_meters():
    """Fix: remove export data from meter 1, keep only in meter 2"""
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor()
        
        # Clear export_energy from meter 1 (keep only import)
        cursor.execute("""
            UPDATE energy_readings
            SET export_energy = NULL, export_power = NULL
            WHERE meter_id = '1'
        """)
        
        # Make sure meter 2 has all the export data (it should from the first split)
        
        conn.commit()
        
        # Get updated counts
        cursor.execute("""
            SELECT meter_id, COUNT(*) as cnt 
            FROM energy_readings 
            WHERE export_energy IS NOT NULL 
            GROUP BY meter_id
        """)
        export_counts = cursor.fetchall()
        
        cursor.execute("""
            SELECT meter_id, COUNT(*) as cnt 
            FROM energy_readings 
            WHERE import_energy IS NOT NULL 
            GROUP BY meter_id
        """)
        import_counts = cursor.fetchall()
        
        return {
            "success": True, 
            "message": "Fixed: removed export from meter 1",
            "export_by_meter": dict(export_counts),
            "import_by_meter": dict(import_counts)
        }
    finally:
        get_db_pool().putconn(conn)


# Meters API
@app.get("/api/meters")
async def get_meters():
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT m.*, 
                   (SELECT MAX(timestamp) FROM energy_readings WHERE meter_id = m.meter_id AND (import_energy IS NOT NULL OR export_energy IS NOT NULL)) as last_data_point,
                   (SELECT COUNT(*) FROM energy_readings WHERE meter_id = m.meter_id AND (import_energy IS NOT NULL OR export_energy IS NOT NULL)) as datapoint_count
            FROM meters m
            ORDER BY m.meter_id
        """)
        return cursor.fetchall()
    finally:
        get_db_pool().putconn(conn)


@app.post("/api/meters")
async def create_meter(request: dict):
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO meters (meter_id, name, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (meter_id) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description
        """, [request.get('meter_id'), request.get('name'), request.get('description')])
        conn.commit()
        return {"success": True}
    finally:
        get_db_pool().putconn(conn)


@app.put("/api/meters/{meter_id}")
async def update_meter(meter_id: str, request: dict):
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE meters SET name = %s, description = %s, last_updated = NOW() WHERE meter_id = %s
        """, [request.get('name'), request.get('description'), meter_id])
        conn.commit()
        return {"success": True}
    finally:
        get_db_pool().putconn(conn)


@app.delete("/api/meters/{meter_id}")
async def delete_meter(meter_id: str):
    conn = get_db_pool().getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM meters WHERE meter_id = %s", [meter_id])
        conn.commit()
        return {"success": True}
    finally:
        get_db_pool().putconn(conn)


APP_VERSION = "1.0"
SCHEMA_VERSION = 1


@app.get("/api/backup")
async def backup_database():
    import zipfile
    
    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "app_version": APP_VERSION,
            "schema_version": SCHEMA_VERSION,
            "tables": [],
            "includes_chromadb": False,
            "backup_timestamp": pd.Timestamp.now().isoformat()
        }
        
        conn = get_db_pool().getconn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = [row[0] for row in cursor.fetchall()]
            
            for table_name in tables:
                df = pd.read_sql(f'SELECT * FROM {table_name}', conn)
                
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False)
                csv_content = csv_buffer.getvalue()
                
                zf.writestr(f'{table_name}.csv', csv_content)
                manifest["tables"].append({
                    "name": table_name,
                    "rows": len(df),
                    "columns": list(df.columns)
                })
            
        finally:
            get_db_pool().putconn(conn)
        
        chromadb_path = 'chroma.sqlite3'
        if os.path.exists(chromadb_path):
            zf.write(chromadb_path, 'chroma.sqlite3')
            manifest["includes_chromadb"] = True
        
        zf.writestr('manifest.json', json.dumps(manifest, indent=2))
    
    buffer.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type='application/zip',
        headers={'Content-Disposition': 'attachment; filename=backup.zip'}
    )


@app.post("/api/restore")
async def restore_database(file: UploadFile = File(...)):
    import zipfile
    
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")
    
    contents = await file.read()
    buffer = io.BytesIO(contents)
    
    try:
        with zipfile.ZipFile(buffer, 'r') as zf:
            if 'manifest.json' not in zf.namelist():
                raise HTTPException(status_code=400, detail="Backup file is missing manifest.json")
            
            manifest_content = zf.read('manifest.json').decode('utf-8')
            manifest = json.loads(manifest_content)
            
            backup_schema_version = manifest.get('schema_version', 0)
            if backup_schema_version != SCHEMA_VERSION:
                raise HTTPException(
                    status_code=400,
                    detail=f"Schema version mismatch: backup has version {backup_schema_version}, current schema version is {SCHEMA_VERSION}. Please update the backup/restore logic before restoring."
                )
            
            conn = get_db_pool().getconn()
            try:
                cursor = conn.cursor()
                
                for name in zf.namelist():
                    if name.endswith('.csv'):
                        table_name = name[:-4]
                        csv_content = zf.read(name).decode('utf-8')
                        df = pd.read_csv(io.StringIO(csv_content))
                        
                        # Normalize columns (lowercase, strip whitespace)
                        df.columns = df.columns.str.lower().str.strip()
                        
                        cursor.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = %s", [table_name])
                        if not cursor.fetchone():
                            raise HTTPException(
                                status_code=400,
                                detail=f"Table '{table_name}' does not exist in the database. Schema drift detected."
                            )
                        
                        if table_name == 'energy_readings':
                            # Apply robust handling similar to CSV upload
                            
                            # 1. Aliases
                            column_mapping = {
                                'time': 'timestamp',
                                'site': 'site_id',
                                'meter': 'meter_id',
                                'production_energy': 'export_energy',
                                'production_power': 'export_power',
                                'consumption_energy': 'import_energy',
                                'consumption_power': 'import_power',
                            }
                            df = df.rename(columns=column_mapping)
                            
                            # 2. Ensure timestamp column exists
                            if 'timestamp' in df.columns:
                                # Parse timestamps
                                df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                                
                                # 3. Calculate derived columns if missing
                                if 'day_of_week' not in df.columns or 'workday' not in df.columns:
                                    try:
                                        import holidays
                                        # Use Austrian holidays as default, matching upload logic
                                        at_holidays = holidays.Austria(years=range(2020, 2030), subdiv=3)
                                        
                                        # Convert timezone
                                        if df['timestamp'].dt.tz is None:
                                            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
                                        df['timestamp'] = df['timestamp'].dt.tz_convert('Europe/Vienna')
                                        
                                        if 'day_of_week' not in df.columns:
                                            df['day_of_week'] = df['timestamp'].dt.day_name()
                                            
                                        if 'workday' not in df.columns:
                                            df['date_only'] = df['timestamp'].dt.date
                                            df['workday'] = df.apply(
                                                lambda r: r['date_only'] not in at_holidays and r['day_of_week'] not in ['Saturday', 'Sunday'],
                                                axis=1
                                            )
                                            df = df.drop(columns=['date_only'])
                                    except Exception as e:
                                        print(f"Warning: Failed to calculate derived columns: {e}")
                            
                            # 4. Ensure numeric columns are numeric
                            numeric_cols = ['export_energy', 'export_power', 'import_energy', 'import_power']
                            for col in numeric_cols:
                                if col in df.columns:
                                    df[col] = pd.to_numeric(df[col], errors='coerce')

                        for _, row in df.iterrows():
                            cols = ', '.join(df.columns)
                            placeholders = ', '.join(['%s'] * len(df.columns))
                            values = [None if pd.isna(v) else v for v in row.values]
                            
                            if table_name == 'energy_readings':
                                col_mapping = {
                                    'timestamp': None, 'site_id': None, 'meter_id': None,
                                    'export_energy': None, 'export_power': None,
                                    'import_energy': None, 'import_power': None,
                                    'day_of_week': None, 'workday': None
                                }
                                for col in df.columns:
                                    if col in col_mapping:
                                        col_mapping[col] = row[col]
                                
                                values = [
                                    col_mapping.get('timestamp'),
                                    col_mapping.get('site_id'),
                                    col_mapping.get('meter_id'),
                                    col_mapping.get('export_energy'),
                                    col_mapping.get('export_power'),
                                    col_mapping.get('import_energy'),
                                    col_mapping.get('import_power'),
                                    col_mapping.get('day_of_week'),
                                    col_mapping.get('workday'),
                                ]
                                values = [None if pd.isna(v) else v for v in values]
                                
                                upsert = """
                                    INSERT INTO energy_readings (timestamp, site_id, meter_id, export_energy, export_power, import_energy, import_power, day_of_week, workday)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                    ON CONFLICT (timestamp, site_id, meter_id) DO UPDATE SET
                                        export_energy = EXCLUDED.export_energy,
                                        export_power = EXCLUDED.export_power,
                                        import_energy = EXCLUDED.import_energy,
                                        import_power = EXCLUDED.import_power,
                                        day_of_week = EXCLUDED.day_of_week,
                                        workday = EXCLUDED.workday
                                """
                                cursor.execute(upsert, values)
                            else:
                                pk_cursor = conn.cursor()
                                pk_cursor.execute(f"""
                                    SELECT kcu.column_name 
                                    FROM information_schema.table_constraints tc
                                    JOIN information_schema.key_column_usage kcu 
                                        ON tc.constraint_name = kcu.constraint_name
                                    WHERE tc.table_name = %s AND tc.constraint_type = 'PRIMARY KEY'
                                """, [table_name])
                                pk_cols = [row[0] for row in pk_cursor.fetchall()]
                                
                                if pk_cols:
                                    set_clause = ', '.join([f"{col} = EXCLUDED.{col}" for col in df.columns if col not in pk_cols])
                                    if set_clause:
                                        placeholders = ', '.join(['%s'] * len(df.columns))
                                        pk_placeholders = ' AND '.join([f"{pk} = EXCLUDED.{pk}" for pk in pk_cols])
                                        upsert = f"""
                                            INSERT INTO {table_name} ({cols})
                                            VALUES ({placeholders})
                                            ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET {set_clause}
                                        """
                                        cursor.execute(upsert, values)
                                    else:
                                        insert = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"
                                        cursor.execute(insert, values)
                                else:
                                    insert = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"
                                    cursor.execute(insert, values)
                        
                        conn.commit()
                        
                        if manifest.get('includes_chromadb') and 'chroma.sqlite3' in zf.namelist():
                            chroma_content = zf.read('chroma.sqlite3')
                            with open('chroma.sqlite3', 'wb') as f:
                                f.write(chroma_content)
                        
            finally:
                get_db_pool().putconn(conn)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")
    
    return {"success": True, "message": "Database restored successfully"}


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    return HTMLResponse(content=open("src/client/build/index.html").read())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001)
