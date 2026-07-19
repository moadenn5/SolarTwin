start "MQTT Broker" cmd /k "mosquitto -c mosquitto.conf -v"
timeout /t 2 >nul
start "Simulator" cmd /k "venv\Scripts\activate && python simulator\publisher.py"
timeout /t 2 >nul
start "Gateway" cmd /k "venv\Scripts\activate && uvicorn gateway.api:app --port 8000"