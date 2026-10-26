import json, os, subprocess, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, urlencode, parse_qs
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time, threading, base64
import argparse, hmac
from pathlib import Path
ARGS=argparse.ArgumentParser(description="Second Life Home dashboard")
ARGS.add_argument("--demo",action="store_true",help="Synthetic data, no Home Assistant required")
ARGS.add_argument("--config",default=os.environ.get("DASHBOARD_CONFIG","config.json"))
OPTIONS=ARGS.parse_args() if __name__=="__main__" else argparse.Namespace(demo=False,config=os.environ.get("DASHBOARD_CONFIG","config.json"))
CONFIG=json.loads(Path(OPTIONS.config).read_text()) if Path(OPTIONS.config).exists() else {}
DEMO=OPTIONS.demo or os.environ.get("DASHBOARD_DEMO")=="1"
if DEMO:CONFIG={}
BASE=os.environ.get("HA_URL",CONFIG.get("ha_url","http://localhost:8123")).rstrip("/")
TOKEN=os.environ.get("HA_TOKEN") or CONFIG.get("ha_token","")
ZONE=ZoneInfo(CONFIG.get("timezone","UTC"))
CALENDARS=CONFIG.get("calendars",{})
MUSIC_PLAYERS=tuple(CONFIG.get("music_players",[]))
CAMERAS=CONFIG.get("cameras",{})
AUTH_USER=os.environ.get("DASHBOARD_USERNAME") or CONFIG.get("auth",{}).get("username","")
AUTH_PASS=os.environ.get("DASHBOARD_PASSWORD") or CONFIG.get("auth",{}).get("password","")
INCLUDE=set(CONFIG.get("include_entities",[]))
EXCLUDE=set(CONFIG.get("exclude_entities",[]))
MUSIC_PLAYERS=tuple(x for x in MUSIC_PLAYERS if x not in EXCLUDE and (not INCLUDE or x in INCLUDE))
CAMERAS={k:v for k,v in CAMERAS.items() if k not in EXCLUDE and (not INCLUDE or k in INCLUDE)}
if not DEMO and (not TOKEN or not AUTH_USER or not AUTH_PASS):
    raise SystemExit("Run python3 setup.py first, or set HA_TOKEN, DASHBOARD_USERNAME and DASHBOARD_PASSWORD. Use --demo to preview.")
def ha(path,data=None):
    req=urllib.request.Request(BASE+"/api/"+path,data=None if data is None else json.dumps(data).encode(),headers={"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=12) as r:return json.load(r)
calendar_cache={}
calendar_lock=threading.Lock()
def agenda():
    with calendar_lock:
        if calendar_cache and time.time()-calendar_cache["cached"]<300:return calendar_cache["data"]
        now=datetime.now(ZONE)
        query=urlencode({"start":now.isoformat(),"end":(now+timedelta(days=14)).isoformat()})
        events=[]; failed=[]
        for entity,name in CALENDARS.items():
            try:
                for e in ha("calendars/"+entity+"?"+query):
                    start=e.get("start",{}); end=e.get("end",{})
                    all_day="date" in start
                    raw=start.get("dateTime",start.get("date"))
                    if not raw:continue
                    dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
                    if dt.tzinfo is None:dt=dt.replace(tzinfo=ZONE)
                    dt=dt.astimezone(ZONE)
                    events.append({"title":e.get("summary","Untitled event"),"calendar":name,"day":dt.strftime("%a, %b %d").replace(" 0"," "),"time":"All day" if all_day else dt.strftime("%I:%M %p").lstrip("0"),"sort":dt.timestamp()})
            except Exception:failed.append(name)
        events.sort(key=lambda e:e["sort"])
        data={"events":events[:40],"failed":failed,"updated":now.strftime("%I:%M %p").lstrip("0")}
        if not failed:calendar_cache.update({"cached":time.time(),"data":data})
        return data

DOMAINS=("light","switch","camera","media_player","climate","fan","cover","scene","sensor","binary_sensor")
def devices():
    states=ha("states")
    result=[]
    # Hide duplicate Apple TV entities once their Music Assistant counterparts exist.
    replacements=CONFIG.get("entity_replacements",{})
    ids={x["entity_id"] for x in states}
    for state in states:
        entity=state["entity_id"];domain=entity.split(".")[0];a=state.get("attributes",{})
        if entity in replacements and replacements[entity] in ids:continue
        if entity in EXCLUDE or (INCLUDE and entity not in INCLUDE):continue
        if domain=="media_player" and entity not in MUSIC_PLAYERS:continue
        if domain=="camera" and entity not in CAMERAS:continue
        if domain not in DOMAINS:continue
        if entity.startswith("sensor.backup_") or entity.startswith("sensor.sun_"):continue
        # Prefer named Wyze camera entities over old generic camera duplicates.

        safe={k:a[k] for k in ("brightness","supported_features","device_class","unit_of_measurement","current_temperature","temperature","target_temp_high","target_temp_low","current_humidity","hvac_action","hvac_modes","min_temp","max_temp","preset_mode","preset_modes","media_title","media_artist","media_album_name","app_name","source","volume_level","is_volume_muted","group_members","shuffle","repeat","media_content_id","media_duration","media_position","media_position_updated_at") if k in a}
        result.append({"id":entity,"domain":domain,"name":a.get("friendly_name",entity),"state":state["state"],"attributes":safe})
    return result
image_cache={}
image_lock=threading.Lock()
def camera_request(entity,live=False):
    if entity not in CAMERAS:raise ValueError("Unknown camera")
    settings=CAMERAS[entity]
    url=settings.get("mjpeg_url" if live else "snapshot_url")
    headers={}
    if not url:
        url=BASE+"/api/camera_proxy/"+entity
        headers["Authorization"]="Bearer "+TOKEN
    elif settings.get("username"):
        headers["Authorization"]="Basic "+base64.b64encode((settings["username"]+":"+settings.get("password","")).encode()).decode()
    if urlparse(url).scheme not in ("http","https"):raise ValueError("Camera URL must use HTTP(S)")
    return urllib.request.Request(url,headers=headers)
def snapshot(entity,fresh=False):
    if entity not in CAMERAS:raise ValueError("Unknown camera")
    with image_lock:
        cached=image_cache.get(entity)
        if not fresh and cached and time.time()-cached[0]<25:return cached[1:]
    with urllib.request.urlopen(camera_request(entity),timeout=40) as response:
        kind=response.headers.get("Content-Type","").split(";")[0]
        body=response.read(8*1024*1024)
    if kind not in ("image/jpeg","image/png"):raise ValueError("Camera snapshot unavailable")
    with image_lock:image_cache[entity]=(time.time(),body,kind)
    return body,kind

month_cache={}
def month_events(value):
    first=datetime.strptime(value,"%Y-%m").replace(tzinfo=ZONE)
    start=first-timedelta(days=(first.weekday()+1)%7)
    end=start+timedelta(days=42)
    if value in month_cache and time.time()-month_cache[value][0]<300:return month_cache[value][1]
    result=[];failed=[]
    query=urlencode({"start":start.isoformat(),"end":end.isoformat()})
    for entity,name in CALENDARS.items():
        try:
            for event in ha("calendars/"+entity+"?"+query):
                a=event.get("start",{});b=event.get("end",{})
                raw=a.get("dateTime",a.get("date"));finish=b.get("dateTime",b.get("date"))
                if not raw:continue
                dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
                if dt.tzinfo is None:dt=dt.replace(tzinfo=ZONE)
                dt=dt.astimezone(ZONE)
                until=datetime.fromisoformat((finish or raw).replace("Z","+00:00"))
                if until.tzinfo is None:until=until.replace(tzinfo=ZONE)
                until=until.astimezone(ZONE)
                result.append({"title":event.get("summary","Untitled event"),"calendar":name,"date":dt.strftime("%Y-%m-%d"),"end":until.strftime("%Y-%m-%d"),"end_ts":until.timestamp(),"sort":dt.timestamp(),"all_day":"date" in a,"time":"All day" if "date" in a else dt.strftime("%I:%M %p").lstrip("0")})
        except Exception:failed.append(name)
    result.sort(key=lambda e:e["sort"])
    data={"events":result,"failed":failed,"month":value}
    if not failed:month_cache[value]=(time.time(),data)
    return data

music_cache={}
art_cache={}
login_failures={}
login_lock=threading.Lock()
music_lock=threading.Lock()
def music_items(category):
    if category not in ("radio","playlists"):raise ValueError("Unknown music category")
    if not MUSIC_PLAYERS:return []
    with music_lock:
        cached=music_cache.get(category)
        if cached and time.time()-cached[0]<120:return cached[1]
        result=ha("services/media_player/browse_media?return_response",{"entity_id":MUSIC_PLAYERS[0],"media_content_type":"music_assistant","media_content_id":category})
        tree=result["service_response"][MUSIC_PLAYERS[0]]
        items=[{"id":x["media_content_id"],"title":x["title"],"type":x["media_content_type"]} for x in tree.get("children",[]) if x.get("can_play")]
        music_cache[category]=(time.time(),items)
        return items

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def authorized(self):
        if DEMO and not AUTH_PASS:return True
        expected="Basic "+base64.b64encode((AUTH_USER+":"+AUTH_PASS).encode()).decode()
        address=self.client_address[0]
        now=time.time()
        with login_lock:
            recent=[t for t in login_failures.get(address,[]) if now-t<60]
            if len(recent)>=10:return self.reply(429,{"error":"Too many attempts; wait one minute"}) or False
            if hmac.compare_digest(self.headers.get("Authorization",""),expected):
                login_failures.pop(address,None)
                return True
            login_failures[address]=recent+[now]
        self.send_response(401);self.send_header("WWW-Authenticate",'Basic realm="Second Life Home"');self.send_header("Content-Length","0");self.send_header("Cache-Control","no-store");self.end_headers();return False
    def demo_get(self):
        from demo import response
        status,data,kind=response(self.path)
        return self.reply(status,data,kind)

    def reply(self,status,data,kind="application/json"):
        body=data if isinstance(data,bytes) else data.encode() if isinstance(data,str) else json.dumps(data).encode()
        self.send_response(status);self.send_header("Content-Type",kind);self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if not self.authorized():return
        try:
            if self.path=="/health":return self.reply(200,{"ok":True})
            if DEMO and self.path.startswith("/api/"):return self.demo_get()
            if self.path=="/":
                public={"title":CONFIG.get("title","Second Life Home"),"location":CONFIG.get("location",""),"timezone":CONFIG.get("timezone","UTC"),"home_camera":CONFIG.get("home_camera",""),"camera_settings":CONFIG.get("camera_settings",[])}
                page=Path(__file__).with_name("dashboard.html").read_text()
                page=page.replace("/*PUBLIC_CONFIG*/", "window.DASHBOARD_CONFIG="+json.dumps(public).replace("<","\\u003c")+";")
                return self.reply(200,page,"text/html; charset=utf-8")
            if self.path.startswith("/api/month?"):
                value=parse_qs(urlparse(self.path).query).get("month",[""])[0]
                return self.reply(200,month_events(value))
            if self.path.startswith("/api/live/"):
                entity=urlparse(self.path).path.rsplit("/",1)[1]
                if entity not in CAMERAS:return self.reply(404,{"error":"Unknown camera"})
                if CAMERAS[entity].get("mjpeg_url"):
                    with urllib.request.urlopen(camera_request(entity,True),timeout=40) as upstream:
                        kind=upstream.headers.get("Content-Type","")
                        if not kind.startswith("multipart/"):return self.reply(503,{"error":"Configure an MJPEG stream, not H.264 or RTSP"})
                        self.send_response(200);self.send_header("Content-Type",kind);self.send_header("Cache-Control","no-store");self.send_header("Connection","close");self.end_headers()
                        try:
                            while True:
                                chunk=upstream.read1(32768)
                                if not chunk:break
                                self.wfile.write(chunk);self.wfile.flush()
                        except (BrokenPipeError,ConnectionResetError):pass
                    return
                self.send_response(200);self.send_header("Content-Type","multipart/x-mixed-replace; boundary=frame");self.send_header("Cache-Control","no-store");self.send_header("Connection","close");self.end_headers()
                try:
                    while True:
                        body,kind=snapshot(entity,True)
                        self.wfile.write(b"--frame\r\nContent-Type: "+kind.encode()+b"\r\nContent-Length: "+str(len(body)).encode()+b"\r\n\r\n"+body+b"\r\n");self.wfile.flush();time.sleep(1)
                except (BrokenPipeError,ConnectionResetError):pass
                return
            if self.path.startswith("/api/art/"):
                entity=urlparse(self.path).path.rsplit("/",1)[1]
                if entity not in MUSIC_PLAYERS:return self.reply(404,{"error":"Unknown speaker"})
                state=ha("states/"+entity);attrs=state.get("attributes",{})
                key=(entity,attrs.get("media_title"),attrs.get("media_album_name"))
                cached=art_cache.get(entity)
                if cached and cached[0]==key and time.time()-cached[1]<120:return self.reply(200,cached[2],cached[3])
                req=urllib.request.Request(BASE+"/api/media_player_proxy/"+entity,headers={"Authorization":"Bearer "+TOKEN})
                with urllib.request.urlopen(req,timeout=12) as r:
                    kind=r.headers.get("Content-Type","").split(";")[0];body=r.read(4*1024*1024)
                if kind not in ("image/jpeg","image/png","image/webp"):return self.reply(404,{"error":"No artwork"})
                art_cache[entity]=(key,time.time(),body,kind)
                return self.reply(200,body,kind)
            if self.path.startswith("/api/music-queue?"):
                entity=parse_qs(urlparse(self.path).query).get("entity",[""])[0]
                if entity not in MUSIC_PLAYERS:return self.reply(400,{"error":"Unknown speaker"})
                result=ha("services/music_assistant/get_queue?return_response",{"entity_id":entity})["service_response"][entity]
                items=[]
                for label,key in (("Now","current_item"),("Next","next_item")):
                    item=result.get(key)
                    if item:items.append({"label":label,"title":item.get("stream_title") or item.get("name",""),"duration":item.get("duration")})
                return self.reply(200,{"items":items,"count":result.get("items",0),"shuffle":result.get("shuffle_enabled"),"repeat":result.get("repeat_mode")})
            if self.path.startswith("/api/music?"):
                category=parse_qs(urlparse(self.path).query).get("category",["radio"])[0]
                return self.reply(200,{"items":music_items(category)})
            if self.path=="/api/devices":return self.reply(200,{"devices":devices()})
            if self.path.startswith("/api/camera/"):
                entity=self.path.split("?",1)[0].rsplit("/",1)[1]
                body,kind=snapshot(entity)
                return self.reply(200,body,kind)
            if self.path=="/api/agenda":return self.reply(200,agenda())
            if self.path=="/api/status":
                weather=ha("states/"+CONFIG["weather_entity"]) if CONFIG.get("weather_entity") else {"state":"Not configured","attributes":{}}
                a=weather.get("attributes",{})
                return self.reply(200,{"weather":weather["state"],"temperature":a.get("temperature"),"unit":a.get("temperature_unit","")})
            self.reply(404,{"error":"Not found"})
        except Exception:self.reply(503,{"error":"Home Assistant is temporarily unavailable"})
    def do_POST(self):
        if not self.authorized():return
        if DEMO:return self.reply(409,{"error":"Demo mode: no devices are controlled"})
        origin=self.headers.get("Origin")
        host=self.headers.get("Host","")
        valid_origins={"http://"+host}
        if self.client_address[0]=="127.0.0.1":valid_origins.add("https://"+host)
        if origin and origin not in valid_origins:return self.reply(403,{"error":"Invalid origin"})
        if self.headers.get("X-Dashboard")!="ipad":return self.reply(403,{"error":"Invalid request"})
        if self.path=="/api/control":
            try:
                size=int(self.headers.get("Content-Length","0"))
                if size<1 or size>1024:return self.reply(400,{"error":"Invalid command"})
                command=json.loads(self.rfile.read(size))
                entity=command.get("entity","");action=command.get("action","")
                device=next((d for d in devices() if d["id"]==entity),None)
                if not device:return self.reply(404,{"error":"Unknown device"})
                domain=device["domain"]
                if domain=="media_player" and action=="play_selection":
                    if entity not in MUSIC_PLAYERS:return self.reply(403,{"error":"Unsupported music player"})
                    if device["state"] in ("unavailable","unknown"):return self.reply(409,{"error":"Speaker unavailable"})
                    category=command.get("category")
                    if category not in ("radio","playlists"):return self.reply(400,{"error":"Invalid music category"})
                    item=next((x for x in music_items(category) if x["id"]==command.get("item")),None)
                    if not item:return self.reply(400,{"error":"Selection no longer available. Reopen the music picker."})
                    members=[x for x in device["attributes"].get("group_members",[]) if x in MUSIC_PLAYERS and x!=entity]
                    ha("services/media_player/play_media",{"entity_id":entity,"media_content_id":item["id"],"media_content_type":item["type"]})
                    if members:ha("services/media_player/join",{"entity_id":entity,"group_members":members})
                    return self.reply(200,{"ok":True})
                if domain=="media_player" and action in ("set_speakers","favorite","shuffle_set","repeat_set"):
                    if entity not in MUSIC_PLAYERS:return self.reply(403,{"error":"Unsupported speaker"})
                    if action=="set_speakers":
                        members=command.get("members")
                        if not isinstance(members,list) or len(members)>len(MUSIC_PLAYERS) or entity not in members or any(x not in MUSIC_PLAYERS for x in members):return self.reply(400,{"error":"Invalid speaker group"})
                        old=device["attributes"].get("group_members",[])
                        for member in old:
                            if member in MUSIC_PLAYERS and member!=entity and member not in members:ha("services/media_player/unjoin",{"entity_id":member})
                        others=[x for x in members if x!=entity]
                        if others:ha("services/media_player/join",{"entity_id":entity,"group_members":others})
                        elif old:ha("services/media_player/unjoin",{"entity_id":entity})
                    elif action=="favorite":
                        ha("services/button/press",{"entity_id":CONFIG.get("favorite_buttons",{}).get(entity,"button."+entity.split(".",1)[1]+"_favorite_current_song")})
                    elif action=="shuffle_set":
                        if not isinstance(command.get("shuffle"),bool):return self.reply(400,{"error":"Invalid shuffle"})
                        ha("services/media_player/shuffle_set",{"entity_id":entity,"shuffle":command["shuffle"]})
                    else:
                        if command.get("repeat") not in ("off","all","one"):return self.reply(400,{"error":"Invalid repeat"})
                        ha("services/media_player/repeat_set",{"entity_id":entity,"repeat":command["repeat"]})
                    return self.reply(200,{"ok":True})
                if domain=="climate":
                    if device["state"] in ("unavailable","unknown"):return self.reply(409,{"error":"Thermostat unavailable"})
                    state=ha("states/"+entity);attrs=state.get("attributes",{})
                    payload={"entity_id":entity}
                    if action=="set_temperature":
                        value=command.get("temperature")
                        if isinstance(value,bool) or not isinstance(value,(int,float)) or not attrs.get("min_temp",50)<=value<=attrs.get("max_temp",90):return self.reply(400,{"error":"Invalid temperature"})
                        if state["state"] in ("off","heat_cool") or attrs.get("preset_mode")=="eco":return self.reply(409,{"error":"Select Heat or Cool and turn Eco off before setting a target"})
                        payload["temperature"]=value
                    elif action=="set_hvac_mode":
                        value=command.get("hvac_mode")
                        if value not in attrs.get("hvac_modes",[]):return self.reply(400,{"error":"Unsupported thermostat mode"})
                        payload["hvac_mode"]=value
                    elif action=="set_preset_mode":
                        value=command.get("preset_mode")
                        if value not in attrs.get("preset_modes",[]):return self.reply(400,{"error":"Unsupported preset"})
                        payload["preset_mode"]=value
                    else:return self.reply(403,{"error":"Unsupported thermostat action"})
                    ha("services/climate/"+action,payload)
                    return self.reply(200,{"ok":True})
                allowed={"light":("turn_on","turn_off"),"switch":("turn_on","turn_off"),"fan":("turn_on","turn_off"),"media_player":("media_play","media_pause","media_next_track","media_previous_track","volume_set")}
                if action not in allowed.get(domain,()):return self.reply(403,{"error":"Action not supported"})
                if device["state"] in ("unavailable","unknown"):return self.reply(409,{"error":"Device unavailable"})
                payload={"entity_id":entity}
                if domain=="media_player" and action=="volume_set":
                    value=command.get("volume_level")
                    if isinstance(value,bool) or not isinstance(value,(int,float)) or not 0<=value<=1:return self.reply(400,{"error":"Invalid volume"})
                    payload["volume_level"]=value
                ha("services/"+domain+"/"+action,payload)
                return self.reply(200,{"ok":True})
            except Exception:return self.reply(503,{"error":"Device command failed"})
        return self.reply(404,{"error":"Not found"})

def main():
    host=CONFIG.get("listen_host","127.0.0.1" if DEMO else "0.0.0.0")
    port=int(os.environ.get("PORT",CONFIG.get("port",8089)))
    if not DEMO and not (AUTH_USER and AUTH_PASS):raise SystemExit("Authentication is required")
    print("Second Life Home listening on %s:%s%s"%(host,port," (synthetic demo; controls disabled)" if DEMO else ""),flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()

if __name__=="__main__":main()
