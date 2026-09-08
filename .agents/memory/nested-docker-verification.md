---
name: Nested Docker verification
description: Replit-hosted Docker daemon constraints that can distort Compose runtime checks.
---

On this Replit host, Docker bridge forwarding between containers can time out, and
exec-based health checks can fail with a `setns` error when the container's PID 1
runs as a non-root user. Do not commit host networking or root application
execution as a workaround for these daemon constraints.

**Why:** Both failures reproduced independently of application connectivity:
host processes could reach published services, while bridge peers could not, and
the same image accepted `docker exec` only while PID 1 remained root.

**How to apply:** Keep the normal bridge topology and non-root image defaults.
When runtime verification must occur on this host, use an uncommitted Compose
override and label the limitation in the evidence. Re-run the standard topology
on an ordinary Docker host when that environment is available.