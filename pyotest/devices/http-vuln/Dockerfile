FROM httpd:2.4
RUN echo "Vulnerable HTTP server" > /usr/local/apache2/htdocs/index.html
RUN mkdir -p /usr/local/apache2/htdocs/etc
RUN echo "root:x:0:0:root:/root:/bin/bash" > /usr/local/apache2/htdocs/etc/passwd

# O CMD padrão do httpd já é correto:
# CMD ["httpd-foreground"]
