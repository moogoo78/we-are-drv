FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY db ./db
COPY run.py ./

RUN apk add --no-cache su-exec \
    && adduser -D -u 10001 app \
    && mkdir -p /app/uploads /app/data \
    && chown -R app:app /app/uploads /app/data
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 4000
# 啟動時先修正既有 volume 的擁有者，再降權為 app 執行
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "--preload", "-w", "2", "-b", "0.0.0.0:4000", "run:app"]
