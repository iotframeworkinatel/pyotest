FROM eclipse-mosquitto

# Install mosquitto-clients for mosquitto_pub
USER root
RUN apk add --no-cache mosquitto-clients

COPY mosquitto.conf /mosquitto/config/mosquitto.conf

# Create init script inline to avoid Windows CRLF issues
RUN printf '#!/bin/sh\nmosquitto_pub -h localhost -t "device/config" -m '"'"'{"wifi_pass": "secret123", "ssid": "IoT_Network"}'"'"' -r\nmosquitto_pub -h localhost -t "device/firmware" -m '"'"'{"version": "1.0", "update_key": "abc123"}'"'"' -r\nmosquitto_pub -h localhost -t "admin/credentials" -m '"'"'{"user": "admin", "pass": "admin"}'"'"' -r\necho "[MQTT] Retained messages published"\n' > /init_messages.sh && chmod +x /init_messages.sh

# Start mosquitto, wait for it, then publish retained messages
CMD sh -c "/usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf & sleep 2 && /init_messages.sh && wait"
