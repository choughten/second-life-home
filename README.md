# Second Life Home

Turn an old iPad into a Home Assistant display instead of throwing it away.

A swipeable dashboard for calendars, cameras, lights, thermostats, and music.
The browser stays lightweight; a Python server talks to Home Assistant and keeps
credentials off the tablet. Originally built and tested on an **iPad 4 running
iOS 10.3.4**. No tablet app, jailbreak, cloud AI service, or modern JavaScript
framework is required.

## Try it in one command

After cloning or downloading this repository, open a terminal in its directory:

```sh
python3 server.py --demo
```

Open **http://localhost:8089**. This preview uses generated sample data and cannot
control devices. It listens only on localhost by default. It needs **Python 3.11
or newer** and no third-party Python packages on Linux/macOS.

## Connect your home

1. Have a working **Home Assistant** installation. Add your devices and calendars
   there first. Any supported calendar integration can be used; Google Calendar
   is not required.
2. In Home Assistant, open your user profile → **Security → Long-lived access
   tokens** and create a token. Treat it like a password. Use a dedicated HA user
   with only the access you need.
3. Run the setup wizard on the computer hosting the dashboard:

   ```sh
   python3 setup.py
   python3 server.py
   ```

   It asks for the HA URL/token, discovers entities, lets you choose what to show,
   and creates a private `config.json`. It also asks for a dashboard login.
4. On the iPad, visit **http://YOUR-SERVER-LAN-ADDRESS:8089**, then sign in with
   the dashboard username/password you chose. The server and tablet need network
   connectivity to each other; the tablet does not connect to HA directly.
5. In Safari, use **Share → Add to Home Screen** for the full-screen experience.
   Use landscape orientation. Swipe left/right or tap the bottom arrows/dots.

You must supply your own accounts, devices, and integrations. This project cannot
automatically create Google/Nest credentials or sign into music services for you.
The setup wizard can be rerun; back up `config.json` before replacing it.

### Already using Docker?

Run the setup wizard first using a reachable LAN URL for HA, then:

```sh
docker compose up -d --build
```

The app runs as a non-root user. The compose file defaults to UID/GID 1000 so it
can read a mode-600 `config.json` owned by the usual first Linux user. If your
user IDs differ, run `DASHBOARD_UID=$(id -u) DASHBOARD_GID=$(id -g) docker compose
up -d --build`. Keep dashboard port 8089 in the config when using this compose file.

`localhost` inside the container is **not your host computer**. Use the HA
machine's LAN IP/name, or `http://host.docker.internal:8123` for HA on the Docker
host. The compose file adds the Linux host-gateway mapping. Native Python startup
works on Linux and macOS; Windows may need `py` instead of `python3`, plus
`py -m pip install tzdata` for timezone data.

### No Home Assistant server yet? Optional Linux/Pi stack

Install Docker Engine with Compose, then:

```sh
docker compose -f compose.full.yaml up -d
```

This starts HA on port **8123** and Music Assistant on **8095**, with persistent
data under the ignored `data/` directory. Complete both web onboarding flows,
configure integrations/music/speakers, and add the **Music Assistant integration
in Home Assistant**. Then run `python3 setup.py` followed by the dashboard startup
above. This optional stack uses Linux host networking for speaker discovery;
use your existing HA install or native host setup on other platforms.

This is a basic container installation, not Home Assistant OS: it does not
include HA's app/add-on store, automatic backups, Zigbee USB passthrough, or
provider-specific camera bridges. See the official installation guides below.

## What's included

- Home screen with favorite accessories and an upcoming agenda.
- Six-week month calendar with day-grouped upcoming events.
- Camera snapshot grid and a full-screen live/refresh view.
- Generic thermostat temperature/mode/preset controls, tested originally with Nest.
- One music-first player with stable album art, track/artist, transport and volume.
- Radio/playlist picker, title filter, six-item pages, and room selection.
- Speaker grouping, shuffle/repeat, Music Assistant favorites, and current/next queue.
- ES5 JavaScript, XMLHttpRequest, and flexbox layouts for older Safari.
- Server-side entity/action validation; HA credentials never appear in page source.

Music requires **Music Assistant plus its HA integration**. Configure providers
(such as Spotify or Pandora) and player providers (such as AirPlay) in Music
Assistant itself. Provider subscriptions and restrictions still apply. Favorites
save to Music Assistant; they are not Pandora thumbs-up. The picker lists synced
library items, not a global Spotify search. Queue display shows current and next,
not a full queue editor. Grouping/synchronization depends on your players.

## Cameras: important compatibility detail

By default, snapshots come from HA's authenticated camera proxy. If your camera
integration does not provide a still image, use a configured snapshot URL instead.

Old Safari cannot display arbitrary RTSP/H.264/WebRTC feeds in an `<img>`. This
dashboard uses **MJPEG**, or continuously refreshed still images as a fallback.
Camera feeds have no audio. The fallback is not smooth video and needs working
snapshots. Set up an external camera bridge or go2rtc/FFmpeg if conversion is
required; those are not installed automatically by this repository.

Example camera entry in your private config:

```json
{
  "camera.front_door": {
    "snapshot_url": "http://camera-bridge.local/snapshot/front-door.jpg",
    "mjpeg_url": "http://camera-bridge.local/mjpeg/front-door",
    "username": "YOUR_BRIDGE_USER",
    "password": "YOUR_BRIDGE_PASSWORD"
  }
}
```

URLs are server-side only. Only configure camera services you trust. Basic auth
is optional; your HA token is sent only to the configured HA API, not to arbitrary
camera URLs. For go2rtc, see [docs/cameras.md](docs/cameras.md).

## Configuration

`config.example.json` documents the structure. Copy it to `config.json` if you
prefer manual setup. Replace the placeholder values before starting. In particular:

| Key | Purpose |
| --- | --- |
| `ha_url`, `ha_token` | Server-side connection to HA |
| `auth.username`, `auth.password` | Login for the dashboard, separate from HA |
| `include_entities` | Explicit device allowlist; wizard fills this |
| `exclude_entities` | Hide entities even if selected |
| `calendars` | Map calendar IDs to display names |
| `music_players` | Music Assistant media-player IDs only |
| `cameras`, `home_camera` | Allowed cameras and the home-screen camera |
| `favorite_buttons` | Optional media-player ID → HA favorite button ID overrides |
| `entity_replacements` | Old entity → replacement; hides old only when replacement exists |
| `camera_settings` | Switch entity IDs treated as camera settings rather than favorites |
| `weather_entity` | Optional weather entity |
| `timezone` | Server-side calendar timezone; clock follows the tablet's local timezone |

Empty optional sections show empty states. `include_entities: ["__none__"]`
disables device access. A manually empty/missing `include_entities` allows all
supported-domain devices except excluded entities, while cameras and music still
require their explicit lists; prefer the wizard's explicit selections.

Environment overrides: `HA_URL`, `HA_TOKEN`, `DASHBOARD_CONFIG`,
`DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`, `PORT`. Do not commit real config,
tokens, provider credentials, or screenshots with private calendar/camera data.

## Keep it running

Docker Compose restarts the dashboard automatically. For native Python on a
systemd Linux host:

```sh
sh scripts/install-service.sh
sudo loginctl enable-linger "$USER"
```

Stop with `systemctl --user disable --now second-life-home.service`, or
`docker compose down` if using Docker. No root privileges are needed for the
dashboard itself.

## Optional remote HTTPS demo

Prefer a private VPN for routine remote access on supported clients. For an old
iPad that cannot run a VPN app, the optional Cloudflare Quick Tunnel forwards
only the authenticated dashboard:

```sh
docker compose --profile remote up -d --build
docker compose logs tunnel
```

Open the generated `https://…trycloudflare.com` address and use your dashboard
login. A Quick Tunnel is for demonstrations/testing, has no availability guarantee,
and gets a new URL when it restarts. It is not enabled by default. It has no timed
expiry: close it with `docker compose stop tunnel`, and remove the profile from
future startup commands. No router port-forwarding is necessary.

HTTP Basic credentials are not encrypted by HTTP alone: use only on a trusted
LAN, or behind HTTPS. Do not forward port 8089 directly to the internet. The same
login protects calendar data, camera feeds, and device controls. A person with
that login can operate the devices selected in your configuration. Do not reuse
your HA, Google, Spotify, or router password.

## Hardware and limits

The tablets display the UI; a single always-on server can serve multiple tablets.
Pi 4/4GB is a reasonable starting point for HA, music, and the dashboard; Pi 5
offers more CPU headroom. Use an SSD, proper power supply, Ethernet, and cooling.
Video conversion and many concurrent cameras/tablets can require a stronger host.
An existing PC/mini PC/laptop also works if it stays awake and connected.

The original household deployment was physically tested on iOS 10.3.4. The
generalized package has automated API tests and browser checks, but cannot be
certified against every old tablet, camera integration, music provider, or speaker.
Pi/macOS/Windows hardware deployments of this public package are not all tested.

## Development and checks

```sh
python3 -m unittest discover -s tests -v
npm install --no-save --ignore-scripts acorn
node scripts/check-es5.cjs
```

CI checks Python 3.11–3.13 and ES5 syntax. Python tests use fake HA responses and
never contact or control real devices. Keep browser code ES5-compatible: no
`fetch`, arrow functions, optional chaining, modules, or modern-only layouts.
Do not commit `node_modules`, private config, or real household exports.

## Official setup references

- [Home Assistant installation](https://www.home-assistant.io/installation/)
- [HA long-lived access tokens](https://developers.home-assistant.io/docs/auth_api/#long-lived-access-token)
- [Music Assistant installation](https://www.music-assistant.io/installation/)
- [Music Assistant HA integration](https://www.home-assistant.io/integrations/music_assistant/)
- [go2rtc](https://github.com/AlexxIT/go2rtc)
- [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

Independent community project, not an Apple or Home Assistant product. It is not
a feature-for-feature clone of an Apple display. MIT licensed; see [LICENSE](LICENSE).
