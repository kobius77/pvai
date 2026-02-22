import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './App.css';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

window.onerror = function(msg, url, line, col, error) {
  document.getElementById('root').innerHTML = '<pre style="color:red;padding:2rem;">Error: '+msg+'\nLine: '+line+'</pre>';
};
