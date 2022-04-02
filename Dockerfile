# syntax=docker/dockerfile:1

FROM python:3.8-slim-buster

# Do not run as root
RUN useradd -m -d /app app
USER app
WORKDIR /app

COPY --chown=app:app requirements.txt requirements.txt
RUN pip3 install --user app -r requirements.txt

COPY --chown=app:app . .

CMD [ "python3", "-m" , "tempo_trace_aggregation", "--config", "/app/config.yml"]