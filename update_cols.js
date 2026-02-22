const { Pool } = require('pg');
const pool = new Pool({ user: 'postgres', password: 'A5u6iZ8m9Z5R', host: 'localhost', port: 5432, database: 'energy_db' });

const holidays = [
  "'2023-01-01'", "'2023-01-06'", "'2023-04-07'", "'2023-04-10'", "'2023-05-01'", "'2023-05-18'", "'2023-05-29'", "'2023-08-15'", "'2023-10-26'", "'2023-11-01'", "'2023-12-08'", "'2023-12-25'", "'2023-12-26'",
  "'2024-01-01'", "'2024-01-06'", "'2024-03-29'", "'2024-04-01'", "'2024-05-01'", "'2024-05-09'", "'2024-05-20'", "'2024-08-15'", "'2024-10-26'", "'2024-11-01'", "'2024-12-08'", "'2024-12-25'", "'2024-12-26'",
  "'2025-01-01'", "'2025-01-06'", "'2025-04-18'", "'2025-04-21'", "'2025-05-01'", "'2025-05-09'", "'2025-05-29'", "'2025-08-15'", "'2025-10-26'", "'2025-11-01'", "'2025-12-08'", "'2025-12-25'", "'2025-12-26'"
];

const sql = `
  UPDATE energy_readings 
  SET 
    day_of_week = TO_CHAR(timestamp AT TIME ZONE 'Europe/Vienna', 'Day'),
    workday = CASE 
      WHEN TO_CHAR(timestamp AT TIME ZONE 'Europe/Vienna', 'DY') IN ('SAT', 'SUN') THEN false
      WHEN TO_CHAR(timestamp AT TIME ZONE 'Europe/Vienna', 'YYYY-MM-DD') = ANY(ARRAY[${holidays.join(',')}]) THEN false
      ELSE true
    END
  WHERE day_of_week IS NULL OR workday IS NULL
`;

pool.query(sql).then(r => {
  console.log('Updated rows:', r.rowCount);
  pool.end();
}).catch(e => console.error(e.message));
