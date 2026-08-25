#include "korg_syro_volcasample.h"
#include <stdlib.h>
typedef struct { uint32_t total; uint32_t pos; uint32_t checksum; } Fake;
SyroStatus SyroVolcaSample_Start(SyroHandle *pH, SyroData *pD, int n, uint32_t f, uint32_t *pF){
  Fake *k; uint32_t tot=0; int i;
  if(!pH||!pD||n<=0||!pF) return Status_OutOfRange;
  for(i=0;i<n;i++){
    if(pD[i].DataType==DataType_Sample_Erase){ tot+=4410; }
    else { if(!pD[i].pData||!pD[i].Size) return Status_IllegalDataType;
           tot += pD[i].Size/2 + 4410; }
    if(pD[i].Number>99) return Status_OutOfRange;
  }
  k=(Fake*)calloc(1,sizeof(Fake)); k->total=tot; k->checksum=(uint32_t)n;
  *pH=(SyroHandle)k; *pF=tot; return Status_Success;
}
SyroStatus SyroVolcaSample_GetSample(SyroHandle h, int16_t *l, int16_t *r){
  Fake *k=(Fake*)h; if(!k||k->pos>=k->total) return Status_OutOfRange;
  *l=(int16_t)((k->pos*37)%20000-10000); *r=(int16_t)-*l; k->pos++; return Status_Success;
}
SyroStatus SyroVolcaSample_End(SyroHandle h){ free(h); return Status_Success; }
