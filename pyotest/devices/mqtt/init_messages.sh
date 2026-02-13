#!/bin/sh
# Publish retained messages with sensitive data (only adaptive tests will discover these)
mosquitto_pub -h localhost -t "device/config" -m '{"wifi_pass": "secret123", "ssid": "IoT_Network"}' -r
mosquitto_pub -h localhost -t "device/firmware" -m '{"version": "1.0", "update_key": "abc123"}' -r
mosquitto_pub -h localhost -t "admin/credentials" -m '{"user": "admin", "pass": "admin"}' -r
echo "[MQTT] Retained messages published on device/config, device/firmware, admin/credentials"
