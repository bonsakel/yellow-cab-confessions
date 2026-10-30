FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . ./

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "Home.py", "--server.address=0.0.0.0", "--server.port=8501"]
