FROM httpd:2.4

# Sensitive file: triggers http_sensitive_files test
RUN echo "DB_PASSWORD=admin123\nSECRET_KEY=supersecret" > /usr/local/apache2/htdocs/.env

# Admin page: triggers http_open_admin test
RUN mkdir -p /usr/local/apache2/htdocs/admin
RUN echo "<html><body><h1>Admin Panel</h1></body></html>" > /usr/local/apache2/htdocs/admin/index.html

# Directory traversal payload
RUN mkdir -p /usr/local/apache2/htdocs/etc
RUN echo "root:x:0:0:root:/root:/bin/bash" > /usr/local/apache2/htdocs/etc/passwd

# Homepage
RUN echo "Vulnerable HTTP server" > /usr/local/apache2/htdocs/index.html

# DAV config: enables PUT/DELETE methods, triggers http_dangerous_methods test
RUN mkdir -p /usr/local/apache2/var
COPY httpd-vuln.conf /usr/local/apache2/conf/extra/httpd-vuln.conf
RUN echo "Include conf/extra/httpd-vuln.conf" >> /usr/local/apache2/conf/httpd.conf

# --- HIDDEN VULNERABILITIES (only adaptive tests will discover these) ---

# Backup files — NOT in static sensitive_files list [".env", ".git/config", "config.php"]
RUN echo "DB_PASSWORD=leaked_backup\nOLD_SECRET=abc123" > /usr/local/apache2/htdocs/.env.bak
RUN echo "-- mysqldump: users table\n-- user: admin, pass: admin123" > /usr/local/apache2/htdocs/backup.sql
RUN echo "User-agent: *\nDisallow: /admin/\nDisallow: /api/debug" > /usr/local/apache2/htdocs/robots.txt

# Hidden API debug endpoint
RUN mkdir -p /usr/local/apache2/htdocs/api
RUN echo '{"debug": true, "version": "1.0", "db_host": "localhost"}' > /usr/local/apache2/htdocs/api/debug
