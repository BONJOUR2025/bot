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
same ~2s, unrelated to xtunnel or any of our own network/VPN code).

First version of this just accepted and immediately closed the connection —
fast, but wrong: Windows/Python's abrupt close (data arrives in the
just-accepted socket's receive buffer before our thread gets to close() it)
sends a TCP RST, and clients that treat "connection refused" as retry-worthy
treat a mid-handshake RST as a hard failure instead — traded a 2s hang for
outright 502s (xtunnel's own log literally labelled it "reset"). This
version transparently proxies to the real IPv4 listener instead, so ::1:8000
just... works, the same as 127.0.0.1:8000 — no special-casing needed on
either end, and no behavior for a client to misinterpret.
"""
import asyncio

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
LISTEN_PORT = 8000


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while chunk := await reader.read(65536):
            writer.write(chunk)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        writer.close()


async def _handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    try:
        backend_reader, backend_writer = await asyncio.open_connection(BACKEND_HOST, BACKEND_PORT)
    except OSError:
        client_writer.close()
        return
    await asyncio.gather(
        _pipe(client_reader, backend_writer),
        _pipe(backend_reader, client_writer),
    )


async def main() -> None:
    server = await asyncio.start_server(_handle, "::1", LISTEN_PORT)
    print(f"Proxying [::1]:{LISTEN_PORT} -> {BACKEND_HOST}:{BACKEND_PORT}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
