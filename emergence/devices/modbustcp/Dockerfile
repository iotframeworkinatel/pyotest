FROM python:3.10-slim

RUN pip install pymodbus==2.5.3

COPY server.py /server.py

EXPOSE 502
CMD ["python", "/server.py"]
