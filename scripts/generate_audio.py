"""
ASMR Audio Generator - Synthesizes realistic tool sounds
"""
import os
import wave
import struct
import math
import random

SAMPLE_RATE = 44100
OUTPUT_DIR = "audio"

def write_wav(filename, samples):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with wave.open(filename, 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        data = bytearray()
        for s in samples:
            val = int(max(-32767, min(32767, s * 32767)))
            data.extend(struct.pack('<h', val))
        wav.writeframes(data)

def gen_wind(d=6): 
    n = int(SAMPLE_RATE * d)
    s, p = [0.0]*n, 0.0
    for i in range(n):
        w = random.uniform(-1,1); p = p*0.95 + w*0.05
        g = (math.sin(2*math.pi*0.3*i/SAMPLE_RATE)+1)*0.5
        s[i] = p*(0.15+0.2*g)
    return s

def gen_ratchet(d=6):
    n = int(SAMPLE_RATE * d); s = [0.0]*n
    for t in [0.8,2.2,3.6]:
        si = int(SAMPLE_RATE*t)
        for c in range(8):
            ci = si + int(c*0.08*SAMPLE_RATE); cl = int(0.015*SAMPLE_RATE)
            for j in range(cl):
                if ci+j<n:
                    d2 = (1-j/cl)**3
                    s[ci+j] += random.uniform(-1,1)*d2*0.4 + math.sin(2*math.pi*2800*j/SAMPLE_RATE)*d2*0.3
    # Drop
    di = int(SAMPLE_RATE*4.8)
    for b in [0,0.12,0.22,0.30]:
        bi = di+int(b*SAMPLE_RATE); bl = int(0.08*SAMPLE_RATE); v = (1-b*2.5)*0.4
        for j in range(bl):
            if bi+j<n:
                dec = math.exp(-j/(0.015*SAMPLE_RATE))
                s[bi+j] += (math.sin(2*math.pi*3200*j/SAMPLE_RATE)+0.4*math.sin(2*math.pi*5100*j/SAMPLE_RATE))*dec*v
    return s

def gen_power_wash(d=6):
    n = int(SAMPLE_RATE*d); s = [0.0]*n; lp1=lp2=0.0
    for i in range(n):
        t = i/SAMPLE_RATE; w = random.uniform(-1,1)
        lp1 = lp1*0.7+w*0.3; lp2 = lp2*0.5+lp1*0.5
        spray = (lp1-lp2); pr = 0.3+0.15*math.sin(2*math.pi*1.8*t)
        splash = random.uniform(-1,1)*0.1 if random.random()<0.05 else 0
        s[i] = spray*pr+splash
    return s

def gen_grinder(d=6):
    n = int(SAMPLE_RATE*d); s = [0.0]*n
    for i in range(n):
        t = i/SAMPLE_RATE; mf = 950+40*math.sin(2*math.pi*4*t)
        motor = 0.15*math.sin(2*math.pi*mf*t)+0.08*math.sin(2*math.pi*mf*2*t)+0.05*math.sin(2*math.pi*mf*3*t)
        friction = random.uniform(-1,1)*(0.2+0.08*math.sin(2*math.pi*12*t))
        spark = random.uniform(-1,1)*0.4 if random.random()<0.015 else 0
        fade = min(1.0, min(t/0.5,(d-t)/0.5))
        s[i] = (motor+friction+spark)*fade*0.6
    return s

def gen_drill(d=6):
    n = int(SAMPLE_RATE*d); s = [0.0]*n
    for i in range(int(SAMPLE_RATE*3.0)):
        t = i/SAMPLE_RATE; st = math.sin(2*math.pi*1.6*t)
        fi = abs(st)**1.5; s[i] = random.uniform(-1,1)*fi*0.3+math.sin(2*math.pi*220*t)*fi*0.15
    ds = int(SAMPLE_RATE*3.2); dl = int(SAMPLE_RATE*2.3)
    for j in range(dl):
        t = j/SAMPLE_RATE; f = 400+min(600,t*1200)-(150 if t>1.2 else 0)
        ds2 = 0.25*math.sin(2*math.pi*f*t)+0.15*math.sin(2*math.pi*f*2.1*t)+random.uniform(-0.1,0.1)
        idx = ds+j
        if idx<n: s[idx] = ds2*0.5
    return s

def gen_spray(d=6):
    n = int(SAMPLE_RATE*d); s = [0.0]*n
    for t in [0.3,0.7,1.1,1.5]:
        si = int(SAMPLE_RATE*t)
        for j in range(int(SAMPLE_RATE*0.04)):
            dec = math.exp(-j/(0.008*SAMPLE_RATE))
            if si+j<n: s[si+j] += math.sin(2*math.pi*3400*j/SAMPLE_RATE)*dec*0.5
    sps = int(SAMPLE_RATE*2.2); spl = int(SAMPLE_RATE*3.5); lp = 0.0
    for j in range(spl):
        w = random.uniform(-1,1); lp = lp*0.4+w*0.6; hiss = (w-lp)*0.35
        idx = sps+j
        if idx<n: s[idx] += hiss
    return s

def gen_reveal(d=6):
    n = int(SAMPLE_RATE*d); s = [0.0]*n
    si = int(SAMPLE_RATE*0.8)
    for j in range(int(SAMPLE_RATE*0.03)):
        dec = (1-j/(0.03*SAMPLE_RATE))**2
        if si+j<n: s[si+j] += math.sin(2*math.pi*2100*j/SAMPLE_RATE)*dec*0.4
    cs = int(SAMPLE_RATE*1.0); cl = int(SAMPLE_RATE*4.8)
    notes = [130.81,196.00,246.94,329.63]
    for j in range(cl):
        t = j/SAMPLE_RATE; env = math.sin(math.pi*j/cl)**1.5
        chord = sum(math.sin(2*math.pi*f*t)*0.1 for f in notes)
        idx = cs+j
        if idx<n: s[idx] += chord*env
    return s

def gen_bgm(d=60):
    n = int(SAMPLE_RATE*d); s = [0.0]*n
    chords = [[174.61,220.00,261.63,329.63],[164.81,196.00,246.94,293.66],
              [146.83,174.61,220.00,261.63],[130.81,164.81,196.00,246.94]]
    cd = 3.0; tc = int(d/cd)
    for ci in range(tc):
        cn = chords[ci%4]; start = int(ci*cd*SAMPLE_RATE); cl = int(cd*SAMPLE_RATE)
        for j in range(cl):
            t = j/SAMPLE_RATE; env = math.exp(-t/2.2)*0.35+0.05; val = 0.0
            for note in cn:
                val += math.sin(2*math.pi*note*t)*0.06+math.sin(2*math.pi*note*2*t)*0.02
            crackle = random.uniform(-0.015,0.015) if random.random()<0.03 else 0
            idx = start+j
            if idx<n: s[idx] += (val*env)+crackle
    mx = max(abs(x) for x in s) or 1
    return [x/mx*0.4 for x in s]

if __name__ == "__main__":
    sfx = OUTPUT_DIR + "/sfx"
    bgm = OUTPUT_DIR + "/bgm"
    
    print("🎵 Generating ASMR Sound Effects...")
    write_wav(f"{sfx}/01_wind.wav", gen_wind())
    write_wav(f"{sfx}/02_ratchet.wav", gen_ratchet())
    write_wav(f"{sfx}/03_wash.wav", gen_power_wash())
    write_wav(f"{sfx}/04_grinder.wav", gen_grinder())
    write_wav(f"{sfx}/05_drill.wav", gen_drill())
    write_wav(f"{sfx}/06_drill2.wav", gen_drill())
    write_wav(f"{sfx}/07_spray.wav", gen_spray())
    write_wav(f"{sfx}/08_reveal.wav", gen_reveal())
    
    print("🎹 Generating Background Music...")
    write_wav(f"{bgm}/bgm_loop.wav", gen_bgm(60))
    
    print("✅ All audio assets ready!")
