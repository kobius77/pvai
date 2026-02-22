# Server Management

## Start FastAPI server
```bash
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
```

Wait ~4 seconds for startup, then verify with:
```bash
curl -s http://localhost:8000/api/sites
```

## Restart after code changes
```bash
pkill -f uvicorn
sleep 1
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/api/sites
```

## Check if running
```bash
pgrep -af uvicorn
```

## Check logs
```bash
cat /tmp/server.log
```

## Common issues
- If upload hangs: server needs restart after code changes
- If 500 error: check `cat /tmp/server.log`
- ERR_CONNECTION_REFUSED: server not running, restart with commands above
