import os
import psycopg2
from psycopg2.extras import execute_values
import holidays

conn = psycopg2.connect(
    host="localhost",
    database="energy_db",
    user="postgres",
    password="A5u6iZ8m9Z5R"
)
conn.autocommit = True
cursor = conn.cursor()

# Get Austrian holidays for years in database - STATE 3 (Lower Austria / Niederösterreich)
years = [2023, 2024, 2025]
at_holidays = holidays.Austria(years=years, subdiv=3)

print("Lower Austria (State 3) holidays:")
for d, name in sorted(at_holidays.items()):
    print(f"  {d}: {name}")

# Update all rows with proper Austrian state 3 holidays
holiday_dates = [str(d) for d in at_holidays.keys()]
placeholders = ','.join([f"'{d}'" for d in holiday_dates])

sql = f"""
  UPDATE energy_readings 
  SET 
    workday = CASE 
      WHEN TO_CHAR(timestamp AT TIME ZONE 'Europe/Vienna', 'DY') IN ('SAT', 'SUN') THEN false
      WHEN TO_CHAR(timestamp AT TIME ZONE 'Europe/Vienna', 'YYYY-MM-DD') IN ({placeholders}) THEN false
      ELSE true
    END
"""

cursor.execute(sql)
print(f"\nUpdated {cursor.rowcount} rows with Austrian state 3 (Lower Austria) holidays")

cursor.close()
conn.close()
