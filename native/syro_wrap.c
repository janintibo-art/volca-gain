/*
 * volcagain / syro_wrap.c
 *
 * Fine couche C au-dessus du Syro SDK de Korg (depot korginc/volcasample).
 *
 * Pourquoi ce fichier ? Le SDK fournit SyroVolcaSample_GetSample() qui rend
 * UNE trame a la fois. Appeler ca depuis Python via ctypes ferait des millions
 * d'appels (plusieurs minutes sur telephone). Ici on boucle en C et on rend le
 * flux complet en un seul appel.
 *
 * Le SDK Korg n'est PAS inclus dans ce depot (licence Korg). Il est ajoute en
 * sous-module git : voir native/README.md
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "korg_syro_volcasample.h"

#define VG_TYPE_SAMPLE   0
#define VG_TYPE_ERASE    1
#define VG_TYPE_PATTERN  2

#define VG_OK             0
#define VG_ERR_START     -1
#define VG_ERR_ALLOC     -2
#define VG_ERR_RENDER    -3
#define VG_ERR_EMPTY     -4

/* Doit correspondre exactement a VGData dans volca/syro.py */
typedef struct {
    int32_t         type;      /* VG_TYPE_*                     */
    int32_t         number;    /* numero de slot 0..99          */
    int32_t         quality;   /* 8..16 bits (mode compresse)   */
    int32_t         compress;  /* 0 = lineaire, 1 = compresse   */
    uint32_t        fs;        /* frequence d'echantillonnage   */
    uint32_t        size;      /* taille de data en octets      */
    const uint8_t  *data;      /* PCM 16 bits mono little endian*/
} VGData;

const char *volcagain_version(void)
{
    return "volcagain-syro 1.0";
}

/*
 * Rend le flux de transfert complet.
 *
 *   items      : tableau de VGData
 *   count      : nombre d'elements
 *   out        : recoit un buffer stereo entrelace int16 (a liberer avec
 *                volcagain_free)
 *   out_frames : recoit le nombre de trames stereo
 *
 * Retour : VG_OK ou un code negatif.
 */
int volcagain_render(const VGData *items, int count,
                     int16_t **out, uint32_t *out_frames)
{
    SyroData     *sd     = NULL;
    SyroHandle    handle;
    SyroStatus    st;
    uint32_t      frames = 0;
    int16_t      *buf    = NULL;
    int           i;

    if (!items || count <= 0 || !out || !out_frames)
        return VG_ERR_EMPTY;

    *out = NULL;
    *out_frames = 0;

    sd = (SyroData *)calloc((size_t)count, sizeof(SyroData));
    if (!sd)
        return VG_ERR_ALLOC;

    for (i = 0; i < count; i++) {
        const VGData *it = &items[i];

        sd[i].Number       = (uint32_t)it->number;
        sd[i].pData        = (uint8_t *)it->data;
        sd[i].Size         = it->size;
        sd[i].Quality      = (uint32_t)it->quality;
        sd[i].Fs           = it->fs;
        sd[i].SampleEndian = LittleEndian;

        switch (it->type) {
        case VG_TYPE_ERASE:
            sd[i].DataType = DataType_Sample_Erase;
            sd[i].pData    = NULL;
            sd[i].Size     = 0;
            break;
        case VG_TYPE_PATTERN:
            sd[i].DataType = DataType_Pattern;
            break;
        default:
            sd[i].DataType = it->compress
                           ? DataType_Sample_Compress
                           : DataType_Sample_Liner;
            break;
        }
    }

    st = SyroVolcaSample_Start(&handle, sd, count, 0, &frames);
    if (st != Status_Success || frames == 0) {
        free(sd);
        return VG_ERR_START;
    }

    /* stereo entrelace */
    buf = (int16_t *)malloc((size_t)frames * 2u * sizeof(int16_t));
    if (!buf) {
        SyroVolcaSample_End(handle);
        free(sd);
        return VG_ERR_ALLOC;
    }

    for (i = 0; (uint32_t)i < frames; i++) {
        int16_t l = 0, r = 0;
        st = SyroVolcaSample_GetSample(handle, &l, &r);
        if (st != Status_Success) {
            SyroVolcaSample_End(handle);
            free(buf);
            free(sd);
            return VG_ERR_RENDER;
        }
        buf[i * 2]     = l;
        buf[i * 2 + 1] = r;
    }

    SyroVolcaSample_End(handle);
    free(sd);

    *out        = buf;
    *out_frames = frames;
    return VG_OK;
}

void volcagain_free(int16_t *p)
{
    if (p)
        free(p);
}
