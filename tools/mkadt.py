#!/usr/bin/env python3
"""Build the minimal Apple Device Tree that the SWEET xnu needs to boot.

Adapted for Sony Xperia XZ Dual (kagura, MSM8996, 3 GB RAM).
Usage:  mkadt.py OUT.adt [--dump] [--qemu] [--highmem] [--pixel1] [--kagura]
"""
import hashlib, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt  # noqa: E402

PHYS_BASE = 0xb0000000
MEM_SIZE = 0x4d000000
HIGH_PHYS_BASE = 0x100000000
HIGH_MEM_SIZE = 0xfcc00000
SOC_BASE = 0x01000000

GICD, GICD_SIZE = 0x17a00000, 0x10000
GICR, GICR_SIZE = 0x17a60000, 0x100000
FB, FB_SIZE = 0x9c000000, 0x1700000
SWEET_ECID = 0x5357454554000001  # 'SWEET' + 1, synthetic
FB_W, FB_H, FB_STRIDE = 1080, 2400, 1080 * 4
UFS, UFS_SIZE = 0x01d84000, 0x3000
TIMEBASE = 19200000
VTIMER_INTID = 19
QEMU_GICD, QEMU_GICR, QEMU_TIMEBASE = 0x08000000, 0x080a0000, 62500000
QEMU_VTIMER_INTID = 27

# Sony Xperia XZ Dual (kagura, MSM8996, 3 GB LPDDR4).
# Upper DDR rank on 3 GB MSM8996 (kagura) is 1.5 GB (0x60000000) at 0x100000000;
# we reserve a small margin at the top (0x5e000000 = 1504 MB) just like sailfish.
PIXEL1 = dict(
    phys_base=0x100000000, mem_size=0x5e000000,  # 1.5 GB upper DDR bank on 3 GB Xperia XZ
    gicd=0x9bc0000, gicr=0x9c00000, gicr_stride=0x40000,
    vtimer=27,
    fb=0x83400000, fb_size=0x2400000, fb_w=1080, fb_h=1920, fb_bpp=24,
    fb_kickoff=0x90201c,  # command-mode panel: MDP CTL0 START sends a frame
    ufs=0x740000, ufs_size=0x1000,  # Sony kagura SDHC1 (eMMC 5.1 HC) at 0x00740000
    # MPIDR, cluster, max clock: 2 x 1.59 GHz + 2 x 2.15 GHz Kryo (Snapdragon 820)
    cpus=[(0x0, 0, 1593600000), (0x1, 0, 1593600000),
          (0x100, 1, 2150400000), (0x101, 1, 2150400000)],
)

BOOT_MANIFEST_HASH = hashlib.sha384(b'sweet boot manifest').digest()

D22AP_ADT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../research/ipsw-x/d22ap.adt')
D20AP_ADT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../research/ipsw-8/d20ap.adt')


def d22ap_product(path=D22AP_ADT):
    if not os.path.exists(path):
        # Built-in iPhone 8 (D20AP) /product fallback when IPSW d20ap.adt is not in research/
        return [
            ('product-name', cstr('iPhone 8')),
            ('product-description', cstr('iPhone 8')),
            ('product-id', u32(1)),
            ('device-color-policy', u32(1)),
            ('artwork-device-idiom', cstr('phone')),
            ('artwork-scale-factor', u32(2)),
            ('artwork-device-subtype', u32(1334)),
            ('artwork-display-gamut', cstr('sRGB')),
            ('display-gamut', cstr('sRGB')),
            ('oled-display', u32(0)),
            ('island-notch-location', u32(0)),
        ]
    root, _ = adt.parse(open(path, 'rb').read())
    for c in root.children:
        if dict((k, v) for k, f, v in c.props).get('name') == b'product\0':
            return [(k, v) for k, f, v in c.props if not f and k not in ('name', 'AAPL,phandle')]
    raise SystemExit(f'{path}: no /product node')

u32 = lambda *v: struct.pack('<%dI' % len(v), *v)
u64 = lambda *v: struct.pack('<%dQ' % len(v), *v)
cstr = lambda s: s.encode() + b'\0'


def node(name, props=(), children=()):
    n = adt.Node()
    n.props = [('name', 0, cstr(name))] + [(k, 0, v) for k, v in props]
    n.children = list(children)
    return n


def build(seed=None, qemu=False, highmem=False, pixel1=False):
    phys_base, mem_size = (HIGH_PHYS_BASE, HIGH_MEM_SIZE) if highmem else (PHYS_BASE, MEM_SIZE)
    gicd, gicr, timebase = (QEMU_GICD, QEMU_GICR, QEMU_TIMEBASE) if qemu else (GICD, GICR, TIMEBASE)
    vtimer = QEMU_VTIMER_INTID if qemu else VTIMER_INTID
    if pixel1:
        P = PIXEL1
        phys_base, mem_size, gicd, gicr, vtimer = P['phys_base'], P['mem_size'], P['gicd'], P['gicr'], P['vtimer']
    seed = seed if seed is not None else os.urandom(64)
    phandle = iter(range(1, 1000))
    ph = lambda: ('AAPL,phandle', u32(next(phandle)))

    chosen = node('chosen', [
        ph(),
        ('dram-base', u64(phys_base)),
        ('dram-size', u64(mem_size)),
        ('random-seed', seed),
        ('debug-enabled', u32(1)),
        ('firmware-version', cstr('sweet-shim')),
        ('system-firmware-version', cstr('sweet-shim')),
        ('boot-manifest-hash', BOOT_MANIFEST_HASH),
        ('crypto-hash-method', cstr('sha2-384')),
        ('display-scale', u32(2 if pixel1 else 3)),
        ('unique-chip-id', struct.pack('<Q', SWEET_ECID)),
        ('chip-id', u32(0x8015)),
        ('mac-address-wifi0', bytes.fromhex('02005e77ee10')),
        ('mac-address-bluetooth0', bytes.fromhex('02005e77ee11')),
        ('certificate-production-status', u32(0)),
        ('effective-production-status-ap', u32(0)),
        ('certificate-security-mode', u32(1)),
        ('effective-security-mode-sep', u32(1)),
    ], [node('memory-map', [ph()]),
        node('asmb', [ph(), ('lp-sip0', u64(0x6f)), ('lp-sip1', u32(1))])])

    cpu_nodes = []
    for core in range(1 if qemu else 8):
        if pixel1:
            break
        cpu_nodes.append(node(f'cpu{core}', [
            ph(),
            ('device_type', cstr('cpu')),
            ('compatible', cstr('qcom,kryo470') + cstr('ARM,v8')),
            ('reg', u32(core << 8)),
            ('cpu-id', u32(core)),
            ('cluster-id', u32(0)),
            ('cluster-type', u32(0)),
            ('die-cluster-id', u32(0)),
            ('cluster-core-id', u32(core)),
            ('l2-cache-id', u32(core)),
            ('l3-cache-id', u32(0)),
            ('state', cstr('running' if core == 0 else 'stopped')),
            ('timebase-frequency', u32(timebase)),
            ('clock-frequency', u32(2304000000 if core >= 6 else 1804800000)),
            ('bus-frequency', u32(100000000)),
            ('memory-frequency', u32(1866000000)),
            ('peripheral-frequency', u32(timebase)),
            ('fixed-frequency', u32(timebase)),
        ]))
    for core, (mpidr, cluster, hz) in enumerate(PIXEL1['cpus'] if pixel1 else []):
        cpu_nodes.append(node(f'cpu{core}', [
            ph(),
            ('device_type', cstr('cpu')),
            ('compatible', cstr('qcom,kryo') + cstr('ARM,v8')),
            ('reg', u32(mpidr)),
            ('cpu-id', u32(core)),
            ('cluster-id', u32(0)),
            ('cluster-type', u32(0)),
            ('die-cluster-id', u32(0)),
            ('cluster-core-id', u32(core)),
            ('l2-cache-id', u32(cluster)),
            ('state', cstr('running' if core == 0 else 'stopped')),
            ('timebase-frequency', u32(timebase)),
            ('clock-frequency', u32(hz)),
            ('bus-frequency', u32(100000000)),
            ('memory-frequency', u32(1866000000)),
            ('peripheral-frequency', u32(timebase)),
            ('fixed-frequency', u32(timebase)),
        ]))
    cpus = node('cpus', [ph(), ('#address-cells', u32(1)),
                         ('#size-cells', u32(0))], cpu_nodes)

    gic = node('gic', [
        ph(),
        ('compatible', cstr('arm,gic-v3')),
        ('interrupt-controller', b''),
        ('virtual-timer-intid', u32(vtimer)),
        ('reg', u64(gicd - SOC_BASE, GICD_SIZE, gicr - SOC_BASE, GICR_SIZE)),
    ] + ([('redistributor-stride', u32(PIXEL1['gicr_stride']))] if pixel1 else []))
    arm_io = node('arm-io', [
        ph(),
        ('device_type', cstr('sweet-io')),
        ('compatible', cstr('sweet-io') + cstr('arm-io')),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
        ('ranges', u64(0, SOC_BASE, 0x100000000 - SOC_BASE)),
    ], [gic,
        node('wdt', [ph(), ('no-pmu', u32(1))]),
        node('disp0', [
            ph(),
            ('device_type', cstr('display-subsystem')),
            ('compatible', cstr('sweet,display')),
            ('canvas-width', u32(750 if pixel1 else 1125)),
            ('canvas-height', u32(1334 if pixel1 else 2436)),
        ])])

    fbcon = node('sweet-fbcon', [
        ph(),
        ('reg', u64(FB, FB_SIZE)),
        ('width', u32(FB_W)),
        ('height', u32(FB_H)),
        ('stride', u32(FB_STRIDE)),
    ])
    if pixel1:
        P = PIXEL1
        fbcon = node('sweet-fbcon', [
            ph(),
            ('reg', u64(P['fb'], P['fb_size'])),
            ('width', u32(P['fb_w'])),
            ('height', u32(P['fb_h'])),
            ('stride', u32(P['fb_w'] * P['fb_bpp'] // 8)),
            ('bits-per-pixel', u32(P['fb_bpp'])),
            ('kickoff-reg', u64(P['fb_kickoff'])),
        ])

    ufs = node('sweet-ufs', [
        ph(),
        ('compatible', cstr('qcom,ufshc')),
        ('reg', u64(PIXEL1['ufs'], PIXEL1['ufs_size']) if pixel1 else u64(UFS, UFS_SIZE)),
    ])

    defaults = node('defaults', [ph(), ('no-effaceable-storage', u32(1))])

    buttons = node('buttons', [
        ph(),
        ('button-names', cstr('volup') + cstr('voldown') + cstr('hold')),
        ('home-button-type', u32(1 if pixel1 else 2)),
        ('opposed-power-vol-buttons', u32(1)),
    ])

    product_props = d22ap_product(D20AP_ADT if pixel1 else D22AP_ADT)
    if pixel1 and product_props:
        product_props = [(k, cstr('sRGB') if k in ('artwork-display-gamut', 'display-gamut') else v)
                         for k, v in product_props]
    product = [node('product', [ph()] + product_props)] if product_props else []

    ident = (('D20AP', 'iPhone10,1', 'D20', 'google,sailfish', 'qcom,msm8996') if pixel1 else
             ('D22AP', 'iPhone10,3', 'D22', 'xiaomi,sweet', 'qcom,sm7150'))
    compat = cstr(ident[0]) + cstr(ident[1]) + cstr('xiaomi,sweet')
    if pixel1:
        compat += cstr(ident[3])
    return node('device-tree', [
        ph(),
        ('compatible', compat + cstr(ident[4]) + cstr('AppleARM')),
        ('model', cstr(ident[1])),
        ('target-type', cstr(ident[2])),
        ('target-sub-type', cstr(ident[0])),
        ('manufacturer', cstr('Apple Inc.')),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
    ], [chosen, defaults, cpus, arm_io, fbcon, buttons] + product + ([] if qemu else [ufs]))


if __name__ == '__main__':
    is_kagura = ('--pixel1' in sys.argv) or ('--kagura' in sys.argv)
    root = build(qemu='--qemu' in sys.argv, highmem='--highmem' in sys.argv, pixel1=is_kagura)
    blob = adt.serialize(root)
    open(sys.argv[1], 'wb').write(blob)
    if '--dump' in sys.argv:
        adt.dump(adt.parse(blob)[0])
    print(f'{sys.argv[1]}: {len(blob)} bytes', file=sys.stderr)
