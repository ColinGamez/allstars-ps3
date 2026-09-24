import struct, os, sys
from Crypto.Cipher import AES
iso_in=r'C:\Users\Colin\Desktop\Playstation all stars battle royale\Game\PlayStation All-Stars Battle Royale (USA) (En,Fr,Es,Pt).iso'
dkey_path=r'C:\Users\Colin\Desktop\Playstation all stars battle royale\Game\PlayStation All-Stars Battle Royale (USA) (En,Fr,Es,Pt).dkey'
iso_out=r'C:\Users\Colin\Desktop\Playstation all stars battle royale\Game\PlayStation All-Stars Battle Royale (USA) (En,Fr,Es,Pt).dec.iso'
key=bytes.fromhex(open(dkey_path,'rb').read().strip().decode())
SECTOR=2048
size=os.path.getsize(iso_in)
print(f"in {size} bytes, {size//SECTOR} sectors", flush=True)
with open(iso_in,'rb') as f:
    hdr=f.read(4096)
rc=struct.unpack('>I', hdr[0:4])[0]
print(f"region_count {rc}", flush=True)
vals=[struct.unpack('>I', hdr[12+i*4:16+i*4])[0] for i in range(rc*2-1)]
regions=[]
for i,v in enumerate(vals):
    mod=i%2
    first=0 if i==0 else regions[i-1][1]+1
    last=(v-mod)*SECTOR+SECTOR-1
    regions.append((first,last,mod==1))
    print(f" region {i} {'ENC' if mod==1 else 'plain'} {first//SECTOR}-{last//SECTOR}", flush=True)
# stream decrypt
import tqdm
with open(iso_in,'rb') as fin, open(iso_out,'wb') as fout:
    # plain header copy fast: find first enc byte
    enc_start=regions[1][0] if len(regions)>1 else size
    print(f"copying plain header {enc_start} bytes...", flush=True)
    fin.seek(0)
    remaining=enc_start
    while remaining>0:
        chunk=fin.read(min(remaining, 16*1024*1024))
        if not chunk: break
        fout.write(chunk)
        remaining-=len(chunk)
    # decrypt sector by sector for enc region(s)
    for (first,last,enc) in regions:
        if not enc:
            continue
        nsec=(last-first+1)//SECTOR
        print(f"decrypting {nsec} sectors at {first}...", flush=True)
        fin.seek(first)
        # reuse cipher? No, IV changes per sector, need new object per sector
        # Use ECB + manual CBC for speed: decrypt blocks then xor
        ecb=AES.new(key, AES.MODE_ECB)
        import tqdm
        for s in tqdm.tqdm(range(nsec)):
            lb=(first//SECTOR)+s
            enc_data=fin.read(SECTOR)
            if len(enc_data)<SECTOR:
                enc_data+=b'\x00'*(SECTOR-len(enc_data))
            # CBC decrypt with IV = 12 zeros + BE LBA
            # manual: ECB decrypt each 16B block, xor with prev (IV for first)
            out=bytearray(SECTOR)
            prev=b'\x00'*12+struct.pack('>I', lb)
            for b in range(0, SECTOR, 16):
                dec_block=ecb.decrypt(enc_data[b:b+16])
                out[b:b+16]=bytes(x^y for x,y in zip(dec_block, prev))
                prev=enc_data[b:b+16]
            fout.write(out)
            if (s+1)%50000==0:
                print(f"  {s+1}/{nsec}", flush=True)
    # copy trailing plain regions
    pos=fout.tell()
    fin.seek(pos)
    print(f"copying tail from {pos}...", flush=True)
    while True:
        chunk=fin.read(16*1024*1024)
        if not chunk: break
        fout.write(chunk)
print("done", flush=True)
