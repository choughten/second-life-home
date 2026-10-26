# Camera bridge recipes

Configure these only when normal HA camera snapshots do not work, or when you
want an MJPEG live view. The dashboard accepts configured HTTP(S) still/MJPEG
URLs; it does not accept an RTSP URL directly and does not install a camera bridge.

For an existing go2rtc server, the following private config pattern converts a
configured stream called `front-door` into MJPEG. Query strings must URL-encode
the `#` in the FFmpeg source:

```json
{
  "camera.front_door": {
    "snapshot_url": "http://go2rtc.local:1984/api/frame.jpeg?src=ffmpeg%3Afront-door%23video%3Dmjpeg",
    "mjpeg_url": "http://go2rtc.local:1984/api/stream.mjpeg?src=ffmpeg%3Afront-door%23video%3Dmjpeg"
  }
}
```

Your go2rtc server needs a configured `front-door` source and FFmpeg. Native
camera protocols, authentication, permissions, device access, acceleration, and
container architecture vary; follow the upstream guide for your cameras/hardware.
Software conversion can be CPU-heavy, especially with several viewers. There is
no guarantee all proprietary Wyze or other camera models will work.

If your bridge exposes only JPEG snapshots, omit `mjpeg_url`: the dashboard will
make a refreshed-image stream at approximately one image per second, subject to
camera response time. This is not full-frame-rate video. Keep bridges on your LAN
and never publish their management API or credentials to GitHub.

[go2rtc upstream documentation](https://github.com/AlexxIT/go2rtc)
