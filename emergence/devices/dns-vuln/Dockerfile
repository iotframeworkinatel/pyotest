FROM alpine:3.18
RUN apk add --no-cache dnsmasq
COPY dnsmasq.conf /etc/dnsmasq.conf
COPY hosts.iot /etc/hosts.iot
EXPOSE 53/udp 53/tcp
CMD ["dnsmasq", "--no-daemon", "--log-queries"]
