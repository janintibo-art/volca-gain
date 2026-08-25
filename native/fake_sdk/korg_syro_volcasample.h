/* FAUX en-tete reproduisant l'API publique du Syro SDK, uniquement pour
   verifier que syro_wrap.c + le wrapper ctypes fonctionnent ensemble. */
#ifndef KORG_SYRO_VOLCASAMPLE_H
#define KORG_SYRO_VOLCASAMPLE_H
#include <stdint.h>
typedef enum { Status_Success=0, Status_IllegalDataType, Status_OutOfRange } SyroStatus;
typedef enum { DataType_Sample_Liner=0, DataType_Sample_Compress, DataType_Sample_Erase,
               DataType_Sample_All, DataType_Sample_AllCompress, DataType_Pattern } SyroDataType;
typedef enum { LittleEndian=0, BigEndian } SyroEndian;
typedef struct { SyroDataType DataType; uint8_t *pData; uint32_t Number; uint32_t Size;
                 uint32_t Quality; uint32_t Fs; SyroEndian SampleEndian; } SyroData;
typedef void* SyroHandle;
SyroStatus SyroVolcaSample_Start(SyroHandle *pHandle, SyroData *pData, int NumOfData,
                                 uint32_t Flags, uint32_t *pNumOfSyroFrame);
SyroStatus SyroVolcaSample_GetSample(SyroHandle Handle, int16_t *pLeft, int16_t *pRight);
SyroStatus SyroVolcaSample_End(SyroHandle Handle);
#endif
