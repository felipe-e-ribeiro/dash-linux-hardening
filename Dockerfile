# Stage 1: extract oscap binary + SSG content from AlmaLinux 9
FROM almalinux:9 AS oscap-extractor
RUN dnf install -y openscap-scanner scap-security-guide && \
    mkdir -p /oscap-bundle/lib /ssg-content && \
    cp /usr/bin/oscap /oscap-bundle/oscap-bin && \
    # Copy application-level libs only (skip system libs)
    ldd /usr/bin/oscap 2>/dev/null | \
      awk '/=>/ && !/libgcc_s|libc\.so|libm\.so|libdl\.so|libpthread|librt\.so|ld-linux/' | \
      awk '{print $3}' | grep -v '^$' | \
      xargs -I{} sh -c 'test -f "{}" && cp -L "{}" /oscap-bundle/lib/ || true' && \
    # Bundle SSG data stream content for RPM-family OSes (ds.xml = modern format)
    for f in almalinux8 almalinux9 rhel7 rhel8 rhel9 centos7 centos8 cs8 cs9 rl8 rl9 ol7 ol8 ol9; do \
        for ext in "-ds.xml" "-xccdf.xml" "-ds-1.2.xml"; do \
            src="/usr/share/xml/scap/ssg/content/ssg-${f}${ext}"; \
            test -f "$src" && cp "$src" /ssg-content/ || true; \
        done; \
    done

# Final stage: application image
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# oscap bundle for RPM-family targets
COPY --from=oscap-extractor /oscap-bundle/oscap-bin /app/bin/oscap-rpm-bin
COPY --from=oscap-extractor /oscap-bundle/lib/ /app/bin/rpm-lib/
RUN chmod +x /app/bin/oscap-rpm-bin

# Pre-built SSG XCCDF content (extracted from AlmaLinux 9 package)
COPY --from=oscap-extractor /ssg-content/ /app/ssg-content/

COPY run.py ./
COPY app ./app

# Persistent data: SSH keys, targets registry
VOLUME /data

EXPOSE 8765

CMD ["python", "run.py"]
