/** Online secondary-path NLMS identification.
 *
 *  Identifies Ŝ(e,s) = speaker[s] → error_mic[e] acoustic transfer function.
 *
 *  Uses anti_spk (ANC output driving speakers) as excitation and err_mic
 *  (bandpassed error microphone) as response.
 *
 *  ══════════════════════════════════════════════════════════════════════════
 *  ⚠⚠ 2026-09-18 真机单变量 A/B 定案: 无辅助噪声时本辨识**不可用** ——
 *  它的稳态解不是 S, 而是 Ŝ ≡ 0.
 *
 *  原注释称 "disturbance residual acts as dither that averages out over time",
 *  该论断是错的: ANC 收敛后残差里**没有**不相关的 dither, 剩下的恰恰就是与
 *  anti 相关的那一部分 (因为 anti 就是为对消它而生成的).
 *
 *  推导 (NLMS 稳态: 残差与激励正交):
 *      e_id = err − Ŝ⊛anti,   err = d + S⊛anti
 *      E[e_id·anti] = 0  ⟹  (Ŝ − S)⊛R_aa = R_da,   R_da = E[d·anti]
 *      近完美对消时 S⊛anti ≈ −d  ⟹  R_da ≈ −S⊛R_aa
 *      ⟹  Ŝ⊛R_aa = 0  ⟹  Ŝ ≡ 0
 *  **对消越好, Ŝ 越趋近 0** —— 不动点在 0, 与步长无关.
 *
 *  后果链: Ŝ↓ → Fx_arr(=Ŝ⊛ref)↓ → FxLMS 梯度饿死 → 只剩 leak 在衰减 Wc
 *  → Wc→0 → 输出归零 → 误差麦回到无控基线. 而保护栈全是"太响"型判据
 *  (safety_mute: err_rms>8×ref; peak_mute: |anti|>0.99; P0-4: 要 anti_rms>0.25),
 *  没有任何一条能看见"静默自关"这条路径.
 *
 *  实测 (同一 exe, 只改 GFANC_SEC_MU, 90s adapt):
 *      µ=5e-6 → NR 峰值 9.2 → 末段 0.1;  ch1 从 0.10 回到 0.24~0.27 (无控基线 0.25)
 *      µ=0    → NR 稳定 9.2~12.8;        ch1 稳在 0.11~0.18 (= ~6dB 实测降噪)
 *  存入库槽的 Wc RMS 也从 0.010/0.016 变回 0.017/0.021 (µ=5e-6 存的是个 −3.4dB 缩水成品).
 *
 *  收敛速率: τ ≈ 1/(2µ) 样本 (归一化 NLMS). µ=5e-6 @16kHz → 6.3s,
 *  所以 90s 的标定窗口足以走完这条路. 降低 µ 只减慢走向 0, 不移动不动点 ——
 *  **这不是调参问题**.
 *
 *  正确的修法是注入辅助噪声 (auxiliary noise / probe signal) 并从 err 中
 *  减去其对消分量 —— 教科书在线 SPM 的标准做法. 在那之前本模块默认禁用
 *  (gfanc_config_t.sec_online_mu = 0).
 *  ══════════════════════════════════════════════════════════════════════════
 */

#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "sec_online.h"

int sec_online_init(sec_online_t *so, int E, int S, int sec_len,
                    int dsp_delay, float mu)
{
    so->E = E; so->S = S; so->sec_len = sec_len;
    so->dsp_delay = dsp_delay;
    so->sp = sec_len + dsp_delay;
    so->anti_ptr = 0;
    so->mu = mu;
    so->power_floor = 1e-6f;

    so->anti_hist = (float *)calloc(S * sec_len, sizeof(float));
    if (!so->anti_hist) return -1;

    return 0;
}

void sec_online_update(sec_online_t *so, const float *anti_spk,
                       const float *err_mic, float *sec_coeffs)
{
    int E = so->E, S = so->S, L = so->sec_len;
    int sp = so->sp, dly = so->dsp_delay;
    float mu = so->mu, pf = so->power_floor;
    int ptr = so->anti_ptr;

    /* 1. Write anti_spk to ring buffers */
    for (int s = 0; s < S; s++) {
        /* NaN guard: poisoned anti poisons the entire Ŝ delay line permanently */
        float a = anti_spk[s];
        if (!isfinite(a)) a = 0.0f;
        so->anti_hist[s * L + ptr] = a;
    }
    ptr = (ptr + 1) % L;
    so->anti_ptr = ptr;

    /* 2. Compute ring read layout: newest → oldest, two linear segments.
     *    segment 1: newest, newest-1, ..., 0
     *    segment 2: L-1, L-2, ..., newest+1 */
    int newest = (ptr == 0) ? L - 1 : ptr - 1;
    int seg1_len = newest + 1;          /* indices newest .. 0 inclusive */
    int seg2_len = L - seg1_len;        /* indices L-1 .. newest+1 */

    /* 3. Power per speaker: Σ anti[s]² over the delay line.
     *    Same for all error mics (same excitation drives all paths). */
    float power[/* GFANC_S_MAX */ 4];   /* max S=4 (GFANC_S_MAX) */
    for (int s = 0; s < S; s++) {
        float pwr = pf;
        float *hist = so->anti_hist + s * L;

        /* seg1: newest .. 0 */
        for (int i = newest; i >= 0; i--)
            pwr += hist[i] * hist[i];
        /* seg2: L-1 .. newest+1 */
        for (int i = L - 1; i > newest; i--)
            pwr += hist[i] * hist[i];

        power[s] = pwr;
    }

    /* 4. Per error mic: predict total Ŝ contribution, then update all Ŝ(e,*) */
    for (int e = 0; e < E; e++) {
        /* 4a. y_pred = Σ_{s,k} Ŝ[e,s,k] * anti[s, delayed_k] */
        float y_pred = 0.0f;
        for (int s = 0; s < S; s++) {
            float *coef = sec_coeffs + (e * S + s) * sp + dly;
            float *hist = so->anti_hist + s * L;

            /* seg1 */
            int k = 0;
            for (int i = newest; i >= 0; i--, k++)
                y_pred += coef[k] * hist[i];
            /* seg2 */
            for (int i = L - 1; i > newest; i--, k++)
                y_pred += coef[k] * hist[i];
        }

        /* 4b. Identification error */
        float em = err_mic[e];
        if (!isfinite(em)) em = 0.0f;
        float e_id = em - y_pred;

        /* 4c. NLMS update: Ŝ[e,s,k] += μ × e_id × anti[s,k] / power[s] */
        for (int s = 0; s < S; s++) {
            float *coef = sec_coeffs + (e * S + s) * sp + dly;
            float *hist = so->anti_hist + s * L;
            float inv_pwr = mu / power[s];

            /* seg1 */
            int k = 0;
            for (int i = newest; i >= 0; i--, k++)
                coef[k] += inv_pwr * e_id * hist[i];
            /* seg2 */
            for (int i = L - 1; i > newest; i--, k++)
                coef[k] += inv_pwr * e_id * hist[i];
        }
    }
}

void sec_online_free(sec_online_t *so)
{
    free(so->anti_hist);
    so->anti_hist = NULL;
}
