#!/usr/bin/env python3
"""Quick connectivity test with auto-detect local IP."""
import socket, time, sys, subprocess
sys.path.insert(0, r"d:\VCC")

output_lines = []
def log(msg):
    output_lines.append(msg)
    print(msg)

try:
    from scapy.contrib.automotive.someip import SOMEIP, SD as SOMEIP_SD, SDEntry_Service
except ImportError:
    log("ERROR: scapy not available")
    sys.exit(1)

# Auto-detect local IP on interface 11 (以太网 6)
TARGET_IP = "192.168.62.31"
LOCAL_IP = None

# Find the IP on 192.168.62.x subnet
for ip_candidate in ["192.168.62.5", "192.168.62.55", "192.168.62.59", "192.168.62.69"]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((ip_candidate, 0))
        s.close()
        LOCAL_IP = ip_candidate
        break
    except:
        pass

if not LOCAL_IP:
    log("ERROR: No 192.168.62.x IP found")
    sys.exit(1)

log("=" * 60)
log(f"  Quick Connectivity Diagnostic")
log(f"  Local IP: {LOCAL_IP}")
log(f"  Target IP: {TARGET_IP}")
log("=" * 60)

# 1. Ping
log(f"\n[1] Ping {TARGET_IP} ...")
try:
    r = subprocess.run(["ping", "-n", "2", "-w", "1000", TARGET_IP], capture_output=True, text=True, timeout=10)
    ping_ok = r.returncode == 0
    log(f"  {'OK' if ping_ok else 'FAIL'}")
    if not ping_ok:
        for line in r.stdout.splitlines():
            if line.strip():
                log(f"  {line.strip()}")
except Exception as e:
    log(f"  Error: {e}")
    ping_ok = False

# 2. ARP
log(f"\n[2] ARP table for {LOCAL_IP}:")
try:
    r = subprocess.run(["arp", "-a", "-N", LOCAL_IP], capture_output=True, text=True, timeout=5)
    found_arp = False
    for line in r.stdout.splitlines():
        if "192.168.62" in line:
            log(f"  {line.strip()}")
            found_arp = True
    if not found_arp:
        log(f"  (no ARP entries)")
except Exception as e:
    log(f"  Error: {e}")

# 3. SD listen + FindService
log(f"\n[3] SD listen on port 30490 (10s) + FindService ...")
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.settimeout(0.5)
s.bind(("", 30490))
try:
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                 socket.inet_aton("239.71.0.2") + socket.inet_aton(LOCAL_IP))
except: pass
try:
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(LOCAL_IP))
except: pass

sd = SOMEIP_SD(flags=0x80, entry_array=[
    SDEntry_Service(type=0x00, srv_id=0xFFFF, inst_id=0xFFFF, ttl=3)
])
find_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=1, msg_type=0x02) / sd

for i in range(3):
    s.sendto(bytes(find_pkt), ("239.71.0.2", 30490))
    s.sendto(bytes(find_pkt), (TARGET_IP, 30490))
    time.sleep(0.5)

count = 0
from_target = 0
deadline = time.time() + 10
while time.time() < deadline:
    try:
        data, addr = s.recvfrom(65535)
        count += 1
        try:
            pkt = SOMEIP(data)
            is_sd = pkt.srv_id == 0xFFFF and pkt.sub_id == 0x8100
            tag = "SD" if is_sd else f"Srv=0x{pkt.srv_id:04X}"
            log(f"  pkt#{count}: {addr} {tag} Type=0x{pkt.msg_type:02X}")
            if addr[0] == TARGET_IP:
                from_target += 1
        except:
            log(f"  pkt#{count}: {addr} raw {len(data)}B")
    except socket.timeout:
        pass
s.close()

log(f"\n  Total: {count} packets, from {TARGET_IP}: {from_target}")

# 4. UDP probe
log(f"\n[4] UDP probe {TARGET_IP}:30500 ...")
s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s2.settimeout(3.0)
s2.bind((LOCAL_IP, 31234))
req = SOMEIP(srv_id=0xA994, sub_id=0x0001, client_id=0x7001, session_id=1, msg_type=0x00) / b'\x00'
s2.sendto(bytes(req), (TARGET_IP, 30500))
try:
    data, addr = s2.recvfrom(65535)
    resp = SOMEIP(data)
    log(f"  Response! from {addr} Type=0x{resp.msg_type:02X} Payload={bytes(resp.payload).hex()}")
except socket.timeout:
    log(f"  Timeout")
s2.close()

# 5. Conclusion
log(f"\n{'=' * 60}")
if from_target > 0:
    log(f"  CONNECTIVITY OK! Received {from_target} packets from {TARGET_IP}")
else:
    log(f"  CONNECTIVITY FAIL! No response from {TARGET_IP}")
    log(f"\n  Please check:")
    log(f"  1. ICC device powered on and SOME/IP service running")
    log(f"  2. Switch port configured for VLAN 62")
    log(f"  3. Windows firewall not blocking ports 30490/30500")
log(f"{'=' * 60}")

with open(r"d:\VCC\tools\diag_result.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))
