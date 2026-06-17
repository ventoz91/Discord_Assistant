FROM python:3.13-slim

WORKDIR /app

# System deps: gcc for any compiled wheels, openssh-client for server management SSH calls
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data/ is a volume — create the mount point so permissions are sane
RUN mkdir -p /app/data

CMD ["python", "main.py"]
