#!/bin/bash
# Wrap a raw arm64 Image like a stock v0 boot.img (Sony Xperia XZ kagura / Pixel 1):
# keeps the stock DTBs (whether appended to Image.gz-dtb or in the v0 dt_size slot),
# ramdisk and header.
# Usage: tools/mkboot-v0.sh STOCK_BOOT.img Image OUT.img
set -euo pipefail
stock=$1 image=$2 out=$3
tmp=$(mktemp -d)
gzip -9 -n -c "$image" > "$tmp/Image.gz"
python3 -I - "$stock" "$tmp/Image.gz" "$out" <<'EOF'
import hashlib, struct, sys
stock, gz, out = sys.argv[1:]
b = open(stock, 'rb').read()
assert b[:8] == b'ANDROID!'
ksize, _, rsize, _, ssize, _, _, page, dtsize = struct.unpack_from('<9I', b, 8)
up = lambda n: (n + page - 1) // page * page
kernel = b[page:page + ksize]
ramdisk = b[page + up(ksize):][:rsize]
second = b[page + up(ksize) + up(rsize):][:ssize]
dt_part = b[page + up(ksize) + up(rsize) + up(ssize):][:dtsize] if dtsize else b''

if b'\xd0\x0d\xfe\xed' in kernel:
    dtbs = kernel[kernel.index(b'\xd0\x0d\xfe\xed'):]
else:
    dtbs = b''

kernel = open(gz, 'rb').read() + dtbs
h = bytearray(b[:page])
struct.pack_into('<I', h, 8, len(kernel))
sha = hashlib.sha1()
for part in (kernel, ramdisk, second) + ((dt_part,) if dtsize else ()):
    sha.update(part); sha.update(struct.pack('<I', len(part)))
h[576:608] = sha.digest().ljust(32, b'\0')
pad = lambda d: d + b'\0' * (up(len(d)) - len(d))
open(out, 'wb').write(bytes(h) + pad(kernel) + pad(ramdisk) + pad(second) + (pad(dt_part) if dtsize else b''))
print(f'{out}: kernel {len(kernel)} bytes ({len(dtbs)} appended DTBs, {len(dt_part)} dt_part bytes)')
EOF
rm -rf "$tmp"
