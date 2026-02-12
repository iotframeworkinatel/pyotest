FROM debian:bullseye-slim

RUN apt-get update && \
    apt-get install -y inetutils-telnetd openbsd-inetd && \
    echo 'telnet stream tcp nowait root /usr/sbin/telnetd telnetd' >> /etc/inetd.conf && \
    useradd -m root -p "" || true

EXPOSE 23
CMD ["inetd", "-d"]
