#!/usr/bin/env python3
"""Test VLAN L2 capture using scapy with file output."""
import sys, os, time, threading
sys.path.insert(0, r"d:\VCC")
OUT = r"d:\VCC\tools\sniff_result.txt"

def main():
    lines = []
    def log(m):
        lines.append(str(m))
    
    try:
        log("importing scapy...")
        from scapy.all import conf
        conf.sniff_promisc = False
        from scapy.layers.l2 import Dot1Q
        from scapy.layers.inet import IP, UDP
        from scapy.sendrecv import sniff
        from scapy.arch import get_if_list, get_if_addr
        log("scapy imported")
    except Exception as e:
        log(f"import error: {e}")
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return
    
    iface = None
    for i in get_if_list():
        try:
            a = get_if_addr(i)
            if a.startswith("192.168.62."):
                iface = i
                log(f"iface={i} ip={a}")
                break
        except:
            pass
    
    if not iface:
        log("no 192.168.62.x iface")
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return
    
    log("sniffing 5s (no filter)...")
    captured = []
    
    def do_sniff():
        try:
            pkts = sniff(iface=iface, store=True, timeout=5)
            captured.extend(pkts)
        except Exception as e:
            log(f"sniff error: {e}")
    
    t = threading.Thread(target=do_sniff, daemon=True)
    t.start()
    t.join(timeout=10)
    
    if t.is_alive():
        log("sniff timed out (10s)")
    
    log(f"captured {len(captured)} packets")
    vlan_count = 0
    for p in captured[:30]:
        has_vlan = Dot1Q in p
        vid = p[Dot1Q].vlan if has_vlan else None
        src = p[IP].src if IP in p else "?"
        dst = p[IP].dst if IP in p else "?"
        if has_vlan:
            vlan_count += 1
        log(f"  VLAN={vid} {src}->{dst}")
    
    log(f"VLAN tagged: {vlan_count}/{min(len(captured),30)}")
    
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

if __name__ == "__main__":
    main()
