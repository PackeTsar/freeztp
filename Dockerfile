FROM python:2.7-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN sed -i "s/deb.debian.org/archive.debian.org/g" /etc/apt/sources.list && sed -i "s/security.debian.org/archive.debian.org/g" /etc/apt/sources.list && sed -i "/buster-updates/d" /etc/apt/sources.list && apt-get update && apt-get install -y --no-install-recommends gcc libc-dev && rm -rf /var/lib/apt/lists/*
COPY ztp.py /app/ztp
COPY nstam_ipaddr.py /app/nstam_ipaddr.py
RUN ln -s /app/ztp /usr/local/bin/ztp
RUN ln -s /usr/local/bin/python /usr/bin/python
RUN python -m pip install --no-cache-dir --upgrade pip==20.3.4 && python -m pip install --no-cache-dir tftpy==0.6.0 flask==1.1.4 requests==2.24.0 isc-dhcp-leases==0.9.1 pysnmp==4.4.12
RUN sed -i "s/dyn_file_func(self.context.file_to_transfer)/dyn_file_func(self.context.file_to_transfer, self.context.host, self.context.port)/" /usr/local/lib/python2.7/site-packages/tftpy/TftpStates.py
RUN mkdir -p /app/ansible && printf "class AnsibleFilterError(Exception):\n    pass\n" > /app/ansible/errors.py && : > /app/ansible/__init__.py
CMD ["python", "/app/ztp", "run"]
