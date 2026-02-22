import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

function ManagePage() {
  const [sites, setSites] = useState([]);
  const [meters, setMeters] = useState([]);
  const [loading, setLoading] = useState(true);
  
  const [file, setFile] = useState(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [sitesRes, metersRes] = await Promise.all([
        fetch('/api/sites'),
        fetch('/api/meters')
      ]);
      const sitesData = await sitesRes.json();
      const metersData = await metersRes.json();
      setSites(sitesData);
      setMeters(metersData);
    } catch (err) {
      console.error('Failed to fetch data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && droppedFile.name.endsWith('.csv')) {
      setFile(droppedFile);
      setError(null);
      setMessage(null);
    } else {
      setError('Please drop a CSV file');
    }
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile && !selectedFile.name.endsWith('.csv')) {
      setError('Please select a CSV file');
      return;
    }
    setFile(selectedFile);
    setError(null);
    setMessage(null);
  };

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a file first');
      return;
    }

    setUploadLoading(true);
    setError(null);
    setMessage(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/api/upload-csv', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (response.ok) {
        setMessage(data.message);
        setFile(null);
        document.querySelector('input[type="file"]').value = '';
        fetchData();
      } else {
        setError(data.error || data.detail || 'Upload failed');
        console.error('Upload failed with:', data);
      }
    } catch (err) {
      setError('Failed to upload file. Please check server logs.');
      console.error(err);
    } finally {
      setUploadLoading(false);
    }
  };

  const clearAllData = async () => {
    if (!confirm('Are you sure you want to delete ALL data (energy readings, sites, meters)? This cannot be undone.')) return;
    
    setLoading(true);
    try {
      const response = await fetch('/api/energy-readings', { method: 'DELETE' });
      const data = await response.json();
      if (response.ok) {
        setMessage('All data cleared successfully.');
        fetchData();
      } else {
        setError(data.message || 'Failed to clear data');
      }
    } catch (err) {
      console.error('Failed to clear data:', err);
      setError('Failed to clear data');
    } finally {
      setLoading(false);
    }
  };

  const [backupLoading, setBackupLoading] = useState(false);
  const [restoreLoading, setRestoreLoading] = useState(false);

  const handleBackup = async () => {
    setBackupLoading(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch('/api/backup');
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Backup failed');
      }
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `backup-${new Date().toISOString().split('T')[0]}.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();
      setMessage('Backup downloaded successfully');
    } catch (err) {
      console.error('Backup failed:', err);
      setError('Failed to create backup');
    } finally {
      setBackupLoading(false);
    }
  };

  const handleRestore = async () => {
    if (!file) {
      setError('Please select a backup file first');
      return;
    }

    if (!file.name.endsWith('.zip')) {
      setError('Please select a .zip backup file');
      return;
    }

    if (!confirm('This will restore data from the backup. Existing data may be overwritten. Continue?')) return;

    setRestoreLoading(true);
    setError(null);
    setMessage(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/api/restore', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (response.ok) {
        setMessage(data.message || 'Restore completed successfully');
        setFile(null);
        document.querySelector('input[type="file"]').value = '';
        fetchData();
      } else {
        setError(data.detail || data.message || 'Restore failed');
      }
    } catch (err) {
      console.error('Restore failed:', err);
      setError('Failed to restore backup');
    } finally {
      setRestoreLoading(false);
    }
  };

  const [editingSite, setEditingSite] = useState(null);
  const [editingMeter, setEditingMeter] = useState(null);

  const updateSite = async (siteId, updates) => {
    try {
      await fetch(`/api/sites/${siteId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      });
      setEditingSite(null);
      fetchData();
    } catch (err) {
      console.error('Failed to update site:', err);
    }
  };

  const updateMeter = async (meterId, updates) => {
    try {
      await fetch(`/api/meters/${meterId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      });
      setEditingMeter(null);
      fetchData();
    } catch (err) {
      console.error('Failed to update meter:', err);
    }
  };

  const metersBySite = {};
  meters.forEach(meter => {
    const siteId = meter.site_id || 'unassigned';
    if (!metersBySite[siteId]) metersBySite[siteId] = [];
    metersBySite[siteId].push(meter);
  });

  return (
    <div className="container">
      <main className="main">
        <div className="page-nav">
          <Link to="/" className="nav-left">Chat</Link>
          <Link to="/chart" className="nav-right">Dashboard</Link>
        </div>

        {/* Sites & Meters Card - TOP */}
        <div className="card">
          <h2>Sites & Meters</h2>
          <p className="hint">Sites and meters are auto-created from imported data</p>
          
          {loading ? (
            <div className="spinner"></div>
          ) : sites.length === 0 && meters.length === 0 ? (
            <p className="no-data">No sites or meters yet. Import CSV data to create them.</p>
          ) : (
            <div className="sites-meters-tree">
              {sites.map(site => (
                <div key={site.site_id} className="site-card">
                  {editingSite === site.site_id ? (
                    <div className="edit-form">
                      <input
                        type="text"
                        defaultValue={site.name || ''}
                        placeholder="Name"
                        id={`site-name-${site.site_id}`}
                      />
                      <input
                        type="text"
                        defaultValue={site.description || ''}
                        placeholder="Description"
                        id={`site-desc-${site.site_id}`}
                      />
                      <div className="edit-actions">
                        <button 
                          onClick={() => {
                            const name = document.getElementById(`site-name-${site.site_id}`).value;
                            const desc = document.getElementById(`site-desc-${site.site_id}`).value;
                            updateSite(site.site_id, { name, description: desc });
                          }}
                          className="save-button"
                        >Save</button>
                        <button onClick={() => setEditingSite(null)} className="cancel-button">Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <div className="site-header">
                      <div className="site-info">
                        <span className="site-name">{site.name || site.site_id}</span>
                        {site.description && <span className="site-desc">{site.description}</span>}
                      </div>
                      <button onClick={() => setEditingSite(site.site_id)} className="edit-button">Edit</button>
                    </div>
                  )}
                  <div className="meters-list">
                    {(metersBySite[site.site_id] || []).map(meter => (
                      <div key={meter.meter_id} className="meter-item">
                        {editingMeter === meter.meter_id ? (
                          <div className="edit-form">
                            <input
                              type="text"
                              defaultValue={meter.name || ''}
                              placeholder="Name"
                              id={`meter-name-${meter.meter_id}`}
                            />
                            <input
                              type="text"
                              defaultValue={meter.description || ''}
                              placeholder="Description"
                              id={`meter-desc-${meter.meter_id}`}
                            />
                            <button 
                              onClick={() => {
                                const name = document.getElementById(`meter-name-${meter.meter_id}`).value;
                                const desc = document.getElementById(`meter-desc-${meter.meter_id}`).value;
                                updateMeter(meter.meter_id, { name, description: desc });
                              }}
                              className="save-button"
                            >Save</button>
                            <button onClick={() => setEditingMeter(null)} className="cancel-button">Cancel</button>
                          </div>
                        ) : (
                          <div className="meter-row">
                            <div className="meter-info">
                              <span className="meter-name">{meter.name || meter.meter_id}</span>
                              {meter.description && <span className="meter-desc">{meter.description}</span>}
                              <span className="meter-meta">
                                {meter.datapoint_count ? `${meter.datapoint_count.toLocaleString()} datapoints` : ''}
                                {meter.last_data_point ? ` · Last: ${new Date(meter.last_data_point).toLocaleDateString()}` : ''}
                                {meter.last_updated ? ` · Updated: ${new Date(meter.last_updated).toLocaleDateString()}` : ''}
                              </span>
                            </div>
                            <button onClick={() => setEditingMeter(meter.meter_id)} className="edit-button-small">Edit</button>
                          </div>
                        )}
                      </div>
                    ))}
                    {(metersBySite[site.site_id] || []).length === 0 && (
                      <span className="no-meters">No meters</span>
                    )}
                  </div>
                </div>
              ))}
                    {metersBySite['unassigned'] && metersBySite['unassigned'].length > 0 && (
                      <div className="site-card unassigned">
                        <div className="site-header">
                          <div className="site-info">
                            <span className="site-name">Unassigned Meters</span>
                          </div>
                        </div>
                        <div className="meters-list">
                          {metersBySite['unassigned'].map(meter => (
                            <div key={meter.meter_id} className="meter-item">
                              <div className="meter-info">
                                <span className="meter-name">{meter.name || meter.meter_id}</span>
                                {meter.description && <span className="meter-desc">{meter.description}</span>}
                                <span className="meter-meta">
                                  {meter.datapoint_count ? `${meter.datapoint_count.toLocaleString()} datapoints` : ''}
                                  {meter.last_data_point ? ` · Last: ${new Date(meter.last_data_point).toLocaleDateString()}` : ''}
                                  {meter.last_updated ? ` · Updated: ${new Date(meter.last_updated).toLocaleDateString()}` : ''}
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
            </div>
          )}
        </div>

        {/* Upload Card */}
        <div className="card">
          <h2>CSV Import</h2>
          <p className="hint">Import energy data from CSV file</p>
          <p className="hint">Columns: timestamp, site_id, meter_id, export_energy/production_energy, import_energy/consumption_energy</p>
          
          <div 
            className={`file-drop-area ${isDragging ? 'dragging' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <input 
              type="file" 
              accept=".csv" 
              onChange={handleFileChange} 
              disabled={uploadLoading}
              id="file-input"
            />
            <label htmlFor="file-input" className="file-label">
              <div className="drop-message">
                {file ? (
                  <span className="file-name">{file.name}</span>
                ) : (
                  <span>Drag & Drop CSV file here<br/>or click to browse</span>
                )}
              </div>
            </label>
          </div>
          
          <button 
            onClick={handleUpload} 
            disabled={!file || uploadLoading}
            className="upload-button"
          >
            {uploadLoading ? 'Uploading...' : 'Upload & Import'}
          </button>
        </div>

        {/* Backup & Restore Card */}
        <div className="card">
          <h2>Backup & Restore</h2>
          <p className="hint">Download a backup or restore from a previous backup</p>
          
          <div className="backup-actions">
            <button 
              onClick={handleBackup} 
              disabled={backupLoading}
              className="upload-button"
            >
              {backupLoading ? 'Creating Backup...' : 'Download Backup'}
            </button>
          </div>

          <div className="restore-section">
            <p className="hint">Restore from backup file (.zip)</p>
            <div className="file-drop-area small">
              <input 
                type="file" 
                accept=".zip" 
                onChange={handleFileChange} 
                disabled={restoreLoading}
                id="restore-file-input"
              />
              <label htmlFor="restore-file-input" className="file-label">
                <div className="drop-message">
                  {file ? (
                    <span className="file-name">{file.name}</span>
                  ) : (
                    <span>Select backup file</span>
                  )}
                </div>
              </label>
            </div>
            
            <button 
              onClick={handleRestore} 
              disabled={!file || restoreLoading}
              className="restore-button"
            >
              {restoreLoading ? 'Restoring...' : 'Restore Backup'}
            </button>

            {message && <div className="success-message">{message}</div>}
            {error && <div className="error-message">{error}</div>}
          </div>
        </div>

        {/* Clear All Data - BOTTOM with warning */}
        <div className="card danger-card">
          <h2>Danger Zone</h2>
          <p className="warning-text">⚠️ This will permanently delete ALL energy readings, sites, and meters. This action cannot be undone.</p>
          <button onClick={clearAllData} className="danger-button">
            Clear All Data
          </button>
        </div>
      </main>
    </div>
  );
}

export default ManagePage;
