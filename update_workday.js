const { Pool } = require('pg');
const pool = new Pool({ user: 'postgres', password: 'A5u6iZ8m9Z5R', host: 'localhost', port: 5432, database: 'energy_db' });

const sql = `
  UPDATE energy_readings 
  SET 
    day_of_week = TO_CHAR(timestamp AT TIME ZONE 'Europe/Vienna', 'Day'),
    workday = CASE 
      WHEN TO_CHAR(timestamp AT TIME ZONE 'Europe/Vienna', 'DY') IN ('SAT', 'SUN') THEN false
      ELSE true
    END
  WHERE day_of_week IS NULL OR workday IS NULL
`;

pool.query(sql).then(r => {
  console.log('Updated rows:', r.rowCount);
  pool.end();
}).catch(e => console.error(e.message));
