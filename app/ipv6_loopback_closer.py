"""Keeps ::1:8000 (IPv6 loopback) from silently hanging. Run as its own pm2
process (`python -m app.ipv6_loopback_closer`) — see deploy topology in the
outer CLAUDE.md for why this lives under app/ rather than scripts/ (only
app/ and admin_frontend/ get mirrored to the production directory).

bot-app's uvicorn listens on 0.0.0.0:8000 — IPv4 only. Some clients (xtunnel
observed doing this, may not be the only one) try localhost's IPv6 address
first before falling back to IPv4. With nothing listening on ::1:8000,
Windows doesn't send back an immediate refusal — it silently drops the SYN,
so the caller sits on its own connect timeout before falling back. Measured
by hand: every request through xtunnel was paying a rock-steady ~2s for
exactly this (confirmed via `curl -6 http://[::1]:8000/...` hanging for the
same ~2s, unrelated to xtunnel or any of our own network/VPN code), and it
dropped to instant the moment anything at all was listening on that address.

This isn't a real service — it doesn't need to speak HTTP or do anything
with what it accepts, just exist so the OS can complete the handshake
immediately instead of leaving the caller to time out.
"""
import socket
import threading


def main() -> None:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("::1", 8000))
    sock.listen(16)
    print("Listening on [::1]:8000 — nothing else, just closing the IPv6-loopback timeout hole.", flush=True)
    while True:
        conn, _ = sock.accept()
        threading.Thread(target=conn.close, daemon=True).start()


if __name__ == "__main__":
    main()
