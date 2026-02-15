FROM debian:bullseye-slim

RUN apt-get update && \
    apt-get install -y inetutils-telnetd openbsd-inetd passwd && \
    echo 'telnet stream tcp nowait root /usr/sbin/telnetd telnetd' >> /etc/inetd.conf && \
    # Create test users with default credentials (for adaptive vulnerability testing)
    useradd -m admin 2>/dev/null || true && \
    echo "admin:admin" | chpasswd && \
    echo "root:root" | chpasswd && \
    useradd -m user 2>/dev/null || true && \
    echo "user:user" | chpasswd

EXPOSE 23
CMD ["inetd", "-d"]
