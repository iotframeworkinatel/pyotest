FROM debian:bullseye-slim

RUN apt-get update && \
    apt-get install -y inetutils-telnetd && \
    apt-get install -y openbsd-inetd && \
    echo 'telnet stream tcp nowait root /usr/sbin/telnetd telnetd' >> /etc/inetd.conf

EXPOSE 23

CMD ["inetd", "-d"]
