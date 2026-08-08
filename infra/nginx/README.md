# nginx — the public edge for the V7 dashboard

`alphabot.conf` is a **mirror** of the live `/etc/nginx/sites-enabled/alphabot`. nginx does not read
it from here; this copy exists so the routing is reviewable, diffable and reconstructable — the same
reason `infra/systemd/` mirrors the units. Hand-reconstructing a config epoch is what made
2026-07-31 → 08-02 unrecoverable.

## Deploy

```sh
sudo cp infra/nginx/alphabot.conf /etc/nginx/sites-enabled/alphabot
sudo nginx -t            # ALWAYS test before reloading — a bad config takes the dashboard down
sudo systemctl reload nginx   # reload, never restart: graceful, drops no connections, keeps the tab
```

## The request path, and why port 8080 exists here

```
browser → https://dashboard.gazbot.dev/v7/…
        → Cloudflare → cloudflared (token-managed tunnel)
        → http://localhost:8080          ← ingress rule, configured REMOTELY
        → nginx :8080 server block       ← this file
        → http://127.0.0.1:8087/…        ← gazbot7-web
```

**The tunnel's ingress rule is not on this box.** cloudflared runs with `--token`, so its ingress is
held in the Cloudflare dashboard. You cannot fix a routing problem here by editing a local file —
which is why the `:8080` block exists at all.

## The 2026-08-08 outage this fixed

The tunnel pointed at `localhost:8080` — retired V5's port, dead since 2026-07-16. Nothing listened,
so **every** public request returned 502, including that morning's Friday report. The `:8080` server
block gives the tunnel a correct origin without needing Cloudflare access.

## Two traps, both live in this file

- **No `location / { proxy_pass 127.0.0.1:8080 }` in the `:8080` block.** The `:80` and `:443` blocks
  forward `/` to 8080; repeating that inside the server *listening* on 8080 is an infinite proxy
  loop. Bare `/` and `/v7shadow` are redirects here, never proxies back to self.
- **`absolute_redirect off`.** By default nginx builds the `Location` header from its own listening
  port, so `/` handed the browser `http://dashboard.gazbot.dev:8080/v7/` — leaking the internal port
  and dropping the visitor off HTTPS. Relative Locations resolve against what the client actually
  requested.

## Verify after any change

```sh
curl -sL -o /dev/null -w '%{http_code} %{url_effective}\n' https://dashboard.gazbot.dev/
#   expect: 200 https://dashboard.gazbot.dev/v7/   — and NO :8080 in the effective URL
curl -s -o /dev/null -w '%{http_code}\n' https://dashboard.gazbot.dev/v7/reports
```

⚠ The `location /` in the `:80`/`:443` blocks still points at 8080 and now resolves to this block
rather than to V5. That is intentional — it keeps the legacy root serving something real — but it
means **the V5 root is gone for good**; do not read a working `/` as evidence V5 is back.
