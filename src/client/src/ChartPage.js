import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { format } from 'date-fns';

function ChartPage() {
  const [chartData, setChartData] = useState([]);
  const [displayData, setDisplayData] = useState([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [year, setYear] = useState('2024');
  const [month, setMonth] = useState('');
  const [day, setDay] = useState('');

  useEffect(() => {
    fetchData();
  }, [year, month, day]);

  const fetchData = async () => {
    setDataLoading(true);
    try {
      let url = `/api/data?year=${year}`;
      if (month) url += `&month=${month}`;
      if (day) url += `&day=${day}`;
      const response = await fetch(url);
      const data = await response.json();
      const formatted = data.map(row => {
        const date = new Date(row.timestamp);
        return {
          ...row,
          timestamp: format(date, day ? 'HH:mm' : (month ? 'MMM dd' : 'MMM')),
          displayLabel: day ? format(new Date(date.getTime() + date.getTimezoneOffset() * 60000), 'HH:mm') : (month ? format(date, 'MMM dd') : format(date, 'MMM yyyy')),
          import_energy: row.import_energy != null ? parseFloat(Number(row.import_energy).toFixed(2)) : null,
          export_energy: row.export_energy != null ? parseFloat(Number(row.export_energy).toFixed(2)) : null,
        };
      });
      
      let displayDataFormatted = formatted;
      if (day && formatted.length >= 96) {
        const hourlyMap = {};
        formatted.forEach(d => {
          const hourLabel = d.displayLabel;
          const hour = hourLabel.split(':')[0];
          if (!hourlyMap[hour]) {
            hourlyMap[hour] = { import_energy: 0, export_energy: 0 };
          }
          hourlyMap[hour].import_energy += d.import_energy || 0;
          hourlyMap[hour].export_energy += d.export_energy || 0;
        });
        displayDataFormatted = Object.entries(hourlyMap).sort((a,b) => parseInt(a[0]) - parseInt(b[0])).map(([hour, vals]) => ({
          displayLabel: `${hour.padStart(2,'0')}:00`,
          import_energy: parseFloat((vals.import_energy).toFixed(2)),
          export_energy: parseFloat((vals.export_energy).toFixed(2)),
        }));
      }
      setChartData(formatted);
      setDisplayData(displayDataFormatted);
    } catch (err) {
      console.error('Failed to fetch data:', err);
    } finally {
      setDataLoading(false);
    }
  };

  return (
    <div className="container">
      <main className="main">
        <div className="page-nav">
          <Link to="/" className="nav-left">Chat</Link>
          <Link to="/manage" className="nav-right">Manage</Link>
        </div>
        <div className="chart-card">
          <h2>Energy Overview</h2>
          <div className="chart-controls">
            <div className="chart-nav-left">
              {(month || day) && (
                <button onClick={() => { setMonth(''); setDay(''); }} className="nav-button">← Back</button>
              )}
            </div>
            <div className="chart-nav-center">
              {day && (
                <button onClick={() => {
                  const d = parseInt(day);
                  const m = parseInt(month);
                  if (d > 1) setDay((d - 1).toString());
                  else if (m > 1) { setMonth((m - 1).toString()); setDay(new Date(parseInt(year), m - 1, 0).getDate().toString()); }
                }} className="nav-button">← Prev</button>
              )}
              {day && (
                <button onClick={() => {
                  const d = parseInt(day);
                  const m = parseInt(month);
                  const daysInMonth = new Date(parseInt(year), m, 0).getDate();
                  if (d < daysInMonth) setDay((d + 1).toString());
                  else if (m < 12) { setMonth((m + 1).toString()); setDay('1'); }
                }} className="nav-button">Next →</button>
              )}
              {month && !day && (
                <button onClick={() => {
                  const m = parseInt(month);
                  if (m > 1) setMonth((m - 1).toString());
                }} className="nav-button">← Prev</button>
              )}
              {month && !day && (
                <button onClick={() => {
                  const m = parseInt(month);
                  if (m < 12) setMonth((m + 1).toString());
                }} className="nav-button">Next →</button>
              )}
            </div>
            <div className="chart-nav-right">
              {month && (
                <select 
                  value={day} 
                  onChange={(e) => setDay(e.target.value)}
                  className="interval-select"
                >
                  <option value="">Full Month</option>
                  {Array.from({length: new Date(parseInt(year), parseInt(month), 0).getDate()}, (_, i) => i + 1).map(d => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
              )}
              <select 
                value={month} 
                onChange={(e) => { setMonth(e.target.value); setDay(''); }}
                className="interval-select"
              >
                <option value="">Full Year</option>
                <option value="1">January</option>
                <option value="2">February</option>
                <option value="3">March</option>
                <option value="4">April</option>
                <option value="5">May</option>
                <option value="6">June</option>
                <option value="7">July</option>
                <option value="8">August</option>
                <option value="9">September</option>
                <option value="10">October</option>
                <option value="11">November</option>
                <option value="12">December</option>
              </select>
              <select 
                value={year} 
                onChange={(e) => { setYear(e.target.value); setMonth(''); setDay(''); }}
                className="interval-select"
              >
                <option value="2023">2023</option>
                <option value="2024">2024</option>
                <option value="2025">2025</option>
              </select>
            </div>
          </div>
          
          {dataLoading ? (
            <div className="spinner"></div>
          ) : displayData.length === 0 ? (
            <p className="no-data">No data for {year}{month ? '-' + month : ''}{day ? '-' + day : ''}</p>
          ) : (
            <ReactECharts
              style={{ height: '500px', width: '100%' }}
              option={{
                tooltip: {
                  trigger: 'axis',
                  backgroundColor: 'rgba(0, 73, 115, 0.95)',
                  borderColor: 'transparent',
                  textStyle: { color: '#fff', fontSize: 12 },
                  formatter: (params) => {
                    const label = params[0]?.name || '';
                    let html = `<div style="border-bottom:1px solid rgba(255,255,255,0.5);padding-bottom:4px;margin-bottom:4px">${label}</div>`;
                    params.forEach(p => {
                      html += `<div style="color:#fff">${p.value?.toFixed(2) || 'N/A'} ${p.seriesName}</div>`;
                    });
                    return html;
                  }
                },
                grid: { left: 50, right: 10, top: 40, bottom: 40 },
                legend: {
                  data: ['Import', 'Export'],
                  bottom: 0,
                  itemGap: 20,
                  icon: 'rect'
                },
                xAxis: {
                  type: 'category',
                  data: displayData.map(d => d.displayLabel),
                  axisLine: { lineStyle: { color: '#9ca3af' } },
                  axisLabel: { fontSize: 12 }
                },
                yAxis: {
                  type: 'value',
                  axisLine: { lineStyle: { color: '#9ca3af' } },
                  axisLabel: { fontSize: 12 },
                  splitLine: { lineStyle: { color: '#eee', width: 0.5 } }
                },
                series: [
                  {
                    name: 'Import',
                    type: 'bar',
                    data: displayData.map(d => d.import_energy),
                    itemStyle: { color: '#7eb5d6' },
                    barGap: '2%'
                  },
                  {
                    name: 'Export',
                    type: 'bar',
                    data: displayData.map(d => d.export_energy),
                    itemStyle: { color: '#004973' },
                    barGap: '2%'
                  }
                ]
              }}
              onEvents={{
                'click': (params) => {
                  if (!day && month) {
                    const label = params.name;
                    const dayNum = label.match(/(\d+)/)?.[1];
                    if (dayNum) setDay(dayNum);
                  } else if (!month) {
                    const label = params.name;
                    const monthNum = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].indexOf(label.substring(0,3)) + 1;
                    if (monthNum) setMonth(monthNum.toString());
                  }
                }
              }}
            />
          )}
        </div>
      </main>
    </div>
  );
}

export default ChartPage;
