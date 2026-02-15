FROM python:3.10-slim
RUN pip install aiocoap
COPY server.py /server.py
EXPOSE 5683/udp
CMD ["python", "/server.py"]
