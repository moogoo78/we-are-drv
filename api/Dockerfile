FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY db ./db
COPY run.py ./

RUN mkdir -p /app/uploads /app/data

EXPOSE 4000
CMD ["gunicorn", "--preload", "-w", "2", "-b", "0.0.0.0:4000", "run:app"]
