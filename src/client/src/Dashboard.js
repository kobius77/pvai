import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import Plot from 'react-plotly.js';

function Dashboard() {
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatHistory, setChatHistory] = useState([]);
  const [expandedChat, setExpandedChat] = useState({});
  const [debugMode, setDebugMode] = useState(false);
  const [briefMode, setBriefMode] = useState(false);
  const [expandedSql, setExpandedSql] = useState({});
  const [expandedResult, setExpandedResult] = useState({});

  const exampleQuestions = [
    'Wie viel Strom haben wir pro Arbeitstag im Durchschnitt von Mai bis Oktober 2024 zwischen 17 und 7 Uhr importiert?',
    'Was war die maximale Leistung die wir exportiert haben?',
    'Zeige den Stromexport pro Monat im Verlauf.'
  ];
  const [currentExample, setCurrentExample] = useState(0);
  const [fadeKey, setFadeKey] = useState(0);

  useEffect(() => {
    if (chatHistory.length === 0) {
      const interval = setInterval(() => {
        setFadeKey(prev => prev + 1);
        setCurrentExample(prev => (prev + 1) % exampleQuestions.length);
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [chatHistory.length]);

  const handleExampleClick = (question) => {
    setChatInput(question);
    // Trigger form submission
    const form = document.querySelector('.chat-form');
    if (form) {
      const event = new Event('submit', { bubbles: true, cancelable: true });
      form.dispatchEvent(event);
    }
  };

  const handleChat = async (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const question = chatInput;
    setChatLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, debugMode, briefMode })
      });
      const data = await response.json();
      
      const newItem = { 
        question, 
        sql: data.sql,
        result: data.result,
        chart: data.chart,
        summary: data.summary,
        error: data.error 
      };

      // Shift existing expanded states down by 1 since new item is at 0
      const shiftKeys = (obj) => {
        const newObj = {};
        Object.keys(obj).forEach(key => {
          newObj[parseInt(key) + 1] = obj[key];
        });
        return newObj;
      };

      setExpandedChat(prev => ({ ...shiftKeys(prev), [0]: true }));
      // When even more is checked (debugMode=true), query and result should be expanded
      // Otherwise (save tokens or nothing): collapsed
      setExpandedSql(prev => ({ ...shiftKeys(prev), [0]: debugMode }));
      setExpandedResult(prev => ({ ...shiftKeys(prev), [0]: debugMode }));
      
      setChatHistory(prev => [newItem, ...prev]);
    } catch (err) {
      const newItem = { 
        question, 
        result: [], 
        sql: null, 
        chart: null,
        summary: null,
        error: err.message 
      };
      
      const shiftKeys = (obj) => {
        const newObj = {};
        Object.keys(obj).forEach(key => {
          newObj[parseInt(key) + 1] = obj[key];
        });
        return newObj;
      };
      
      setExpandedChat(prev => ({ ...shiftKeys(prev), [0]: true }));
      setChatHistory(prev => [newItem, ...prev]);
    } finally {
      setChatLoading(false);
      setChatInput('');
    }
  };

  const copyToInput = (text) => {
    setChatInput(text || '');
    setDebugMode(false);
  };

  return (
    <div className="container">
      <main className="main">
        <div className="page-nav">
          <Link to="/chart" className="nav-left">Dashboard</Link>
          <Link to="/manage" className="nav-right">Manage</Link>
        </div>
        <div className="chat-card">
          <form onSubmit={handleChat} className="chat-form">
            <textarea
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (chatInput.trim() && !chatLoading) {
                    handleChat(e);
                  }
                }
              }}
              placeholder="Ask a question about your energy data..."
              className="chat-input"
              disabled={chatLoading}
              rows={6}
            />
            <label className="debug-toggle save-tokens">
              <input type="checkbox" checked={briefMode} onChange={() => {
                // If both are active, clicking save tokens deactivates both
                // Otherwise just toggles save tokens
                if (briefMode && debugMode) {
                  setBriefMode(false);
                  setDebugMode(false);
                } else {
                  setBriefMode(!briefMode);
                }
              }} />
              save tokens
            </label>
            <label className="debug-toggle even-more">
              <input type="checkbox" checked={debugMode} onChange={() => {
                // If save tokens not active, activating even more activates both
                // Otherwise just toggles even more
                if (!briefMode) {
                  setBriefMode(true);
                  setDebugMode(true);
                } else {
                  setDebugMode(!debugMode);
                }
              }} />
              even more
            </label>
            <button type="submit" disabled={chatLoading || !chatInput.trim()} className="chat-button">
              {chatLoading ? <span className="spinner"></span> : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 19V5M5 12l7-7 7 7"/>
                </svg>
              )}
            </button>
          </form>

          {chatHistory.length === 0 && (
            <div className="example-questions">
              <span className="example-label">Example: </span>
              <span 
                key={fadeKey} 
                className="example-question"
                onClick={() => handleExampleClick(exampleQuestions[currentExample])}
              >
                {exampleQuestions[currentExample]}
              </span>
            </div>
          )}

          <div className="chat-history">
            {chatHistory.map((item, idx) => {
              const isExpanded = !!expandedChat[idx];
              return (
                <div key={idx} className={`chat-message ${isExpanded ? 'expanded' : 'collapsed'}`}>
                  <div 
                    className="chat-question-row"
                    onClick={() => setExpandedChat(prev => ({ ...prev, [idx]: !prev[idx] }))}
                  >
                    <span className="chat-toggle">{isExpanded ? '[-] ' : '[+] '}</span>
                    <span className="chat-question">Q: {item.question}</span>
                    <button 
                      className="copy-icon-btn" 
                      onClick={(e) => { e.stopPropagation(); copyToInput(item.question); }}
                      title="Copy to question box"
                    >
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                      </svg>
                    </button>
                  </div>
                  {isExpanded && (
                    <div className="chat-answer">
                      {item.error ? (
                        <p className="message error">{item.error}</p>
                      ) : (
                        <>
                          {item.summary && (
                            item.summary.includes('|') ? 
                              <pre className="chat-natural-answer">{item.summary}</pre> :
                              <div className="chat-natural-answer">{item.summary}</div>
                          )}
                          {item.chart && (
                            <div className="chat-chart">
                              <Plot
                                data={item.chart.data}
                                layout={item.chart.layout}
                                style={{ width: '100%', height: '100%' }}
                                useResizeHandler={true}
                              />
                            </div>
                          )}
                          {item.sql && (
                            <div className="chat-section">
                              <div 
                                className="chat-section-header"
                                onClick={() => setExpandedSql(prev => ({ ...prev, [idx]: !prev[idx] }))}
                                style={{ cursor: 'pointer' }}
                              >
                                {expandedSql[idx] !== false ? '[-] ' : '[+] '} Query
                              </div>
                              {expandedSql[idx] !== false && (
                                <pre className="chat-sql">{item.sql}</pre>
                              )}
                            </div>
                          )}
                          {item.result && item.result.length > 0 && (
                            <div className="chat-section">
                              <div 
                                className="chat-section-header"
                                onClick={() => setExpandedResult(prev => ({ ...prev, [idx]: !prev[idx] }))}
                                style={{ cursor: 'pointer' }}
                              >
                                {expandedResult[idx] !== false ? '[-] ' : '[+] '} Result
                              </div>
                              {expandedResult[idx] !== false && (
                                <pre className="chat-result">{JSON.stringify(item.result, null, 2)}</pre>
                              )}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}

export default Dashboard;
