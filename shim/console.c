/*
 * Minimal text console on the ABL/aboot splash framebuffer. With the MMU off
 * every access is Device memory, so stay aligned (-mstrict-align).
 * Adapted for Sony Xperia XZ Dual (kagura, MSM8996): auto-detects active
 * MDP5 SSPP source address and stride set up by Sony aboot.
 */
#include "console.h"
#include "font.h"
#include "pstore.h"

#define SCALE		3
#define CH_W		(8 * SCALE)
#define CH_H		(16 * SCALE)
#define MARGIN		24
#define LABEL_COLS	8

/* MSM8996 MDP5 SSPP registers (MDP base 0x00900000) */
#define MDP_SSPP_VIG0_SRC0_ADDR		0x00905014UL
#define MDP_SSPP_VIG0_SRC_YSTRIDE	0x00905024UL
#define MDP_SSPP_VIG0_SRC_FORMAT	0x00905030UL
#define MDP_SSPP_RGB0_SRC0_ADDR		0x00915014UL
#define MDP_SSPP_RGB0_SRC_YSTRIDE	0x00915024UL
#define MDP_SSPP_RGB0_SRC_FORMAT	0x00915030UL
#define MDP_SSPP_DMA0_SRC0_ADDR		0x00925014UL
#define MDP_SSPP_DMA0_SRC_YSTRIDE	0x00925024UL
#define MDP_SSPP_DMA0_SRC_FORMAT	0x00925030UL

volatile uint32_t *con_fb = (volatile uint32_t *)FB_BASE;
uint32_t active_stride = FB_STRIDE;
uint32_t active_bpp = FB_BPP;
static uint32_t con_bg;
static int row;
static int fb_probed = 0;

static void probe_mdp_fb(void)
{
	if (fb_probed)
		return;
	fb_probed = 1;

	/* Check RGB0, VIG0, and DMA0 pipes to find which one Sony aboot left active */
	uintptr_t pipes[3][3] = {
		{ MDP_SSPP_RGB0_SRC0_ADDR, MDP_SSPP_RGB0_SRC_YSTRIDE, MDP_SSPP_RGB0_SRC_FORMAT },
		{ MDP_SSPP_VIG0_SRC0_ADDR, MDP_SSPP_VIG0_SRC_YSTRIDE, MDP_SSPP_VIG0_SRC_FORMAT },
		{ MDP_SSPP_DMA0_SRC0_ADDR, MDP_SSPP_DMA0_SRC_YSTRIDE, MDP_SSPP_DMA0_SRC_FORMAT },
	};

	for (int i = 0; i < 3; i++) {
		uint32_t addr = *(volatile uint32_t *)pipes[i][0];
		uint32_t stride = *(volatile uint32_t *)pipes[i][1] & 0xffff;
		uint32_t fmt = *(volatile uint32_t *)pipes[i][2];
		if (addr >= 0x80000000U && addr < 0xe0000000U && stride >= 1080 * 3) {
			con_fb = (volatile uint32_t *)(uintptr_t)addr;
			active_stride = stride;
			active_bpp = stride / FB_W;
			plog_hex("MDP pipe", i);
			plog_hex("MDP fb_addr", addr);
			plog_hex("MDP stride", stride);
			plog_hex("MDP fmt", fmt);
			return;
		}
	}
	plog_hex("MDP fallback fb_addr", (uintptr_t)con_fb);
}

static void put_px(int x, int y, uint32_t c)
{
	if (active_bpp == 3) {
		volatile uint8_t *p = (volatile uint8_t *)con_fb + y * active_stride + x * 3;
		p[0] = c;
		p[1] = c >> 8;
		p[2] = c >> 16;
	} else {
		volatile uint32_t *row_p = (volatile uint32_t *)((volatile uint8_t *)con_fb + y * active_stride);
		row_p[x] = c;
	}
}

void con_flush(void)
{
#ifdef PIXEL1
	/*
	 * Command-mode panel, no autorefresh: MDP CTL0 START sends one frame.
	 */
	volatile uint32_t *intr = (volatile uint32_t *)0x901014UL;
	uint64_t t0, t, f;
	intr[1] = 1u << 8;
	__asm__ volatile("dsb sy" ::: "memory");
	*(volatile uint32_t *)0x90201cUL = 1;
	__asm__ volatile("mrs %0, cntfrq_el0" : "=r"(f));
	__asm__ volatile("mrs %0, cntpct_el0" : "=r"(t0));
	do {
		__asm__ volatile("mrs %0, cntpct_el0" : "=r"(t));
	} while (!(intr[0] & (1u << 8)) && t - t0 < f / 10);	/* 100 ms cap */
#endif
}

void con_clear(uint32_t bg)
{
	probe_mdp_fb();
	for (int y = 0; y < FB_H; y++)
		for (int x = 0; x < FB_W; x++)
			put_px(x, y, bg);
	con_bg = bg;
	row = 0;
}

static void put_char(int col, char ch, uint32_t fg)
{
	if (ch < 0x20 || ch > 0x7e)
		ch = '?';
	const unsigned char *g = font8x16[ch - 0x20];
	int x0 = MARGIN + col * CH_W, y0 = MARGIN + row * CH_H;
	if (x0 + CH_W > FB_W || y0 + CH_H > FB_H)
		return;
	for (int gy = 0; gy < 16; gy++)
		for (int gx = 0; gx < 8; gx++) {
			uint32_t c = (g[gy] & (0x80 >> gx)) ? fg : con_bg;
			for (int sy = 0; sy < SCALE; sy++)
				for (int sx = 0; sx < SCALE; sx++)
					put_px(x0 + gx * SCALE + sx, y0 + gy * SCALE + sy, c);
		}
}

static int put_str(int col, const char *s, uint32_t fg)
{
	while (*s)
		put_char(col++, *s++, fg);
	return col;
}

static void fmt_hex(char *buf, uint64_t v, int digits)
{
	static const char hex[] = "0123456789ABCDEF";
	for (int i = 0; i < digits; i++)
		buf[i] = hex[(v >> (4 * (digits - 1 - i))) & 0xf];
	buf[digits] = 0;
}

void con_skip(void)
{
	row++;
}

void con_str(const char *label, const char *s)
{
	put_str(0, label, YELLOW);
	put_str(LABEL_COLS, s, WHITE);
	row++;
}

void con_hex(const char *label, uint64_t v)
{
	char buf[17];
	fmt_hex(buf, v, 16);
	con_str(label, buf);
}

void con_hex2(const char *label, const char *a, uint32_t va, const char *b, uint32_t vb)
{
	char buf[9];
	int col = put_str(0, label, YELLOW);
	col = col < LABEL_COLS ? LABEL_COLS : col + 1;
	col = put_str(col, a, YELLOW);
	fmt_hex(buf, va, 8);
	col = put_str(col, buf, WHITE);
	if (b) {
		col = put_str(col + 1, b, YELLOW);
		fmt_hex(buf, vb, 8);
		put_str(col, buf, WHITE);
	}
	row++;
}
